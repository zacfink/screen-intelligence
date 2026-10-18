"""desk jevtype: Jev writes, one character at a time. Each character is a Choice over the keyboard (letters, digits,
space, punctuation, end); the chosen one is typed straight away with a keystroke, then Jev picks the next.

  desk jevtype "What's the capital of Canada?" [--max 80] [--dry] [--words]   --dry prints instead of typing;
                            --words picks whole words from your notes' 3,000 commonest (letters alone spell nothing)

Jev is a decision model, not a writer, so this is a stunt to see how far one-character choices get, not a typist.
"""
import collections
import json
import re
import string
from pathlib import Path
import sys
import time

from . import desk

KEYS = {c: None for c in string.ascii_lowercase + string.digits}
KEYS.update({"space": "a space between words", "period": ".", "comma": ",", "question": "?", "exclamation": "!",
             "apostrophe": "'", "dash": "-", "END": "the answer is finished"})
CHAR = {"space": " ", "period": ".", "comma": ",", "question": "?", "exclamation": "!", "apostrophe": "'", "dash": "-"}


def vocabulary(question, size=3000):
    """Whole words for --words mode: the most common words in ~/Notes plus the question's own words."""
    counts = collections.Counter(w for f in (Path.home() / "Notes").rglob("*.md")
                                 for w in re.findall(r"[A-Za-z][a-z']+", f.read_text(errors="ignore")))
    lower = {w for w in counts if w.islower()}
    # one form per word: "Review" folds into "review"; names that never appear lowercase (Ottawa, QWeb) keep capitals
    words = [w.lower() if w.lower() in lower else w for w, _ in counts.most_common(size)]
    words += re.findall(r"[A-Za-z][a-z']+", question)
    return {w: None for w in dict.fromkeys(words)} | {".": None, "END": None}


def run_words(question, most):
    """Jev picks the next whole word. A choice takes at most 255 options, so the vocabulary is split into lists of
    250, all asked in the same request (Jev answers them in parallel), and the most confident word across them wins."""
    vocab, typed, times = list(vocabulary(question)), [], []
    chunks = [vocab[i:i + 250] for i in range(0, len(vocab), 250)]
    while len(typed) < most:
        t0 = time.time()
        ask = ("We are writing a correct answer to `question` as one full, natural sentence, one word at a time. `answer_so_far` is what has"
               " been written. Which word comes next? Choose none if the right next word isn't in this list.")
        spec = {"state": {"question": question, "answer_so_far": " ".join(typed) or "(nothing yet)"},
                "questions": {f"w{i}": {"type": "choice", "instructions": ask,
                                        "criteria": {w: None for w in c} | {"none": "the right next word isn't listed"}}
                              for i, c in enumerate(chunks)}}
        answers = desk.jev("raw", json.dumps(spec), "").values()
        best = max(((w, p) for a in answers for w, p in a["probabilities"].items() if w != "none"), key=lambda x: x[1])
        word = best[0]
        times.append(time.time() - t0)
        if word == "END":
            break
        out = word if word == "." else (" " if typed else "") + (word.capitalize() if not typed else word)
        typed.append(word)
        yield out
        if word == ".":
            break
    print(f"\n[{len(typed)} words, {sum(times) / max(1, len(times)):.2f}s per Jev choice]", file=sys.stderr)


def run(args):
    question = next(a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--max"))
    most = int(args[args.index("--max") + 1]) if "--max" in args else 80
    dry = "--dry" in args
    desk.jev_start()
    if "--words" in args:
        for out in run_words(question, most if "--max" in args else 20):
            sys.stdout.write(out) if dry else desk.natural_type(out)
            sys.stdout.flush()
        return
    typed, times = "", []
    while len(typed) < most:
        t0 = time.time()
        spec = {"state": {"question": question, "answer_so_far": typed or "(nothing yet)"},
                "questions": {"next": {"type": "choice", "criteria": KEYS, "instructions":
                    "We are writing a short, correct answer to `question`, one keyboard key at a time. `answer_so_far`"
                    " is what has been typed. Which key comes next? Choose END when the answer is complete."}}}
        key = desk.jev("raw", json.dumps(spec), "")["next"]["choice"]
        times.append(time.time() - t0)
        if key == "END":
            break
        ch = CHAR.get(key, key)
        if not typed.strip() or typed.rstrip().endswith((".", "?", "!")):
            ch = ch.upper()  # capitals come automatically: a "capital" key changed nothing, so Jev chose it forever
        typed += ch
        sys.stdout.write(ch) if dry else desk.natural_type(ch, wpm=400)
        sys.stdout.flush()
    print(f"\n[{len(typed)} characters, {sum(times) / max(1, len(times)):.2f}s per Jev choice]", file=sys.stderr)
