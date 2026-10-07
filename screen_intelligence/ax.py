"""Read the frontmost window's accessibility tree: the buttons, fields and labels apps publish for
screen readers. Text instead of pixels, and exact positions instead of guessed ones."""
import time

from AppKit import NSWorkspace
from ApplicationServices import (
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
    AXUIElementSetAttributeValue,
    AXValueGetValue,
    kAXValueCGPointType,
    kAXValueCGSizeType,
)

ROLES = {  # AX role -> short name; anything else is walked through but not listed
    "AXButton": "button", "AXTextField": "field", "AXTextArea": "textarea", "AXSearchField": "search",
    "AXCheckBox": "checkbox", "AXRadioButton": "radio", "AXPopUpButton": "popup", "AXComboBox": "combo",
    "AXLink": "link", "AXMenuButton": "menu", "AXTab": "tab", "AXSlider": "slider", "AXStaticText": "text",
    "AXHeading": "heading", "AXMenuItem": "item",
}
MAX_NODES = 4000  # walk budget, so a huge web page can't hang
MAX_TEXT = 60


def attr(element, name):
    err, value = AXUIElementCopyAttributeValue(element, name, None)
    return value if err == 0 else None


def frame(element):
    pos, size = attr(element, "AXPosition"), attr(element, "AXSize")
    if pos is None or size is None:
        return None
    _, p = AXValueGetValue(pos, kAXValueCGPointType, None)
    _, s = AXValueGetValue(size, kAXValueCGSizeType, None)
    return p.x, p.y, s.width, s.height


def label(element, role):
    for name in ["AXTitle", "AXDescription", "AXValue", "AXPlaceholderValue", "AXHelp"]:
        value = attr(element, name)
        if isinstance(value, str) and value.strip():
            text = " ".join(value.split())
            return text if len(text) <= MAX_TEXT else text[:MAX_TEXT - 1] + "…"
    return ""


def front_app(name=None):
    apps = NSWorkspace.sharedWorkspace().runningApplications()
    if name:
        return next((a for a in apps if a.localizedName() == name), None)
    return NSWorkspace.sharedWorkspace().frontmostApplication()


def front_name():
    """Owner of the topmost window. Unlike frontmostApplication, this stays current in a long-running
    process (NSWorkspace only refreshes on a run loop, which `desk watch` doesn't have)."""
    import Quartz

    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    for w in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID):  # front to back
        if w.get("kCGWindowLayer") == 0:
            return w.get("kCGWindowOwnerName", "")
    return ""


def elements(app_name=None):
    """Visible, labelled elements of the app's focused window, in reading order."""
    app = front_app(app_name)
    if app is None:
        raise SystemExit(f"No running app called {app_name!r}.")
    root = AXUIElementCreateApplication(app.processIdentifier())
    # Chrome and Electron apps only build their web accessibility tree when asked to
    if AXUIElementSetAttributeValue(root, "AXManualAccessibility", True) == 0 and attr(root, "AXManualAccessibility") is not True:
        time.sleep(0.5)
    window = attr(root, "AXFocusedWindow") or attr(root, "AXMainWindow")
    if window is None:
        raise SystemExit(f"{app.localizedName()} has no window to read.")
    wx, wy, ww, wh = frame(window)

    found, stack, seen = [], [window], 0
    while stack and seen < MAX_NODES:
        element = stack.pop()
        seen += 1
        role = attr(element, "AXRole")
        f = frame(element)
        if role in ROLES and f and f[2] > 0 and f[3] > 0:
            x, y, w, h = f
            cx, cy = x + w / 2, y + h / 2
            text = label(element, role)
            if wx <= cx <= wx + ww and wy <= cy <= wy + wh and (text or role != "AXStaticText"):
                found.append({"role": ROLES[role], "text": text, "x": round(cx), "y": round(cy)})
        stack.extend(reversed(attr(element, "AXChildren") or []))

    found.sort(key=lambda e: (round(e["y"] / 8), e["x"]))  # rows, then left to right
    deduped, labels = [], set()
    for e in found:  # labels repeat a lot (a button's text child, a heading shown twice)
        if e["text"] and e["text"] in labels:
            continue
        labels.add(e["text"])
        deduped.append(e)
    return app, attr(window, "AXTitle") or "", deduped


def bring_to_front(pid):
    """Elements can sit under another window (the terminal, usually), so raise their app before clicking."""
    from AppKit import NSRunningApplication

    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if app and not app.isActive():
        app.activateWithOptions_(0)
        time.sleep(0.3)
