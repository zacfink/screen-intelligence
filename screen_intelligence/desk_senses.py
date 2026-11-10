"""Senses and memory for desk do, the way a robot body feeds its brain: every step Jev gets a short summary of the
whole Mac, not only the screen, plus what it did and saw before. And a roam mode with no goal, where Jev looks
around by itself.

  sight    front app, window title, what's under the mouse      (the screenshot + elements still go in as before)
  hearing  what Music/Spotify is playing, output volume
  body     battery, how long since Zac last touched the keyboard/mouse, clipboard changed (never its contents)
  memory   runtime/senses-memory.jsonl: the last moves and windows, kept between runs

  desk do --roam [--steps 8]   Jev explores for a few moves: clicks buttons/links/tabs, scrolls, goes back, switches
                               between a few safe apps. It never types, skips risky labels, and stops if you move
                               the mouse. Only runs when started; there is no background mode.
"""
import json
import re
import subprocess
import time

import pyautogui

from . import RUNTIME, ax, desk

MEMORY = RUNTIME / "senses-memory.jsonl"
RECALL = 12  # memory lines handed to Jev each step; more crowds the choice
ROAM_MAX = 20  # hard cap on a roam, whatever --steps says
ROAM_APPS = ("Safari", "Finder", "Calendar")  # apps roam may switch to; opening them changes nothing
ROAM_ROLES = {"button", "link", "tab"}  # no fields (it can't type), checkboxes, popups (those change settings)
RISKY = re.compile(r"send|submit|post|delete|remove|trash|erase|buy|pay|purchase|checkout|order|sign ?out|log ?out"
                   r"|apply|cancel|quit|install|update|upgrade|allow|accept|confirm|agree|subscribe|follow|reply|share"
                   r"|save|upload|download|close|eject|restart|shut ?down|reset|clear|empty|block|report", re.I)


def osa(script):
    """One AppleScript answer, or "" if the app is slow (an open menu makes Apple Events wait up to two minutes)."""
    try:
        return subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=1).stdout.strip()
    except subprocess.TimeoutExpired:
        return ""


def playing():
    """Hearing: the track Music or Spotify is playing. `if running` first, so asking never launches the app."""
    for app in ("Spotify", "Music"):
        out = osa(f'if application "{app}" is running then tell application "{app}" to if player state is playing '
                  f'then return (name of current track) & " by " & (artist of current track)')
        if out:
            return f"{out} ({app})"
    return "nothing"


def idle_seconds():
    """Seconds since the keyboard or mouse was last touched, from IOKit's HIDIdleTime (nanoseconds)."""
    out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"], capture_output=True, text=True).stdout
    m = re.search(r'"HIDIdleTime" = (\d+)', out)
    return int(m.group(1)) // 1_000_000_000 if m else None


def battery():
    m = re.search(r"(\d+)%; ([\w ]+)", subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout)
    return f"{m.group(1)}% {m.group(2)}" if m else "no battery"


_clip = {"count": None}


def clipboard():
    """Only whether it changed since the last look and how long it is: what Zac copied stays private."""
    from AppKit import NSPasteboard, NSPasteboardTypeString

    board = NSPasteboard.generalPasteboard()
    count, before = board.changeCount(), _clip["count"]
    _clip["count"] = count
    if before is None or count == before:
        return "unchanged"
    return f"changed ({len(board.stringForType_(NSPasteboardTypeString) or '')} characters)"


def sense(title=""):
    """The whole body in a few short lines, for Jev's state. Each sense is cheap (~0.1s together)."""
    from .desk_do import element_at

    x, y = pyautogui.position()
    idle = idle_seconds()
    return {"front_app": ax.front_app().localizedName(), "window": title, "time": time.strftime("%a %H:%M"),
            "under_mouse": element_at(x, y) or "nothing labelled", "hearing": playing(),
            "volume": osa("output volume of (get volume settings)") + "%", "battery": battery(),
            "zac_last_touched": f"{idle}s ago" if idle is not None else "unknown", "clipboard": clipboard()}


def remember(mode, window, did):
    MEMORY.parent.mkdir(exist_ok=True)
    with MEMORY.open("a") as f:
        f.write(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M"), "mode": mode, "window": window, "did": did},
                           ensure_ascii=False) + "\n")


def recall(n=RECALL):
    """The last n memories as lines like '11-10 18:02 in "Inbox": clicked the link News'."""
    if not MEMORY.exists():
        return ["nothing yet"]
    rows = [json.loads(l) for l in MEMORY.read_text().splitlines()[-n:] if l.strip()]
    return [f"{r['when'][5:]} in {r['window']!r}: {r['did']}" for r in rows] or ["nothing yet"]


def roam_moves(found, w, h, front):
    """The menu for one roam step: safe labelled elements on screen, plus scroll/back/switch. Risky labels never
    get on the menu at all, so no confidence threshold can let one through."""
    from .desk_do import where

    on_screen = [e for e in found if e["role"] in ROAM_ROLES and e["text"] and not RISKY.search(e["text"])
                 and 0 <= e["x"] < w and 90 <= e["y"] < h][:40]  # y >= 90: below the menu bar and browser chrome
    elements = {f"#{i + 1}": f"{e['role']} {e['text']} ({where(e['x'], e['y'], w, h)})" for i, e in enumerate(on_screen)}
    moves = {"scroll down": "Scroll down to see more of this window.", "scroll up": "Scroll back up.",
             "back": "Go back to the previous page (Safari only).",
             "stop": "Nothing here is new or worth looking at; end the roam."}
    if elements:
        moves["click"] = "Click one of `elements` to see what it opens."
    moves.update({f"switch {a}": f"Switch to the {a} app." for a in ROAM_APPS if a != front})
    return on_screen, elements, moves


def roam(args):
    """desk do --roam: no goal. Each step Jev gets the senses, its memory and the screen, and picks the move most
    likely to show it something it hasn't seen. A second Jev check vets any click before it happens."""
    from .desk_do import flags, look, report

    budget = min(int((flags(args, "--steps") or [8])[0]), ROAM_MAX)
    w, h = pyautogui.size()
    desk.stop_requested()
    desk.jev_start()
    desk.status("running", "Roaming", "Looking around", 0, budget)
    problem, left_at, done = None, None, []
    for n in range(1, budget + 1):
        if desk.stop_requested():
            problem = "Stopped: you chose Stop in the menu bar"
            break
        now = pyautogui.position()
        if left_at and abs(now[0] - left_at[0]) + abs(now[1] - left_at[1]) > 3:
            problem = "Stopped: you moved the mouse, so it's yours"
            break
        front = ax.front_app().localizedName()
        _, (_, title, found) = look(front, w)
        on_screen, elements, moves = roam_moves(found, w, h, front)
        if len(done) >= 2 and all(d.startswith("scroll") for d in done[-2:]):
            # Jev picks the safe scroll every time (4/4 on the first demo) even with memory saying so: force a change
            moves = {k: v for k, v in moves.items() if not k.startswith("scroll")}
        state = {"senses": sense(title), "memory": recall(), "elements": elements}
        questions = {"move": {"type": "choice", "criteria": moves, "instructions":
                              "You are a curious explorer living in this Mac, with `senses` as your body and `memory` "
                              "as what you did before. Pick the move most likely to show you something you haven't "
                              "seen yet. Don't repeat what `memory` already shows."}}
        if elements:
            questions["element"] = {"type": "choice", "criteria": elements,
                                    "instructions": "Which element in `elements` would show something new and interesting?"}
        a = desk.jev("raw", json.dumps({"state": state, "questions": questions}), RUNTIME / "do.png")
        move = a["move"]["choice"]
        if move == "stop":
            problem = f"Jev chose to stop after {n - 1} moves: nothing new here"
            break
        if move == "click":
            e = on_screen[int(a["element"]["choice"][1:]) - 1]
            vet = desk.jev("raw", json.dumps({"state": {"senses": state["senses"], "element": f"{e['role']} {e['text']}"},
                                              "questions": {"risky": {"type": "noul", "instructions":
                                                  "Would clicking `element` send, post, delete, buy, pay for, or change "
                                                  "something, rather than just show something?"}}}), RUNTIME / "do.png")
            if vet["risky"] >= 0.3:  # stricter than desk do's 0.5: with no goal there's no reason to take the chance
                did = f"skipped the {e['role']} '{e['text']}' (looked risky, {vet['risky']:.2f})"
            else:
                desk.click(e["x"], e["y"], "left")
                did = f"clicked the {e['role']} '{e['text']}'"
        elif move.startswith("scroll"):
            pyautogui.moveTo(w // 2, h // 2)  # scroll goes to what's under the cursor, so put it on the window
            desk.do("scroll", [move.split()[1], "5"])
            did = move
        elif move == "back":
            desk.do("key", ["cmd+["])
            did = "went back"
        else:
            desk.do("open", [move.split(" ", 1)[1]])
            did = f"switched to {move.split(' ', 1)[1]}"
        remember("roam", title, did)
        done.append(did)
        desk.status("running", None, did, n, budget)
        print(f"{n}. {did}  · in {front}: {title[:50]}")
        left_at = tuple(pyautogui.position())
        time.sleep(0.4)  # let what it opened draw before the next look
    desk.status("stopped" if problem else "done", "Roaming", problem or f"Roamed {budget} moves")
    print(problem or f"done: roamed {budget} moves")
    report(ax.front_app().localizedName(), h)
    return "stopped" if problem else None
