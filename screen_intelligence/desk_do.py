"""desk do: Jev drives. Each step it sees the screen, the goal, what's been done, and the window's labelled elements,
and picks one move: click a labelled element, click a spot it points at, press a shortcut, type a text it was given,
or stop. Jev chooses and points; it doesn't write, so text to type goes in the step in double quotes
(then type "hello") or with --type.

  desk do "Click Save, then Share" [--app Safari] [--type "text"]... [--steps 15] [--allow-risky]

It stops by itself when Jev judges the goal done, when the next move looks like sending, submitting, deleting or
paying (those go back to Claude/Zac), when it repeats itself, or after --steps.
"""
import json
import re
import subprocess
import time
from pathlib import Path

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
    actions.update({f"type {i}": f"Type this text at the cursor: {t}" for i, t in enumerate(texts)})  # texts = --type + quoted
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
    loses track of order when handed the whole task (it clicked the last button first). Quoted text isn't split."""
    parts, buf, quote = [], "", False
    for piece in re.split(r'("[^"]*"|“[^”]*”)', task):
        if piece[:1] in ('"', "“"):
            buf += piece
            continue
        bits = re.split(r",?\s*\bthen\b\s*|;\s*", piece, flags=re.I)
        buf += bits[0]
        for b in bits[1:]:
            parts, buf = parts + [buf], b
    return [p.strip(" ,.") for p in parts + [buf] if p.strip(" ,.")]


def quoted(step):
    """Text in double quotes inside a step is text to type: then type "weather in Kingston". Jev chooses and points
    but doesn't write, so this is how a step carries its words. Single quotes are left alone (don't, it's)."""
    return [m[0] or m[1] for m in re.findall(r'"([^"]+)"|“([^”]+)”', step)]


def picker_open():
    """Is a file picker up? Safari shows it as a sheet on its window (or, elsewhere, as a separate Open panel), so
    look for an AXSheet / an "Open" dialog rather than for buttons a web page could also have."""
    from ApplicationServices import AXUIElementCreateApplication

    app = AXUIElementCreateApplication(ax.front_app().processIdentifier())
    for window in ax.attr(app, "AXWindows") or []:
        if ax.attr(window, "AXSubrole") == "AXDialog" and (ax.attr(window, "AXTitle") or "") in ("Open", "Choose File"):
            return True
        if any(ax.attr(c, "AXRole") == "AXSheet" for c in ax.attr(window, "AXChildren") or []):
            return True
    return False


def attach(path):
    """Attach a file: open the page's file picker if it isn't up (Jev finds the Choose File/Browse button), then
    Go to Folder with the full path. Safari only opens a picker after a real click on the page, so the first try
    can fail; it says so and Zac clicks once."""
    from pathlib import Path

    if not Path(path).expanduser().exists():
        return None, f"no such file: {path}"
    if not picker_open():
        # Safari lists a file input as a button: "Choose File", or "no file selected" next to it
        _, _, found = ax.elements(ax.front_app().localizedName())
        button = next((e for e in found if e["role"] == "button"
                       and re.search(r"choose file|browse|no file selected|upload a file", e["text"], re.I)), None)
        if button:
            desk.click(button["x"], button["y"], "left")
        elif desk.find("the Choose File or Browse button for uploading a file"):
            return None, "couldn't find the Choose File button"
        else:
            desk.click(*desk.point(["@"])[0], "left")
        for _ in range(20):
            if picker_open():
                break
            time.sleep(0.1)
        else:
            return None, "the file picker didn't open (Safari wants one real click on Choose File first)"
    desk.do("key", ["cmd+shift+g"])
    time.sleep(0.6)
    desk.paste(str(Path(path).expanduser()))
    time.sleep(0.3)
    desk.do("key", ["return"])
    time.sleep(0.8)
    desk.do("key", ["return"])
    for _ in range(20):
        if not picker_open():
            return f"attached {Path(path).name}", None
        time.sleep(0.1)
    return None, "the file picker is still open; the path may be wrong"


def direct(step, allow_risky=True):
    """Steps that need no judgment run without asking Jev: type "text", press <key>, choose "Option" (in an open
    dropdown), attach "/path/file". Returns what was done, or None. A failed attach/choose raises StepFailed."""
    m = re.fullmatch(r'open\s+"(https?://[^"]+)"', step.strip(), re.I)
    if m:  # go to a page in the app's front window, then give it a moment to load
        subprocess.run(["osascript", "-e", f'tell application "Safari" to set URL of current tab of front window to "{m.group(1)}"'])
        time.sleep(2.5)
        return f"opened {m.group(1)}"
    m = re.fullmatch(r'attach\s+(?:the\s+file\s+)?"([^"]+)"', step.strip(), re.I)
    if m:
        did, problem = attach(m.group(1))
        if problem:
            raise StepFailed(problem)
        return did
    m = re.fullmatch(r'(?:choose|pick|select)\s+"([^"]+)"(?:\s+in\s+.*)?', step.strip(), re.I)
    if m:  # an open native dropdown jumps to the item you type; return picks it
        desk.do("type", ["--keys", m.group(1)])
        time.sleep(0.2)
        desk.do("key", ["return"])
        return f"chose {m.group(1)!r}"
    m = re.fullmatch(r'type\s+(?:"([^"]*)"|“([^”]*)”)', step.strip(), re.I)
    if m:
        desk.natural_type(m.group(1) if m.group(1) is not None else m.group(2))
        return f"typed {m.group(1) or m.group(2)!r}"
    m = re.fullmatch(r"(?:press|hit)\s+(?:the\s+)?([\w+]+)(?:\s+key)?", step.strip(), re.I)
    if m:
        key = desk.KEYS.get(m.group(1).lower(), m.group(1).lower())
        if key in ("return", "enter") and not allow_risky:
            return None  # return can submit a form: let Jev's risk check see it first
        if all(k in pyautogui.KEYBOARD_KEYS or k == "cmd" for k in key.split("+")):
            desk.do("key", [key])
            return f"pressed {key}"
    return None


def log_step(step, move, did, elements, title):
    """Every Jev-decided move, for later: enough runs of (step, screen elements, move, result) can teach a picker
    or become replayable recipes. Stays local (runtime/ is gitignored)."""
    with (RUNTIME / "do-log.jsonl").open("a") as f:
        f.write(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M:%S"), "window": title, "step": step, "move": move,
                            "did": did, "elements": len(elements)}, ensure_ascii=False) + "\n")


class StepFailed(Exception):
    pass


def report(app_name, screen_h):
    """What's on screen now, as ~20 lines of text, so the next "now what" needs no screenshot: the window title,
    headings, messages (errors, missing, submitted...), fields and the page's buttons and links."""
    _, title, found = ax.elements(app_name)
    page = [e for e in found if e["y"] > 90]  # below the browser's tab and tool bars
    words = re.compile(r"error|required|missing|invalid|success|submitted|thank|attention|warning|failed|uploaded", re.I)
    lines = [f"now: {title}"]
    lines += [f"  # {e['text']}" for e in page if e["role"] == "heading"][:5]
    lines += [f"  ! {e['text']}" for e in page if e["role"] == "text" and words.search(e["text"])][:6]
    lines += [f"  [{e['role']}] {e['text']}" for e in page if e["role"] in ("field", "textarea", "popup", "combo", "checkbox", "radio")][:8]
    actions = [e["text"] for e in page if e["role"] in ("button", "link") and e["text"]]
    if actions:
        lines.append("  buttons/links: " + " · ".join(dict.fromkeys(actions[-14:])))
    print("\n".join(lines))


def look(app_name, screen_w):
    """Screenshot and the window's labelled elements, read at the same time (~0.2s instead of ~0.4s one after the other)."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(2) as pool:
        shot, tree = pool.submit(pyautogui.screenshot), pool.submit(ax.elements, app_name)
        full = shot.result()
        full.resize((desk.MAX_SIDE, round(full.height * desk.MAX_SIDE / full.width))).save(RUNTIME / "do.png")
        return full, tree.result()


def pick(answer):
    """Jev's chosen move, but not a timid `stuck`: when it's under 60% sure, take the best real move instead."""
    probs = answer["probabilities"]
    if answer["choice"] == "stuck" and probs.get("stuck", 1) < 0.6:
        return max((m for m in probs if m != "stuck"), key=probs.get, default="stuck")
    return answer["choice"]


RECIPES = Path(__file__).resolve().parent.parent / "recipes"


def recipe(args):
    """desk recipe list | show NAME | NAME key=value...: a saved plan (one step per line, # comments, {blanks}),
    filled in and run with desk do. Built from a flow that worked once, so repeats need no decisions."""
    if not args or args[0] == "list":
        for f in sorted(RECIPES.glob("*.txt")):
            print(f"{f.stem:16} {next((l[2:] for l in f.read_text().splitlines() if l.startswith('# vars:')), '')}")
        return None
    if args[0] == "show":
        print((RECIPES / f"{args[1]}.txt").read_text())
        return None
    path = RECIPES / f"{args[0]}.txt"
    if not path.exists():
        return f"no recipe {args[0]!r}; `desk recipe list`"
    values = dict(a.split("=", 1) for a in args[1:] if "=" in a and not a.startswith("--"))
    steps = [l.strip() for l in path.read_text().splitlines() if l.strip() and not l.startswith("#")]
    missing = sorted({v for l in steps for v in re.findall(r"{(\w+)}", l)} - values.keys())
    if missing:
        return f"recipe {args[0]} needs: " + ", ".join(f"{m}=..." for m in missing)
    plan = "; ".join(re.sub(r"{(\w+)}", lambda m: values[m.group(1)], l) for l in steps)
    extra = [a for a in args[1:] if a.startswith("--")]
    if re.search(r"^# allow-risky", path.read_text(), re.M):  # a recipe with no final Submit/Send step in it
        extra.append("--allow-risky")
    return run([plan] + extra)


def run(args):
    """Run the plan, then always print what's on screen, so the caller's next move needs no screenshot."""
    problem = _run(args)
    if problem:
        print(problem)
    report((flags(args, "--app") or ["Safari"])[0], pyautogui.size()[1])
    return "stopped" if problem else None


def _run(args):
    task = next(a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or not args[i - 1].startswith("--")))
    app_name = (flags(args, "--app") or ["Safari"])[0]
    texts = flags(args, "--type")
    budget = int((flags(args, "--steps") or [15])[0])
    allow_risky = "--allow-risky" in args  # lets planned return/submit keys through; risky clicks still stop
    desk.do("open", [app_name])
    desk.jev_start()
    screen_w, screen_h = pyautogui.size()
    history, moves, left_at = [], 0, None
    for s_i, step in enumerate(plan(task), 1):
        tries = []
        t0 = time.time()
        try:
            did = ax.front_app().localizedName() == app_name and direct(step, allow_risky)
        except StepFailed as e:
            return f"Step {s_i} ({step}) failed: {e}"
        if did:
            moves += 1
            history.append(f"step {s_i} ({step}): {did}")
            print(f"{s_i}. {step} → {did} · {time.time() - t0:.2f}s (no look needed)")
            continue
        while True:
            if moves >= budget:
                return f"Ran out of moves ({budget}) on step {s_i}: {step}"
            now = pyautogui.position()
            if left_at and abs(now[0] - left_at[0]) + abs(now[1] - left_at[1]) > 3:
                return f"Stopped before step {s_i} ({step}): you moved the mouse, so it's yours"
            if ax.front_app().localizedName() != app_name:
                return f"Stopped before step {s_i} ({step}): {app_name} isn't in front any more (you switched apps?), so keys would go astray"
            t0, clicked, changed = time.time(), "", False
            full, (_, title, found) = look(app_name, screen_w)
            k = full.width / screen_w
            on_screen = [(i, e) for i, e in enumerate(found) if e["role"] in desk.CLICKABLE and e["text"]
                         and 0 <= e["x"] < screen_w and 0 <= e["y"] < screen_h][:MAX_ELEMENTS]
            elements = {f"#{i + 1}": f"{e['role']} {e['text']} ({where(e['x'], e['y'], screen_w, screen_h)})" for i, e in on_screen}
            typeable = texts + quoted(step)
            a = desk.jev("raw", json.dumps(step_spec(step, task, history, title, elements, typeable)), RUNTIME / "do.png")
            if tries and a["done"] >= DONE_AT:  # a step counts as done only after a move made for it
                break
            move = pick(a["action"])
            if move == "stuck":
                return f"Jev is stuck on step {s_i} ({step}): it needs a person, or nothing on screen does it"
            # --allow-risky only lets a planned return/submit key through; a risky-looking click always stops
            # (on an already-submitted posting the button near "Apply" is "Cancel Application")
            if a["risky"] >= RISKY_AT and (move.startswith("click") or (move == "key submit" and not allow_risky)):
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
                changed = desk.click(e["x"], e["y"], "left")
                did, clicked = f"clicked the {e['role']} '{e['text']}'", e["text"]
            elif move.startswith("click"):  # a spot Jev points at, sharpened on a close-up like desk find
                box = (b["left"] * full.width, b["top"] * full.height, b["right"] * full.width, b["bottom"] * full.height)
                better = desk.zoom(full, box, desk.CLOSE_UP, "what to click to " + step, 2)
                l, t, r, bt = better[0] if better else box
                x, y = (l + r) / 2 / k, (t + bt) / 2 / k
                changed = desk.click(x, y, "left")
                name = element_at(x, y)
                clicked = name.split("'")[1] if "'" in name else ""
                did = f"clicked the {name}" if name else f"clicked the spot at ({round(x)}, {round(y)}) ({where(x, y, screen_w, screen_h)})"
            elif move.startswith("key "):
                desk.do("key", [desk.KEYS[move[4:]]])
                did = f"pressed {desk.KEYS[move[4:]]} ({move[4:]})"
            else:  # type N
                desk.natural_type(typeable[int(move[5:])])
                did = f"typed {typeable[int(move[5:])]!r}"
            moves += 1
            history.append(f"step {s_i} ({step}): {did}")
            tries.append(did)
            log_step(step, move, did, elements, title)
            print(f"{s_i}. {step} → {did} · {time.time() - t0:.2f}s" + (f"  [{move}]" if "--why" in args else ""))
            if clicked and (clicked.lower() in step.lower() or (changed and step.lower().startswith("click"))):
                break  # a "click X" step whose click hit X by name or visibly did something: done (asking again clicked twice)
            if len(tries) >= 3 and len(set(tries[-3:])) == 1:
                return f"Stopped: step {s_i} did the same thing three times ({did}), so it isn't working"
            left_at = tuple(pyautogui.position())
            if not changed:
                time.sleep(0.15)  # a click already waited for the screen to change; keys and typing get a moment
    print(f"done: {len(plan(task))} steps in {moves} moves")
