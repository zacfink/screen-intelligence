"""desk: let Claude drive the Mac. Claude is the vision model and planner; this only sees and acts.

  Look (cheapest first):
    desk ui [--find TEXT] [--all] [App]   front window's buttons, fields and labels as numbered lines
                              (first 80 unless --all; --find keeps lines containing TEXT)
    desk shot                 screenshot -> runtime/desk.png (1280 wide, grid every 100px), prints its path
  Act:
    desk click #N             click element N from the last `ui`
    desk click X Y [right|double]   click at (X, Y) in the last screenshot's pixels
    desk drag X1 Y1 X2 Y2     press, move slowly, release (screenshot pixels)
    desk type "text"          type at the cursor
    desk key cmd+l            a key or a combo (pyautogui key names joined by +)
    desk scroll up|down|left|right N
    desk open "App Name"      open or switch to an app
    desk wait SECONDS
  Batch:
    desk run "click #4; type Zac; key tab; type Finkelstein; ui"
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
    from .ax import elements

    find = args[args.index("--find") + 1].lower() if "--find" in args else None
    show_all = "--all" in args
    rest = [a for i, a in enumerate(args) if a not in ("--find", "--all") and (i == 0 or args[i - 1] != "--find")]
    RUNTIME.mkdir(exist_ok=True)
    app, title, found = elements(" ".join(rest) or None)
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


def do(command, args):
    match command:
        case "ui":
            ui(args)
        case "shot":
            shot()
        case "click":
            (x, y), rest = point(args)
            kind = rest[0] if rest else "left"
            if kind == "double":
                pyautogui.doubleClick(x, y)
            else:
                pyautogui.click(x, y, button=kind)
        case "drag":
            (x1, y1), rest = point(args)
            (x2, y2), _ = point(rest)
            pyautogui.moveTo(x1, y1)
            pyautogui.mouseDown()
            pyautogui.moveTo(x2, y2, duration=0.8)  # gradual, so apps see motion events, not a jump
            pyautogui.mouseUp()
        case "type":
            # pyautogui.write drops non-ASCII, so paste anything else through the clipboard
            text = " ".join(args)
            if text.isascii():
                pyautogui.write(text, interval=0.01)
            else:
                subprocess.run(["pbcopy"], input=text.encode())
                pyautogui.hotkey("command", "v")
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
        case "run":
            for step in " ".join(args).split(";"):
                if step.strip():
                    words = shlex.split(step)
                    do(words[0], words[1:])
                    time.sleep(0.1)  # let the app catch up between steps
        case _:
            sys.exit(__doc__)


def main(argv):
    if not argv:
        sys.exit(__doc__)
    pyautogui.PAUSE = 0.05  # slam the mouse into a corner to abort (pyautogui's fail-safe)
    do(argv[0], argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
