"""desk do: Jev drives. Each step it sees the screen, the goal, what's been done, and the window's labelled elements,
and picks one move: click a labelled element, click a spot it points at, press a shortcut, type a text it was given,
or stop. Jev chooses and points; it doesn't write, so anything to type comes in with --type.

  desk do "Click Save, then Share" [--app Safari] [--type "text"]... [--steps 15]

It stops by itself when Jev judges the goal done, when the next move looks like sending, submitting, deleting or
paying (those go back to Claude/Zac), when it repeats itself, or after --steps.
"""
import json
import re
import time

import pyautogui

from . import RUNTIME, ax, desk

DONE_AT = 0.6  # Noul "has this step been done?" above this moves on to the next step
RISKY_AT = 0.5  # Noul "would the next move send/submit/delete/pay?" above this hands back
DISAGREE = 120  # screen points between the chosen label and where Jev points before the pointing wins
MAX_ELEMENTS = 60  # labelled clickables offered per step; more crowds the choice


def where(x, y, w, h):
    """A coarse place on screen, so two elements with the same label (Safari's Share vs the page's) can be told apart."""
    return ("top" if y < h / 3 else "middle" if y < 2 * h / 3 else "bottom") + "-" + \
        ("left" if x < w / 3 else "centre" if x < 2 * w / 3 else "right")


def element_at(x, y):
    """What's under a screen point, as 'button ☆', for the history after clicking a spot Jev pointed at."""
    from ApplicationServices import AXUIElementCopyElementAtPosition, AXUIElementCreateSystemWide

    err, e = AXUIElementCopyElementAtPosition(AXUIElementCreateSystemWide(), x, y, None)
    if err or e is None:
        return ""
    role = ax.ROLES.get(ax.attr(e, "AXRole") or "", "")
    text = ax.label(e, role)
    return f"{role} '{text}'".strip() if text else ""


def flags(args, name):
    return [args[i + 1] for i, a in enumerate(args[:-1]) if a == name]


def step_spec(step, task, history, title, elements, texts):
    actions = {"click_labelled": "Click one of the elements listed in `elements`.",
               "click_point": "Click something visible on `screen` that is not listed in `elements`.",
               "stuck": "Nothing available does `step`, or it needs a person (login, password, a choice only they can make)."}
    actions.update({f"key {name}": f"Press {combo} ({name})." for name, combo in desk.KEYS.items()})
    actions.update({f"type {i}": f"Type this text at the cursor: {t}" for i, t in enumerate(texts)})
    questions = {
        "done": {"type": "noul", "instructions": "Judging by `screen` and `done_so_far`, has `step` been done?"},
        "risky": {"type": "noul", "instructions": "Would doing `step` send, submit, post, delete, buy or pay for something?"},
        "action": {"type": "choice", "instructions": "What single move does `step` on `screen`?", "criteria": actions},
        "point": {"type": "box", "instructions": "what to click to do `step`,"},
    }
    if elements:
        questions["element"] = {"type": "choice", "criteria": elements,
                                "instructions": "Which element in `elements` should be clicked to do `step`?"}
    state = {"step": step, "whole_task": task, "done_so_far": history or ["nothing yet"], "window": title, "elements": elements}
    return {"state": state, "questions": questions}


def plan(task):
    """The caller writes the order ("A, then B; C"); Jev only does one step at a time. Jev judges a step well but
    loses track of order when handed the whole task (it clicked the last button first)."""
    return [p.strip(" ,.") for p in re.split(r",?\s*\bthen\b\s*|;\s*", task, flags=re.I) if p.strip(" ,.")]


def pick(answer):
    """Jev's chosen move, but not a timid `stuck`: when it's under 60% sure, take the best real move instead."""
    probs = answer["probabilities"]
    if answer["choice"] == "stuck" and probs.get("stuck", 1) < 0.6:
        return max((m for m in probs if m != "stuck"), key=probs.get, default="stuck")
    return answer["choice"]


def run(args):
    task = next(a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or not args[i - 1].startswith("--")))
    app_name = (flags(args, "--app") or ["Safari"])[0]
    texts = flags(args, "--type")
    budget = int((flags(args, "--steps") or [15])[0])
    desk.do("open", [app_name])
    desk.jev_start()
    screen_w, screen_h = pyautogui.size()
    history, moves = [], 0
    for s_i, step in enumerate(plan(task), 1):
        tries = []
        while True:
            if moves >= budget:
                return f"Ran out of moves ({budget}) on step {s_i}: {step}"
            t0 = time.time()
            full = pyautogui.screenshot()
            k = full.width / screen_w
            full.resize((desk.MAX_SIDE, round(full.height * desk.MAX_SIDE / full.width))).save(RUNTIME / "do.png")
            _, title, found = ax.elements(app_name)
            on_screen = [(i, e) for i, e in enumerate(found) if e["role"] in desk.CLICKABLE and e["text"]
                         and 0 <= e["x"] < screen_w and 0 <= e["y"] < screen_h][:MAX_ELEMENTS]
            elements = {f"#{i + 1}": f"{e['role']} {e['text']} ({where(e['x'], e['y'], screen_w, screen_h)})" for i, e in on_screen}
            a = desk.jev("raw", json.dumps(step_spec(step, task, history, title, elements, texts)), RUNTIME / "do.png")
            if tries and a["done"] >= DONE_AT:  # a step counts as done only after a move made for it
                break
            move = pick(a["action"])
            if move == "stuck":
                return f"Jev is stuck on step {s_i} ({step}): it needs a person, or nothing on screen does it"
            if a["risky"] >= RISKY_AT and (move.startswith("click") or move == "key submit"):
                return f"Stopped before step {s_i} ({step}): it looks like sending/submitting/deleting (risky {a['risky']:.2f}); that's Zac's call"
            e = found[int(a["element"]["choice"][1:]) - 1] if "element" in a else None
            b = a["point"]["box"]
            px, py = (b["left"] + b["right"]) / 2 * screen_w, (b["top"] + b["bottom"]) / 2 * screen_h
            if move == "click_labelled" and e and a["point"]["confidence"] >= desk.MIN_CONFIDENCE \
                    and abs(px - e["x"]) + abs(py - e["y"]) > DISAGREE:
                # where Jev points on screen isn't where its chosen label is. Labels can mislead (the accessibility
                # tree listed Safari's Share but not the page's), so the pixels win.
                move = "click_point"
            if move == "click_labelled" and e:
                desk.click(e["x"], e["y"], "left")
                did = f"clicked the {e['role']} '{e['text']}'"
            elif move.startswith("click"):  # a spot Jev points at, sharpened on a close-up like desk find
                box = (b["left"] * full.width, b["top"] * full.height, b["right"] * full.width, b["bottom"] * full.height)
                better = desk.zoom(full, box, desk.CLOSE_UP, "what to click to " + step, 2)
                l, t, r, bt = better[0] if better else box
                x, y = (l + r) / 2 / k, (t + bt) / 2 / k
                desk.click(x, y, "left")
                name = element_at(x, y)
                did = f"clicked the {name}" if name else f"clicked the spot at ({round(x)}, {round(y)}) ({where(x, y, screen_w, screen_h)})"
            elif move.startswith("key "):
                desk.do("key", [desk.KEYS[move[4:]]])
                did = f"pressed {desk.KEYS[move[4:]]} ({move[4:]})"
            else:  # type N
                desk.paste(texts[int(move[5:])])
                did = f"typed {texts[int(move[5:])]!r}"
            moves += 1
            history.append(f"step {s_i} ({step}): {did}")
            tries.append(did)
            print(f"{s_i}. {step} → {did} · {time.time() - t0:.2f}s" + (f"  [{move}]" if "--why" in args else ""))
            if len(tries) >= 3 and len(set(tries[-3:])) == 1:
                return f"Stopped: step {s_i} did the same thing three times ({did}), so it isn't working"
            time.sleep(0.3)  # let the app react before the next look
    print(f"done: {len(plan(task))} steps in {moves} moves")
