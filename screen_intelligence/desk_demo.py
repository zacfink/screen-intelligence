"""desk demo: a test page of buttons (big, medium, tiny) in random spots; desk finds and clicks each one and the page
says whether it was hit. Scores accuracy and speed, so changes to desk can be measured instead of guessed.

  desk demo [jev|ui] [N]    jev (default): find each button from pixels with Jev, then click @
                            ui: find it by label in the accessibility tree instead, for comparison
"""
import json
import random
import statistics
import subprocess
import time

from . import RUNTIME

# (id, text on the button, how a person would describe it, CSS size class)
TARGETS = [
    ("save", "Save", "the big green Save button", "big green"),
    ("delete", "Delete", "the big red Delete button", "big red"),
    ("send", "Send", "the big blue Send button", "big blue"),
    ("settings", "Settings", "the grey Settings button", "mid grey"),
    ("cancel", "Cancel", "the white Cancel button", "mid white"),
    ("upload", "Upload", "the purple Upload button", "mid purple"),
    ("next", "Next →", "the Next → button", "mid teal"),
    ("share", "Share", "the orange Share button", "mid orange"),
    ("close", "✕", "the small ✕ close button", "tiny dark"),
    ("gear", "⚙", "the small gear icon button", "tiny dark"),
    ("star", "☆", "the small star icon button", "tiny yellow"),
    ("help", "?", "the tiny ? help button", "tiny blue"),
]
PAGE = RUNTIME / "demo.html"
PAGE_TOP = 90  # screen points; Safari's tab and tool bars sit above this
CSS = """body{margin:0;background:#f4f1ea;font:16px -apple-system,sans-serif;height:100vh;overflow:hidden}
h1{position:fixed;left:24px;top:12px;margin:0;font-size:15px;color:#888;font-weight:500}
button{position:absolute;border:0;border-radius:10px;cursor:pointer;font-weight:600;color:#fff}
.big{padding:22px 44px;font-size:22px}.mid{padding:11px 20px;font-size:15px}
.tiny{width:26px;height:26px;padding:0;font-size:14px;border-radius:6px}
.green{background:#2e9d5b}.red{background:#d43c3c}.blue{background:#2f6fde}.grey{background:#7a7a7a}
.white{background:#fff;color:#333;border:1px solid #ccc}.purple{background:#7b4fd6}.teal{background:#15938a}
.orange{background:#e8822a}.dark{background:#333}.yellow{background:#e9b820;color:#333}"""


def page(targets, seed):
    """Buttons scattered over a 4x3 grid (one per cell, jittered), so none overlap. Each click sets the window
    title to 'hit <id> #<n>', which desk reads back through the accessibility tree; a click on nothing is a miss."""
    rng = random.Random(seed)
    cells = rng.sample([(c, r) for c in range(4) for r in range(3)], len(targets))
    buttons = "".join(
        f'<button id="{i}" class="{size}" aria-label="{text}" style="left:calc({c * 25 + 3 + rng.random() * 12}vw);'
        f'top:calc({r * 30 + 12 + rng.random() * 14}vh)">{text}</button>' for (i, text, _, size), (c, r) in zip(targets, cells))
    # a click also flashes the button, the way real buttons react, so desk's click sees the screen change at once
    js = ("let n=0;document.addEventListener('click',e=>{n++;const b=e.target.tagName==='BUTTON';document.title=(b?'hit '+e.target.id:'miss')"
          "+' #'+n;if(b){e.target.style.outline='5px solid #111';setTimeout(()=>e.target.style.outline='',400)}});")
    PAGE.write_text(f"<!doctype html><meta charset=utf-8><title>Desk demo</title><style>{CSS}</style><h1>desk demo · seed {seed}</h1>{buttons}<script>{js}</script>")


def title():
    from .ax import elements

    return elements("Safari")[1] or ""


def run(args):
    from . import desk

    mode = args[0] if args and args[0] in ("jev", "ui") else "jev"
    n = int(next((a for a in args if a.isdigit()), len(TARGETS)))
    seed = random.randrange(1000)
    targets = random.Random(seed).sample(TARGETS, n)
    RUNTIME.mkdir(exist_ok=True)
    page(targets, seed)
    subprocess.run(["open", "-a", "Safari", str(PAGE)])
    desk.until(["desk demo", "Safari", "--timeout", "10"])
    time.sleep(0.8)  # let the page paint before the first look
    rows, last = [], ""
    for i, text, desc, _ in targets:
        t0 = time.time()
        if mode == "jev":
            problem = desk.find(desc)
            conf = json.loads((RUNTIME / "desk-found-conf.json").read_text())
            located = time.time()
            desk.click(*desk.point(["@"])[0], "left")
        else:
            from . import ax

            _, _, found = ax.elements("Safari")
            # below Safari's toolbar, which has its own Share button
            e = next((e for e in found if e["role"] == "button" and e["text"] == text and e["y"] > PAGE_TOP), None)
            located, problem, conf = time.time(), None if e else "not in the accessibility tree", None
            if e:
                desk.click(e["x"], e["y"], "left")
        deadline, now = time.time() + 1, title()
        while now == last and time.time() < deadline:  # the title can lag the click a moment
            time.sleep(0.05)
            now = title()
        hit = now.startswith(f"hit {i} ") and now != last
        last = now
        rows.append({"target": desc, "hit": hit, "confidence": conf, "locate_s": round(located - t0, 2), "total_s": round(time.time() - t0, 2),
                     "note": problem or ("" if hit else now)})
        print(f"{'✓' if hit else '✗'} {desc:<30} locate {rows[-1]['locate_s']:.2f}s  total {rows[-1]['total_s']:.2f}s  {'' if conf is None else f'conf {conf:.2f}  '}{rows[-1]['note']}")
    hits = sum(r["hit"] for r in rows)
    print(f"\n{mode}: {hits}/{len(rows)} hit · median locate {statistics.median(r['locate_s'] for r in rows):.2f}s"
          f" · median per button {statistics.median(r['total_s'] for r in rows):.2f}s · seed {seed}")
    log = RUNTIME / "demo-log.jsonl"
    with log.open("a") as f:
        f.write(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M"), "mode": mode, "seed": seed, "hits": hits, "rows": rows}) + "\n")
