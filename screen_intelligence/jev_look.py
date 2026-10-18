"""Ask Jev about a screenshot. Runs in the TypeSafe venv (desk itself runs on pyenv 3.10, which has no SDK), so
desk calls it as a subprocess and gets one JSON line back.

  jev_look.py box "the Submit button" IMAGE    -> {"box": {top, bottom, left, right}, "confidence", "visible"}
  jev_look.py see "Is there an error?" IMAGE   -> {"yes": probability}
  jev_look.py raw SPEC_JSON IMAGE              -> any questions: SPEC = {"state": {...}, "questions": {name: {"type":
                                                  "noul"|"choice"|"box", "instructions", "criteria"}}}; `screen` is the image
  jev_look.py serve                            -> one JSON line in ([mode, text, image]), one out, until stdin closes:
                                                  one Python start and one open connection for a whole desk run

Images and Box are TypeSafe beta features: they need the danger-zone header and Jev 1.14 by name.
"""
import json
import os
import re
import sys
from pathlib import Path

from typesafe_sdk import Box, Choice, Image, Noul, TypeSafeClient

MODEL = "jev-1.14.0"  # jev-latest is still 1.13, which has no Box
HEADERS = {"TypeSafe-Danger-Zone-Images": "true"}


def api_key():
    """Claude's tool shells don't read ~/.zshrc, where the key lives, so fall back to its export line."""
    if os.environ.get("TYPESAFE_API_KEY"):
        return os.environ["TYPESAFE_API_KEY"]
    m = re.search(r"^export TYPESAFE_API_KEY=['\"]?([^'\"\s]+)", (Path.home() / ".zshrc").read_text(), re.M)
    if not m:
        sys.exit("TYPESAFE_API_KEY isn't set (or in ~/.zshrc)")
    return m.group(1)


def raw(client, spec, image):
    """Free-form request for desk do: the caller writes the state and questions, the image goes in as `screen`."""
    kinds = {"noul": lambda q: Noul(instructions=q["instructions"]), "box": lambda q: Box(instructions=q["instructions"]),
             "choice": lambda q: Choice(instructions=q["instructions"], criteria=q["criteria"])}
    questions = {k: kinds[q["type"]](q) for k, q in spec["questions"].items()}
    state = {**spec["state"], "screen": Image(Path(image))} if image else spec["state"]  # no image: text only
    a = client.system_one(model=MODEL, state=state, questions=questions, extra_headers=HEADERS).answers
    out = {}
    for k, v in a.items():
        if v.type == "noul":
            out[k] = v.noul
        elif v.type == "choice":
            out[k] = {"choice": v.choice, "confidence": v.confidence, "probabilities": dict(v.probabilities or {})}
        else:
            out[k] = {"box": {"top": v.box.top, "bottom": v.box.bottom, "left": v.box.left, "right": v.box.right},
                      "confidence": v.confidence}
    return out


def ask(client, mode, text, image):
    if mode == "raw":
        return raw(client, json.loads(text), image)
    state = {"screen": Image(Path(image))}
    if mode == "see":
        questions = {"yes": Noul(instructions=f"{text} Look at `screen`.")}
    else:  # a Box always returns a box, even for something absent, so a Noul says whether to trust it
        questions = {"box": Box(instructions=f"{text} in `screen`"),
                     "visible": Noul(instructions=f"Is {text} visible in `screen`?")}
    a = client.system_one(model=MODEL, state=state, questions=questions, extra_headers=HEADERS).answers
    if mode == "see":
        return {"yes": a["yes"].noul}
    b = a["box"].box
    return {"box": {"top": b.top, "bottom": b.bottom, "left": b.left, "right": b.right},
            "confidence": a["box"].confidence, "visible": a["visible"].noul}


if __name__ == "__main__":
    with TypeSafeClient(api_key=api_key()) as client:
        if sys.argv[1] != "serve":
            print(json.dumps(ask(client, *sys.argv[1:4])))
        for line in sys.stdin if sys.argv[1] == "serve" else []:
            try:
                out = ask(client, *json.loads(line))
            except Exception as e:  # report and keep serving; desk turns it into a message
                out = {"error": f"{type(e).__name__}: {e}"}
            print(json.dumps(out), flush=True)
