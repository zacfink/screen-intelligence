"""desk: let Claude drive the Mac. Claude is the vision model and planner; this only sees and acts.

  Look (cheapest first):
    desk ui [--find TEXT] [--all] [--full] [App]   front window's buttons, fields and labels as numbered lines
                              (first 80 unless --all; --find keeps lines containing TEXT)
    desk shot                 screenshot -> runtime/desk.png (1280 wide, grid every 100px), prints its path
  Act:
    desk click #N             click element N from the last `ui`
    desk click X Y [right|double]   click at (X, Y) in the last screenshot's pixels
    desk drag X1 Y1 X2 Y2     press, move slowly, release (screenshot pixels)
    desk type "text"          paste text at the cursor (keeps your clipboard)
    desk type --keys "text"   real keystrokes, for menus and anything that ignores paste
    desk key cmd+l            a key or a combo (pyautogui key names joined by +)
    desk scroll up|down|left|right N
    desk open "App Name"      open or switch to an app
    desk wait SECONDS
  Hand off:
    desk until TEXT[|TEXT2] [App] [--gone] [--timeout S]   wait until a label containing TEXT appears (or, with
                              --gone, disappears), e.g. while Zac logs in. Checks every 2s, gives up after S (300).
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
    """#N -> centre of element N from the last ui; X Y -> screenshot pixels scaled to the screen."""
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


def click(x, y, kind):
    """Click, then report whether the screen changed. The mouse moves first so hover effects don't count."""
    pyautogui.moveTo(x, y)
    time.sleep(0.15)
    bounds = window_at(x, y)
    before = frame(bounds)
    if kind == "double":
        pyautogui.doubleClick(x, y)
    else:
        pyautogui.click(x, y, button=kind)
    deadline = time.time() + CHANGE_WAIT
    while time.time() < deadline:
        time.sleep(0.15)
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


def steps(text):
    """Split a batch on ; outside quotes. # isn't a comment here, since #N means element N."""
    lex = shlex.shlex(text, posix=True, punctuation_chars=";")
    lex.whitespace_split, lex.commenters = True, ""
    out, step = [], []
    for token in lex:
        if token == ";":
            out, step = out + [step] if step else out, []
        else:
            step.append(token)
    return out + [step] if step else out


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


def until(args):
    from .ax import elements

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
        case "shot":
            shot()
        case "click":
            (x, y), rest = point(args)
            if not click(x, y, rest[0] if rest else "left"):
                return "click changed nothing on screen"
        case "drag":
            (x1, y1), rest = point(args)
            (x2, y2), _ = point(rest)
            pyautogui.moveTo(x1, y1)
            pyautogui.mouseDown()
            pyautogui.moveTo(x2, y2, duration=0.8)  # gradual, so apps see motion events, not a jump
            pyautogui.mouseUp()
        case "type":
            if args and args[0] == "--keys":
                pyautogui.write(" ".join(args[1:]), interval=0.03)
            else:
                paste(" ".join(args))
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
