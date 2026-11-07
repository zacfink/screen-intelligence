"""desk js: drive the front Safari tab through its own page code (the DOM) instead of pixels. ~0.1s a step.

  desk js read [--find TEXT]   numbered clickable/typeable elements on the page (same idea as `ui`, from the DOM)
  desk js text [--max N]       the page as words: dialogs/alerts, headings, field values, then body text. Replaces
                               a screenshot for reading a page.
  desk js click N [--real] [--allow-risky]   click element N. Refuses send/submit/delete/pay labels without
                               --allow-risky, and elements a dialog covers. Tries a JS click; if the page doesn't react (sites that ignore
                               synthetic clicks), falls back to a real mouse click at the element's exact spot.
  desk js type N "text"        set a field's text the way React/Vue notice; falls back to a real click + paste
  desk js eval "code"          run JS in the tab, print the result
  desk js selftest             check the fallbacks on a page built to defeat them (then `desk demo js` for speed)

Fallbacks are logged to runtime/js-log.jsonl: the sites that need real input. Every click/type also saves a
background screenshot to runtime/js-audit/ (last 50), for checking what was really on screen afterwards.

Needs Safari ▸ Develop ▸ Allow JavaScript from Apple Events (on). Cross-origin iframes and canvas apps can't be
read this way: use `desk ui` / `desk find` for those, and for native apps.
"""
import json
import re
import subprocess
import sys
import time

from . import RUNTIME

STATE = RUNTIME / "desk-js.json"
LOG = RUNTIME / "js-log.jsonl"  # every fallback (page ignored js), so the sites that need real input are on record
REACT_WAIT = 0.25  # seconds a JS click gets to change the page before we fall back to a real click

# Tags each element with data-desk=N and returns them with their spot in the viewport plus the window geometry,
# so a real click can land on it without a screenshot.
READ = r"""(() => {
const sel = 'a[href],button,input:not([type=hidden]),textarea,select,summary,[role=button],[role=link],[role=tab],' +
  '[role=menuitem],[role=checkbox],[role=option],[contenteditable=""],[contenteditable=true],[onclick],[tabindex]:not([tabindex="-1"])';
const out = [], kept = new Map();  // element -> label, to drop nested duplicates (a link inside a link)
document.querySelectorAll('[data-desk]').forEach(e => e.removeAttribute('data-desk'));
for (const e of document.querySelectorAll(sel)) {
  const r = e.getBoundingClientRect();
  if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
  const s = getComputedStyle(e);
  if (s.visibility === 'hidden' || s.opacity === '0') continue;
  const text = (e.getAttribute('aria-label') || e.innerText || e.value || e.placeholder || e.title || e.alt ||
    (e.querySelector('img') || {}).alt || '').trim().replace(/\s+/g, ' ').slice(0, 80);
  const up = e.parentElement && e.parentElement.closest(sel);
  if (up && kept.has(up) && (kept.get(up) === text || !text)) continue;
  kept.set(e, text);
  const role = e.getAttribute('role') || (e.tagName === 'INPUT' ? 'input:' + (e.type || 'text') : e.tagName.toLowerCase());
  e.setAttribute('data-desk', out.length + 1);
  out.push({role, text, x: r.left + r.width / 2, y: r.top + r.height / 2});
}
const frames = [...document.querySelectorAll('iframe')].filter(f => { try { return !f.contentDocument } catch { return true } }).length;
return JSON.stringify({url: location.href, title: document.title, sx: screenX, sy: screenY,
  top: outerHeight - innerHeight, frames, elements: out});
})()"""

# Click, and watch for the page reacting: DOM changes, navigation, focus or scroll.
CLICK = r"""(() => {
const e = document.querySelector('[data-desk="%d"]');
if (!e) return 'gone';
let r = e.getBoundingClientRect();
if (r.bottom < 0 || r.top > innerHeight) { e.scrollIntoView({block: 'center'}); r = e.getBoundingClientRect(); }
const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
if (top && !e.contains(top) && !top.contains(e))  // a dialog or overlay sits on it: a person couldn't click it
  return 'covered:' + (top.getAttribute('aria-label') || top.innerText || top.tagName).trim().slice(0, 60);
window.__desk = {n: 0, href: location.href, focus: document.activeElement, sy: scrollY};
window.__desk.obs = new MutationObserver(m => window.__desk.n += m.length);
window.__desk.obs.observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
e.click();
const d = window.__desk;
return d.obs.takeRecords().length || d.href !== location.href || d.focus !== document.activeElement || d.sy !== scrollY ? 'reacted' : 'ok';
})()"""
REACTED = r"""(() => { const d = window.__desk; return !d || d.n > 0 || d.href !== location.href ||
  d.focus !== document.activeElement || d.sy !== scrollY ? 'yes' : 'no' })()"""
WHERE = r"""(() => { const e = document.querySelector('[data-desk="%d"]'); if (!e) return '';
e.scrollIntoView({block: 'center', inline: 'center'}); const r = e.getBoundingClientRect();
return JSON.stringify({x: screenX + r.left + r.width / 2, y: screenY + outerHeight - innerHeight + r.top + r.height / 2}) })()"""
# The native value setter is what makes React see the change; plain `e.value = x` gets overwritten on next render.
TYPE = r"""((t) => { const e = document.querySelector('[data-desk="%d"]'); if (!e) return 'gone';
e.focus();
if (e.isContentEditable) { document.execCommand('selectAll'); document.execCommand('insertText', false, t); }
else { const p = e instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : e instanceof HTMLSelectElement ?
  HTMLSelectElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(p, 'value').set.call(e, t);
  e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); }
return (e.isContentEditable ? e.innerText : e.value).trim() === t.trim() ? 'ok' : 'mismatch';
})(%s)"""


def js(code):
    """Run JS in Safari's front tab, in-process (NSAppleScript, ~12ms) rather than spawning osascript (~110ms)."""
    from Foundation import NSAppleScript

    literal = '"' + code.replace("\\", "\\\\").replace('"', '\\"') + '"'
    script = NSAppleScript.alloc().initWithSource_(
        f'tell application "Safari" to do JavaScript {literal} in current tab of front window')
    result, err = script.executeAndReturnError_(None)
    if err:
        msg = str(err.get("NSAppleScriptErrorMessage", err))
        if "Allow JavaScript" in msg or err.get("NSAppleScriptErrorNumber") in (-1743, 8):
            sys.exit("Turn on Safari ▸ Develop ▸ Allow JavaScript from Apple Events, then retry.")
        sys.exit(f"Safari JS failed: {msg}")
    return (result.stringValue() or "").strip() if result else ""


TEXT = r"""(() => {
const v = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 };
const t = s => (s || '').trim().replace(/\s+/g, ' ');
const alerts = [...document.querySelectorAll('[role=alert],[role=alertdialog],[aria-live=assertive],dialog[open],[aria-modal=true]')]
  .filter(v).map(e => t(e.innerText).slice(0, 200)).filter(Boolean);
const heads = [...document.querySelectorAll('h1,h2,h3')].filter(v).map(e => t(e.innerText).slice(0, 100)).filter(Boolean).slice(0, 15);
const fields = [...document.querySelectorAll('input:not([type=hidden]),textarea,select')].filter(v).map(e =>
  t(e.getAttribute('aria-label') || (e.labels && e.labels[0] && e.labels[0].innerText) || e.placeholder || e.name) + ' = ' +
  (e.type === 'password' ? '••••' : e.type === 'checkbox' || e.type === 'radio' ? e.checked : t(e.value).slice(0, 60))).slice(0, 25);
const main = document.querySelector('main,[role=main]') || document.body;
return JSON.stringify({title: document.title, url: location.href, alerts, heads, fields, body: t(main.innerText).slice(0, %d)});
})()"""


def text(limit=2500):
    """The page as text: alerts and dialogs first, then headings, form fields with their values, then the words."""
    p = json.loads(js(TEXT % limit))
    print(f"{p['title']}\n{p['url']}")
    for name in ("alerts", "heads", "fields"):
        if p[name]:
            print(f"{name}: " + " | ".join(p[name]))
    print(p["body"])


def note(what, n):
    """Record a fallback with the page it happened on."""
    try:
        page = json.loads(STATE.read_text())
        el = page["elements"][n - 1] if 0 < n <= len(page["elements"]) else {}
    except (OSError, ValueError):
        page, el = {}, {}
    with LOG.open("a") as f:
        f.write(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M"), "what": what, "url": page.get("url"),
                            "element": f"{el.get('role')} {el.get('text')!r}"}) + "\n")


def read(find=None):
    page = json.loads(js(READ))
    RUNTIME.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(page))
    print(page["title"] or page["url"])
    for i, e in enumerate(page["elements"], 1):
        if not find or find.lower() in e["text"].lower():
            print(f"{i} {e['role']} {e['text']!r}" if e["text"] else f"{i} {e['role']}")
    if page["frames"]:
        print(f"({page['frames']} cross-origin frame(s) not readable here: use `desk ui` / `desk find` inside them)")
    return page


def real_click(n):
    from . import desk

    spot = js(WHERE % n)
    if not spot:
        return f"element {n} is gone: run `desk js read` again"
    desk.pyautogui.PAUSE = 0.05  # main() skipped this for js; corner-slam fail-safe still applies
    time.sleep(0.15)  # let scrollIntoView settle
    spot = json.loads(js(WHERE % n))
    desk.click(round(spot["x"]), round(spot["y"]), "left")


RISKY = re.compile(r"\b(send|submit|delete|remove|pay|buy|purchase|order|post|publish|confirm|apply|sign up|unsubscribe)\b", re.I)
AUDIT = RUNTIME / "js-audit"  # a screenshot per action, taken in the background, for checking afterwards
AUDIT_KEEP = 50


def label(n):
    try:
        return json.loads(STATE.read_text())["elements"][n - 1]["text"]
    except (OSError, ValueError, IndexError, KeyError):
        return ""


def audit(what):
    """Screenshot what's on screen as an action happens, without waiting for it (~0s on the action's clock)."""
    AUDIT.mkdir(parents=True, exist_ok=True)
    name = time.strftime("%H%M%S") + f"-{what}.jpg"
    subprocess.Popen(["screencapture", "-x", "-t", "jpg", str(AUDIT / name)])
    for old in sorted(AUDIT.glob("*.jpg"))[:-AUDIT_KEEP]:
        old.unlink(missing_ok=True)


def click(n, real=False, risky=False):
    text = label(n)
    if RISKY.search(text) and not risky:
        return f"element {n} is {text!r}: that looks like send/submit/delete/pay. Ask Zac, then add --allow-risky"
    audit(f"click{n}")
    if real:
        return real_click(n) or print("real click")
    first = js(CLICK % n)
    if first == "gone":
        return f"element {n} is gone: run `desk js read` again"
    if first.startswith("covered:"):
        return f"element {n} is covered by {first[8:]!r} (a dialog?): deal with that first"
    if first == "reacted":  # the handler changed the page right away: no need to wait
        return print("js click")
    time.sleep(REACT_WAIT)  # maybe it reacts later (fetch, then render)
    if js(REACTED) == "yes":
        return print("js click")
    print("page ignored the js click; real click")
    note("click fallback", n)
    return real_click(n)


def type_(n, text):
    from . import desk

    audit(f"type{n}")
    result = js(TYPE % (n, json.dumps(text)))
    if result == "gone":
        return f"element {n} is gone: run `desk js read` again"
    if result == "ok":
        return print("typed (js)")
    print("field rejected js text; real click + paste")
    note("type fallback", n)
    real_click(n)
    desk.do("key", ["cmd+a"])
    desk.paste(text)


TRAPS = """<!doctype html><meta charset=utf-8><title>traps</title><body style="font:18px -apple-system;padding:60px">
<button id=t style="padding:20px 40px;font-size:20px">Trusted only</button>
<p><input id=c aria-label="Controlled" style="font-size:18px;padding:8px"> <span id=out></span>
<p style="position:relative;width:220px"><button id=h style="padding:12px 24px">Under dialog</button>
<span role=dialog style="position:absolute;inset:0;background:#0009;color:#fff">Cookie banner</span><script>
let log=[];const T=()=>document.title='traps · '+log.join(',');
t.addEventListener('click',e=>{if(e.isTrusted){log.push('trusted');T()}});
h.addEventListener('click',()=>{log.push('UNDER-CLICKED');T()});
let state='';c.addEventListener('input',e=>{state=e.target.value;out.textContent='state='+state;log.push('state:'+state);T()});
setInterval(()=>{if(c.value!==state)c.value=state},100);</script>"""


def selftest():
    """Open a page built to defeat page-code input (a button that only takes real clicks, a React-style field) and
    check both fallbacks land. Then `desk demo js` scores plain buttons."""
    page = RUNTIME / "js-traps.html"
    RUNTIME.mkdir(exist_ok=True)
    stamp = f"{time.time():.0f}"
    page.write_text(TRAPS.replace("<title>traps</title>", f"<title>traps</title><meta name=run content={stamp}>"))
    subprocess.run(["open", "-a", "Safari", f"file://{page}"])
    for _ in range(50):  # this run's tab, fully loaded: a page still loading looks like a page reacting to a click
        time.sleep(0.1)
        if js("(document.querySelector('meta[name=run]') || {}).content + document.readyState") == f"{stamp}complete":
            break
    else:
        return "selftest page never loaded"
    read()
    click(1)
    type_(2, "kingston weather")
    covered = click(3) or ""
    print(covered)
    time.sleep(0.3)
    got = js("document.title")
    ok = "trusted" in got and "state:kingston weather" in got and "covered" in covered and "UNDER" not in got
    js("window.close()")
    return None if ok else f"selftest failed: page says {got!r}"


def run(args):
    if not args:
        sys.exit(__doc__)
    cmd, rest = args[0], args[1:]
    if cmd == "read":
        read(rest[rest.index("--find") + 1] if "--find" in rest else None)
    elif cmd == "click":
        return click(int(rest[0].lstrip("#")), "--real" in rest, "--allow-risky" in rest)
    elif cmd == "type":
        words = " ".join(rest[1:])
        words = words[1:-1] if len(words) > 1 and words[0] == words[-1] and words[0] in "'\"" else words
        return type_(int(rest[0].lstrip("#")), words)
    elif cmd == "text":
        text(int(rest[rest.index("--max") + 1]) if "--max" in rest else 2500)
    elif cmd == "selftest":
        return selftest()
    elif cmd == "eval":
        print(js(" ".join(rest)))
    else:
        sys.exit(__doc__)
