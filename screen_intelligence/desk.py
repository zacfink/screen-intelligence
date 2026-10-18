"""desk: let Claude drive the Mac. Claude is the vision model and planner; this only sees and acts.

  Look (cheapest first):
    desk ui [--find TEXT] [--all] [--full] [App]   front window's buttons, fields and labels as numbered lines
                              (first 80 unless --all; --find keeps lines containing TEXT)
    desk shot                 screenshot -> runtime/desk.png (1280 wide, grid every 100px), prints its path
    desk see "Is there an error dialog?"   Jev answers yes/no about the screen (probability); no screenshot to read
    desk find "the blue Submit button"     Jev finds it on screen (two passes: whole screen, then a close-up crop),
                              prints its centre in screenshot pixels; then `click @` clicks it. For apps `ui` can't read.
    desk highlight "the Wi-Fi icon"        find it, then open the screenshot in Preview with a red box around it
  Act:
    desk click #N             click element N from the last `ui`
    desk click @              click what the last `find` found
    desk click X Y [right|double]   click at (X, Y) in the last screenshot's pixels
    desk drag X1 Y1 X2 Y2     press, move slowly, release (screenshot pixels)
    desk move X Y | #N        put the cursor there without clicking (scroll goes to whatever is under it)
    desk type "text"          paste text at the cursor (keeps your clipboard)
    desk type --keys "text"   real keystrokes, for menus and anything that ignores paste
    desk type --natural "text"   types like a person, one key at a time with human rhythm (~100 wpm)
    desk key cmd+l            a key or a combo (pyautogui key names joined by +)
    desk scroll up|down|left|right N
    desk open "App Name"      open or switch to an app
    desk wait SECONDS
  Hand off:
    desk until TEXT[|TEXT2] [App] [--gone] [--timeout S]   wait until a label containing TEXT appears (or, with
                              --gone, disappears), e.g. while Zac logs in. Checks every 2s, gives up after S (300).
  Map:
    desk map [App]            the moves available right now, as JSON: the fixed keyboard map plus a mouse map of
                              this screen's clickable elements (same #N numbers as `ui`, so `click #N` works after it)
  Jev drives:
    desk do "goal" [--app Safari] [--type "text"]... [--steps 15]   Jev picks each move from the screen, the goal and
                              what's been done; stops when done, stuck, repeating, or before anything risky
  Demo:
    desk demo [jev|ui] [N]    a test page of buttons in random spots; find + click each, the page scores hits and times
  Check:
    desk expect TEXT[|TEXT2] [App] [--timeout S]   stop unless a label containing TEXT shows up within S (3)
  Batch:
    desk run "click #4; expect 'First name'; type Ada; key tab; type Lovelace; ui --find Submit"
                              Every click waits for the screen to change. If it doesn't (a missed click, a form
                              that never opened), the batch stops there and says which step. Move the mouse
                              yourself and the batch finishes the step it's on, then stops.
"""
import json
import shlex
from pathlib import Path
import subprocess
import sys
import time

import pyautogui

from . import RUNTIME

WIDTH = 1280  # small enough that the image reaches Claude unshrunk, so its coordinates are exact
GRID = 100
SHOT = RUNTIME / "desk.png"
SCALE = RUNTIME / "desk-scale.json"  # screen points per screenshot pixel, from the last shot
UI = RUNTIME / "desk-ui.json"  # element centres (screen points) from the last `ui`
FOUND = RUNTIME / "desk-found.json"  # centre (screen points) of what the last `find` found
JEV_PYTHON = Path.home() / ".venvs/typesafe/bin/python"  # the TypeSafe SDK lives there, not in this Python
JEV_LOOK = Path(__file__).with_name("jev_look.py")
CLOSE_UP = 560  # native pixels on each side of the second-pass crop: Jev answers in 0.01 steps, ~6px here vs ~13 on the whole screen
MIN_CONFIDENCE = 0.6  # demo 2026-10-17: 35/36 hits, all >= 0.71; the one miss was 0.51
MAX_SIDE = 1568  # Jev rejects images over 1568px (or under 280) on a side
# The keyboard map: a small, fixed set of shortcuts that work across most Mac apps. Nothing destructive (no quit,
# delete or send) — those stay with Claude.
KEYS = {
    "address bar": "cmd+l", "new tab": "cmd+t", "close tab": "cmd+w", "back": "cmd+[", "forward": "cmd+]",
    "reload": "cmd+r", "find": "cmd+f", "submit": "return", "cancel": "escape", "next field": "tab",
    "previous field": "shift+tab", "select all": "cmd+a", "copy": "cmd+c", "paste": "cmd+v", "undo": "cmd+z",
    "page down": "pagedown", "page up": "pageup", "top": "cmd+up", "bottom": "cmd+down", "switch app": "cmd+tab",
}
CLICKABLE = {"button", "link", "field", "textarea", "search", "checkbox", "radio", "popup", "combo", "menu", "tab",
             "slider", "item"}
UI_LINES = 80  # a dense page lists hundreds; past this a screenshot is cheaper
CHANGE_WAIT = 1.5  # seconds a click gets to visibly change the screen
CHANGED_PIXELS = 40  # pixels (640-wide grey frame) that must differ; a blinking text caret is ~15, an opened form thousands


def to_screen(x, y, scale):
    return round(x * scale), round(y * scale)


def load(path, what):
    if not path.exists():
        sys.exit(f"Run `desk {what}` first.")
    return json.loads(path.read_text())


def point(args):
    """#N -> centre of element N from the last ui; @ -> what the last find found; X Y -> screenshot pixels."""
    if args[0] == "@":
        return tuple(load(FOUND, "find")), args[1:]
    if args[0].startswith("#"):
        from .ax import bring_to_front

        last = load(UI, "ui")
        bring_to_front(last["pid"])
        e = last["elements"][int(args[0][1:]) - 1]
        return (e["x"], e["y"]), args[1:]
    return to_screen(float(args[0]), float(args[1]), load(SCALE, "shot")), args[2:]


def window_at(x, y):
    """Bounds (screen points) of the topmost app window under (x, y), or None (desktop, Dock, menu bar)."""
    import Quartz

    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    for w in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID):  # front to back
        b = w["kCGWindowBounds"]
        if w.get("kCGWindowLayer") == 0 and b["X"] <= x < b["X"] + b["Width"] and b["Y"] <= y < b["Y"] + b["Height"]:
            return b
    return None


def frame(bounds=None):
    """A small grey screenshot for change checks. Only the clicked window counts, so a busy terminal next to it
    doesn't look like a change; with no window, the whole screen minus the menu bar (clock, status icons)."""
    image = pyautogui.screenshot().convert("L")
    if bounds:
        k = image.width / pyautogui.size()[0]  # screenshot pixels per screen point
        image = image.crop(tuple(round(v * k) for v in (bounds["X"], bounds["Y"], bounds["X"] + bounds["Width"], bounds["Y"] + bounds["Height"])))
    else:
        image.paste(0, (0, 0, image.width, round(image.height * 0.04)))
    return image.resize((640, max(1, round(image.height * 640 / image.width))))


def changed(before, after):
    from PIL import ImageChops

    diff = ImageChops.difference(before, after).point(lambda v: 255 if v > 24 else 0)
    return diff.histogram()[255] >= CHANGED_PIXELS


def glide(x, y):
    """Move the mouse like a hand would: ease in and out, longer for longer trips (0.12-0.4s). The target is fixed
    before it starts, so this is only how it looks."""
    cx, cy = pyautogui.position()
    distance = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
    pyautogui.moveTo(x, y, duration=min(0.4, 0.12 + distance / 4000), tween=pyautogui.easeInOutQuad)


def click(x, y, kind):
    """Click, then report whether the screen changed. The mouse moves first so hover effects don't count."""
    glide(x, y)
    time.sleep(0.05)
    bounds = window_at(x, y)
    before = frame(bounds)
    if kind == "double":
        pyautogui.doubleClick(x, y)
    else:
        pyautogui.click(x, y, button=kind)
    deadline = time.time() + CHANGE_WAIT
    while time.time() < deadline:
        time.sleep(0.03)
        if changed(before, frame(bounds)):
            return True
    return False


def paste(text):
    # typing drops Shift now and then (":" came out as ";"), so text goes through the clipboard
    old = subprocess.run(["pbpaste"], capture_output=True).stdout
    subprocess.run(["pbcopy"], input=text.encode())
    pyautogui.hotkey("command", "v")
    time.sleep(0.2)  # let the app read the clipboard before it's restored
    subprocess.run(["pbcopy"], input=old)


def natural_type(text, wpm=None):
    """Type like a person at a keyboard: one character at a time, ~90-120 wpm with uneven gaps and short pauses after
    spaces and punctuation. Each character goes in as a Unicode key event, so capitals, ":" and emoji come out right
    (pyautogui's per-key typing sometimes dropped Shift)."""
    import random

    import Quartz

    gap = 60 / ((wpm or random.uniform(90, 120)) * 5)  # seconds per character at that speed (a word is 5 characters)
    for ch in text:
        for down in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(None, 0, down)
            Quartz.CGEventKeyboardSetUnicodeString(event, len(ch.encode("utf-16-le")) // 2, ch)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            time.sleep(random.uniform(0.008, 0.02) if down else 0)  # key held a moment
        pause = gap * random.uniform(0.5, 1.5)
        if ch in " ,.;:!?\n":
            pause += random.uniform(0.02, 0.1)
        time.sleep(pause)


def split_batch(text):
    """Split on ; outside quotes, keeping each step's raw text (quotes included)."""
    out, cur, quote = [], "", None
    for ch in text:
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == ";":
            out, cur = out + [cur], ""
            continue
        cur += ch
    return [c.strip() for c in out + [cur] if c.strip()]


def steps(text):
    """Split a batch into steps. `type` keeps its text exactly as written (quotes, brackets, &&), minus one pair of
    wrapping quotes, so shell commands survive. Other steps are split like a shell. # isn't a comment: #N is element N."""
    out = []
    for raw in split_batch(text):
        word, _, rest = raw.partition(" ")
        if word == "type":
            keys = rest.startswith("--keys ")
            rest = rest[7:].strip() if keys else rest.strip()
            if len(rest) > 1 and rest[0] == rest[-1] and rest[0] in "'\"":
                rest = rest[1:-1]
            out.append(["type"] + (["--keys"] if keys else []) + ([rest] if rest else []))
        else:
            lex = shlex.shlex(raw, posix=True)
            lex.whitespace_split, lex.commenters = True, ""
            out.append(list(lex))
    return out


def shot():
    from PIL import Image, ImageDraw

    RUNTIME.mkdir(exist_ok=True)
    screen_w, _ = pyautogui.size()
    image = pyautogui.screenshot()
    image = image.resize((WIDTH, round(image.height * WIDTH / image.width)))
    grid = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(grid)
    for x in range(GRID, image.width, GRID):
        draw.line([(x, 0), (x, image.height)], fill=(255, 0, 255, 70))
        draw.text((x + 2, 2), str(x), fill=(255, 0, 255, 255))
    for y in range(GRID, image.height, GRID):
        draw.line([(0, y), (image.width, y)], fill=(255, 0, 255, 70))
        draw.text((2, y + 2), str(y), fill=(255, 0, 255, 255))
    image = Image.alpha_composite(image.convert("RGBA"), grid).convert("RGB")
    mx, my = pyautogui.position()
    scale = screen_w / WIDTH
    cx, cy = mx / scale, my / scale
    ImageDraw.Draw(image).ellipse((cx - 6, cy - 6, cx + 6, cy + 6), outline=(255, 0, 0), width=2)
    image.save(SHOT)
    SCALE.write_text(json.dumps(scale))
    print(SHOT)


_jev_worker = None


def jev_start():
    """Start the worker if it isn't running. find/see call this before the screenshot so the two overlap."""
    global _jev_worker
    if _jev_worker is None or _jev_worker.poll() is not None:
        _jev_worker = subprocess.Popen([str(JEV_PYTHON), "-I", str(JEV_LOOK), "serve"], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def jev(mode, text, image):
    """One Jev question about an image, via a worker in the TypeSafe venv that stays up for this desk process, so
    starting Python and opening the connection (~0.35s) is paid once, not per question. Returns its JSON answer."""
    jev_start()
    _jev_worker.stdin.write(json.dumps([mode, text, str(image)]) + "\n")
    _jev_worker.stdin.flush()
    line = _jev_worker.stdout.readline()
    if not line:
        sys.exit(f"Jev failed: {(_jev_worker.stderr.read().strip().splitlines() or ['worker exited'])[-1]}")
    out = json.loads(line)
    if "error" in out:
        sys.exit(f"Jev failed: {out['error']}")
    return out


def fit(image):
    """Shrink an image so neither side is over MAX_SIDE (Jev's limit)."""
    k = min(1, MAX_SIDE / max(image.size))
    return image if k == 1 else image.resize((round(image.width * k), round(image.height * k)))


def zoom(full, box, side, text, n):
    """Ask again on a crop of at least side x side native pixels around box (shifted, not shrunk, at screen edges).
    Returns the finer box and Jev's answer, or None when the crop no longer shows the target."""
    W, H = full.size
    l, t, r, b = box
    w, h = min(W, max((r - l) * 1.6, side)), min(H, max((b - t) * 1.6, side))
    x0 = round(min(max(0, (l + r) / 2 - w / 2), W - w))
    y0 = round(min(max(0, (t + b) / 2 - h / 2), H - h))
    x1, y1 = round(x0 + w), round(y0 + h)
    fit(full.crop((x0, y0, x1, y1))).save(RUNTIME / f"jev-{n}.png")
    a = jev("box", text, RUNTIME / f"jev-{n}.png")
    if a["visible"] < 0.5:
        return None
    e = a["box"]
    return (x0 + e["left"] * (x1 - x0), y0 + e["top"] * (y1 - y0), x0 + e["right"] * (x1 - x0), y0 + e["bottom"] * (y1 - y0)), a


def find_box(full, text):
    """Where `text` is in a full-resolution screenshot, as a native-pixel box, plus Jev's answer. Pass 1 looks at the
    whole screen at Jev's largest size (1568 wide); pass 2 asks again on a close-up around that box, about twice as
    exact. A tighter pass 3 was tried for icons and didn't help: icon misses are mix-ups in pass 1 (the gear for the
    star), which zooming can't fix, and they come with low confidence."""
    RUNTIME.mkdir(exist_ok=True)
    W, H = full.size
    full.resize((MAX_SIDE, round(H * MAX_SIDE / W))).save(RUNTIME / "jev-1.png")
    a = jev("box", text, RUNTIME / "jev-1.png")
    b = a["box"]
    box = (b["left"] * W, b["top"] * H, b["right"] * W, b["bottom"] * H)
    better = zoom(full, box, CLOSE_UP, text, 2)
    if better:  # the close-up still shows it, so trust its finer box
        box, a = better[0], {**better[1], "visible": max(a["visible"], better[1]["visible"])}
    l, t, r, bt = box
    return (l, t, r, bt), a


def find(text, show=False):
    jev_start()
    screen_w, _ = pyautogui.size()
    full = pyautogui.screenshot()
    k = full.width / screen_w  # native pixels per screen point (2 on Retina)
    (l, t, r, b), a = find_box(full, text)
    if show:
        highlight(full, (l, t, r, b), f"{text} · {a['confidence']:.2f}")
    x, y = (l + r) / 2 / k, (t + b) / 2 / k  # screen points
    scale = screen_w / WIDTH
    SCALE.write_text(json.dumps(scale))  # so `click X Y` with the printed pixels lands here too
    FOUND.write_text(json.dumps([round(x), round(y)]))
    (RUNTIME / "desk-found-conf.json").write_text(json.dumps(a["confidence"]))
    print(f"found at {round(x / scale)} {round(y / scale)} (screenshot px) · confidence {a['confidence']:.2f} · visible {a['visible']:.2f}")
    if a["visible"] < 0.5:
        return f"Jev doesn't think {text!r} is on screen (visible {a['visible']:.2f}); the box is a guess"
    if a["confidence"] < MIN_CONFIDENCE:
        return f"Jev isn't sure (confidence {a['confidence']:.2f}); check with `desk shot` before clicking"


def highlight(full, box, caption):
    """Save the screenshot with a red box around `box` (native pixels) and open it in Preview."""
    from PIL import ImageDraw

    image = full.convert("RGB")
    draw, pad, w = ImageDraw.Draw(image), 8, max(4, image.width // 600)
    l, t, r, b = box
    draw.rectangle((l - pad, t - pad, r + pad, b + pad), outline=(255, 40, 40), width=w)
    draw.text((l - pad, max(0, t - pad - 30)), caption, fill=(255, 40, 40), font_size=max(16, image.width // 90))
    out = RUNTIME / "desk-highlight.png"
    image.resize((image.width // 2, image.height // 2)).save(out)
    subprocess.run(["open", "-a", "Preview", str(out)])
    print(out)


def see(text):
    jev_start()
    RUNTIME.mkdir(exist_ok=True)
    image = pyautogui.screenshot()
    image.resize((WIDTH, round(image.height * WIDTH / image.width))).save(RUNTIME / "jev-1.png")
    print(f"yes {jev('see', text, RUNTIME / 'jev-1.png')['yes']:.2f}")


def ui(args):
    from . import ax

    find = args[args.index("--find") + 1].lower() if "--find" in args else None
    show_all = "--all" in args
    if "--full" in args:  # untruncated labels, for reading paragraphs rather than finding buttons
        ax.MAX_TEXT = 2000
    rest = [a for i, a in enumerate(args) if a not in ("--find", "--all", "--full") and (i == 0 or args[i - 1] != "--find")]
    RUNTIME.mkdir(exist_ok=True)
    app, title, found = ax.elements(" ".join(rest) or None)
    # numbering always covers everything, so #N stays valid whatever was printed
    UI.write_text(json.dumps({"pid": app.processIdentifier(), "elements": found}))
    name = app.localizedName()
    print(f"{name} — {title}" if title else name)
    lines = [(i, e) for i, e in enumerate(found, 1) if not find or find in e["text"].lower()]
    for i, e in lines if show_all or find else lines[:UI_LINES]:
        print(f"{i} {e['role']} {e['text']!r}" if e["text"] else f"{i} {e['role']}")
    if not found:
        print("(nothing readable: this app draws its own pixels, so use `desk shot`)")
    elif not (show_all or find) and len(lines) > UI_LINES:
        print(f"... {len(lines) - UI_LINES} more: use --find TEXT, --all, or `desk shot`")


def moves(app, title, found):
    """The full menu of moves: every keyboard shortcut, plus each labelled clickable element on screen by its #N."""
    mouse = {f"#{i}": f"{e['role']} {e['text']}" for i, e in enumerate(found, 1) if e["role"] in CLICKABLE and e["text"]}
    return {"app": app, "window": title, "keyboard": KEYS, "mouse": mouse}


def map_(args):
    from . import ax

    RUNTIME.mkdir(exist_ok=True)
    app, title, found = ax.elements(" ".join(args) or None)
    UI.write_text(json.dumps({"pid": app.processIdentifier(), "elements": found}))  # so `click #N` matches
    print(json.dumps(moves(app.localizedName(), title, found), indent=1, ensure_ascii=False))


def until(args):
    from . import ax
    from .ax import elements

    ax.MAX_TEXT = 1_000_000  # match anywhere, e.g. inside a terminal's single big text area
    gone = "--gone" in args
    timeout = float(args[args.index("--timeout") + 1]) if "--timeout" in args else 300
    words = [a for i, a in enumerate(args) if a not in ("--gone", "--timeout") and (i == 0 or args[i - 1] != "--timeout")]
    texts, app_name = words[0].lower().split("|"), " ".join(words[1:]) or None  # "log out|logout": any of them
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, title, found = elements(app_name)
        hits = [e for e in found if any(t in e["text"].lower() for t in texts)]
        hits += [{"role": "window", "text": title}] if any(t in title.lower() for t in texts) else []
        if bool(hits) != gone:
            print(f"{'gone' if gone else 'found'}: {hits[0]['role']} {hits[0]['text']!r}" if hits else "gone")
            return
        time.sleep(min(2, timeout / 6))
    sys.exit(f"Timed out after {timeout:.0f}s waiting for {words[0]!r} to {'go' if gone else 'appear'}.")


def do(command, args):
    match command:
        case "ui":
            ui(args)
        case "map":
            map_(args)
        case "shot":
            shot()
        case "find":
            return find(" ".join(args))
        case "highlight":
            return find(" ".join(args), show=True)
        case "see":
            see(" ".join(args))
        case "do":
            from . import desk_do

            return desk_do.run(args)
        case "demo":
            from . import desk_demo

            desk_demo.run(args)
        case "click":
            (x, y), rest = point(args)
            if not click(x, y, rest[0] if rest else "left"):
                return "click changed nothing on screen"
        case "move":
            glide(*point(args)[0])
        case "drag":
            (x1, y1), rest = point(args)
            (x2, y2), _ = point(rest)
            pyautogui.moveTo(x1, y1)
            pyautogui.mouseDown()
            pyautogui.moveTo(x2, y2, duration=0.8)  # gradual, so apps see motion events, not a jump
            pyautogui.mouseUp()
        case "type":
            text = " ".join(args)
            mode = next((f for f in ("--natural", "--keys") if text.startswith(f + " ")), None)
            if mode:  # a batch hands the rest over raw, quotes and all
                text = text[len(mode) + 1:].strip()
                text = text[1:-1] if len(text) > 1 and text[0] == text[-1] and text[0] in "'\"" else text
            if mode == "--natural":
                natural_type(text)
            elif mode == "--keys":
                pyautogui.write(text, interval=0.03)
            else:
                paste(text)
        case "key":
            pyautogui.hotkey(*[k.replace("cmd", "command") for k in args[0].lower().split("+")])
        case "scroll":
            amount = int(args[1]) * (1 if args[0] in ("up", "right") else -1)
            (pyautogui.scroll if args[0] in ("up", "down") else pyautogui.hscroll)(amount)
        case "open":
            subprocess.run(["open", "-a", " ".join(args)])
            time.sleep(0.5)
        case "wait":
            time.sleep(float(args[0]))
        case "until":
            until(args)
        case "expect":
            until(args if "--timeout" in args else args + ["--timeout", "3"])
        case "run":
            batch = steps(" ".join(args))
            left_at = None  # where the cursor was after the last step; Claude never moves it between steps
            for i, words in enumerate(batch, 1):
                now = pyautogui.position()
                if left_at and abs(now[0] - left_at[0]) + abs(now[1] - left_at[1]) > 3:
                    sys.exit(f"Stopped before step {i} of {len(batch)} ({' '.join(words)}): you moved the mouse, so it's yours")
                try:
                    problem = do(words[0], words[1:])
                except SystemExit as e:
                    problem = str(e.code)
                if problem:
                    sys.exit(f"Stopped at step {i} of {len(batch)} ({' '.join(words)}): {problem}")
                time.sleep(0.1)  # let the app catch up between steps
                left_at = tuple(pyautogui.position())
        case _:
            sys.exit(__doc__)


def main(argv):
    if not argv:
        sys.exit(__doc__)
    pyautogui.PAUSE = 0.05  # slam the mouse into a corner to abort (pyautogui's fail-safe)
    problem = do(argv[0], argv[1:])
    if problem:
        print(problem)


if __name__ == "__main__":
    main(sys.argv[1:])
