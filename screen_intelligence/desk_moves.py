"""Move brain for desk do: a step that worked once is done again from memory, with no Jev call (~1.2s saved a step).

  short-term  this run only, in memory: a step that repeats inside one task ("click Next" five times). Also keeps
              spots Jev pointed at, but only while the window title is the same.
  long-term   runtime/move-brain.json, across tasks: "click the Wikipedia search field" on wikipedia.org learnt in
              one task is replayed in the next. Only labelled clicks and keys (screen spots move between pages).

A move is found again by the element's role + label (not its position), so it survives layout changes. A replay
that misses (element gone, click changes nothing) counts as a fail and Jev takes over; a move that fails more
than it works is forgotten. Risky labels are never replayed: those always go past Jev's risk check.
"""
import json
import re
from urllib.parse import urlparse

from . import RUNTIME, desk

LONG = RUNTIME / "move-brain.json"
_short = {}  # key -> move, for this process (one desk do run)


def norm(step):
    """'Click the Wikipedia search field.' and 'click Wikipedia search field' are the same step."""
    words = re.sub(r"[^\w\s#]", " ", step.lower()).split()
    return " ".join(w for w in words if w not in ("the", "a", "an", "please"))


def place(app):
    """Where a move holds: the site for a browser (moves on wikipedia.org hold on every Wikipedia page), else the app."""
    if app == "Safari":
        from .desk_do import safari_url

        host = urlparse(safari_url()).hostname or ""
        return f"Safari {host.removeprefix('www.')}"
    return app


def key(app, step):
    return f"{place(app)} | {norm(step)}"


def _load():
    try:
        return json.loads(LONG.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def _save(brain):
    LONG.parent.mkdir(exist_ok=True)
    LONG.write_text(json.dumps(brain, indent=1, ensure_ascii=False))


def learn(k, move):
    """A move that did a step on its own (one move, no retries). Points stay short-term only."""
    _short[k] = move
    if move[0] == "point":
        return
    brain = _load()
    row = brain.get(k)
    if row and row["move"] == list(move):
        row["hits"] += 1
    else:
        brain[k] = {"move": list(move), "hits": 1, "fails": 0}
    _save(brain)


def fail(k):
    _short.pop(k, None)
    brain = _load()
    if k in brain:
        brain[k]["fails"] += 1
        if brain[k]["fails"] > brain[k]["hits"]:
            del brain[k]
        _save(brain)


def recall(k, title):
    """('short' | 'long', move) or None."""
    move = _short.get(k)
    if move and (move[0] != "point" or move[3] == title):
        return "short", move
    row = _load().get(k)
    if row and row["hits"] > row["fails"]:
        return "long", tuple(row["move"])
    return None


def replay(k, title, found, screen_w, screen_h, allow_risky=False):
    """Do a remembered move. Returns what was done, or None (nothing remembered, or it missed and Jev should look)."""
    from .desk_senses import RISKY

    got = recall(k, title)
    if not got:
        return None
    which, move = got
    if move[0] == "key":
        if move[1] in ("return", "enter") and not allow_risky:
            return None  # return can submit: Jev's risk check sees it first, as in desk do
        desk.do("key", [move[1]])
        return f"pressed {move[1]} (from {which}-term memory)"
    if move[0] == "point":
        changed = desk.click(move[1] * screen_w, move[2] * screen_h, "left")
        did = f"clicked the same spot as before (from {which}-term memory)"
    else:
        _, role, text = move
        if RISKY.search(text):
            return None
        e = next((e for e in found if e["role"] == role and e["text"] == text
                  and 0 <= e["x"] < screen_w and 0 <= e["y"] < screen_h), None)
        if not e:
            fail(k)
            return None
        changed = desk.click(e["x"], e["y"], "left")
        did = f"clicked the {role} '{text}' (from {which}-term memory)"
    if not changed:
        fail(k)
        return None
    learn(k, move)
    return did
