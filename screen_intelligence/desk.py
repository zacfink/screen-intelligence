"""desk: let Claude drive the Mac. Claude is the vision model and planner; this only sees and acts.

    desk shot                 screenshot -> runtime/desk.png (1280 wide, grid every 100px), prints its path
    desk click X Y [right|double]   click at (X, Y) in the last screenshot's coordinates
    desk type "text"          type text at the cursor
    desk key cmd+l            press a key or a combo (pyautogui key names joined by +)
    desk scroll up|down|left|right N
    desk open "App Name"      open or switch to an app
"""
import json
import subprocess
import sys

import pyautogui
from PIL import Image, ImageDraw

from . import RUNTIME
from .actions import scroll

WIDTH = 1280  # small enough that the image reaches Claude unshrunk, so its coordinates are exact
GRID = 100
SHOT = RUNTIME / "desk.png"
SCALE = RUNTIME / "desk-scale.json"  # screen points per screenshot pixel, from the last shot


def to_screen(x, y, scale):
    return round(x * scale), round(y * scale)


def shot():
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
    draw = ImageDraw.Draw(image)
    mx, my = pyautogui.position()
    scale = screen_w / WIDTH
    cx, cy = mx / scale, my / scale
    draw.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), outline=(255, 0, 0), width=2)
    image.save(SHOT)
    SCALE.write_text(json.dumps(scale))
    print(SHOT)


def main(argv):
    if not argv:
        sys.exit(__doc__)
    command, args = argv[0], argv[1:]
    pyautogui.PAUSE = 0.15  # slam the mouse into a corner to abort (pyautogui's fail-safe)
    match command:
        case "shot":
            shot()
        case "click":
            if not SCALE.exists():
                sys.exit("Take a shot first: click coordinates are in the last screenshot's space.")
            x, y = to_screen(float(args[0]), float(args[1]), json.loads(SCALE.read_text()))
            kind = args[2] if len(args) > 2 else "left"
            if kind == "double":
                pyautogui.doubleClick(x, y)
            else:
                pyautogui.click(x, y, button=kind)
        case "type":
            # pyautogui.write drops non-ASCII, so paste anything else through the clipboard
            text = " ".join(args)
            if text.isascii():
                pyautogui.write(text, interval=0.02)
            else:
                subprocess.run(["pbcopy"], input=text.encode())
                pyautogui.hotkey("command", "v")
        case "key":
            pyautogui.hotkey(*[k.replace("cmd", "command") for k in args[0].lower().split("+")])
        case "scroll":
            scroll(args[0], int(args[1]))
        case "open":
            subprocess.run(["open", "-a", " ".join(args)])
        case _:
            sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
