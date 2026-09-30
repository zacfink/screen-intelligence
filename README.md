# Screen Intelligence

A macOS agent that looks at the screen, works out the steps, and drives the mouse and keyboard to
carry them out. You give it an instruction in plain English — "Go onto Safari and open the Amazon
Neo hedged stock" — and it does the clicking.

Built in 2025 as an experiment in whether a vision model plus a fixed action vocabulary is enough to
operate a desktop without any app-specific integration. It is a prototype, not a product.

## How it works

1. **Capture** — takes a screenshot of the current screen.
2. **Describe** — sends it to GPT-4o with a prompt that forces a spatial, bullet-point breakdown:
   which app is open, where the panels are, what text is visible, where the cursor is.
3. **Reason** — turns that description plus your instruction into an ordered list of steps, drawn
   from a fixed action vocabulary defined in `screen_intelligence/action_list.json`
   (`move_mouse`, `left_click`, `scroll`, keyboard input, and so on — each with its arguments,
   preconditions and expected visible effect).
4. **Act and verify** — runs each step, takes a before and after screenshot around it, and compares
   them to check the action actually did something.
5. **Recover** — if the screen didn't change the way the step predicted, it reasons about the
   failure and alters the remaining steps rather than blindly continuing.

Steps the model marks `requires_confirmation` pop a dialog and wait for you before running. There
is also an OCR fallback (`ocr.py`) for finding a target by its on-screen text when
coordinates aren't reliable, and a log of every step taken in `runtime/steps.json`.

## Layout

All of it is in `screen_intelligence/`:

- `__main__.py` — entry point: screenshot, describe, plan, run.
- `llm.py` — the four model calls (describe, plan, check a step, replan).
- `agent.py` — the run loop: act, screenshot before and after, check, replan.
- `actions.py` — the action vocabulary, carried out with pyautogui.
- `ocr.py` — finds on-screen text with Tesseract for `move_and_click_text`.
- `screenshots.py` — capture and encode.

## Running it

Needs Python 3.10, an OpenAI API key, and Tesseract installed for the OCR fallback.

```bash
pip install -r requirements.txt
echo "OPENAI_API_KEY=sk-..." > .env
python -m screen_intelligence "Open Safari and search for the weather in Kingston"
```

Leave off the instruction and it asks for one. macOS will ask for Screen Recording and
Accessibility permission the first time, because the agent really does take over the mouse and
keyboard. To stop it mid-run, slam the mouse into a corner of the screen (pyautogui's fail-safe).

A run stops on its own when you decline a confirmation, when the plan asks for an action outside
the vocabulary, or after 5 replans of a step that keeps failing.

Tests (no model calls, nothing touches the real mouse):

```bash
python -m unittest
```

## Known rough edges

- Which steps ask for confirmation is decided by the model, not by you, so a step it judges safe
  runs without asking. Watch it while it runs.
- `undo_tag` is part of the plan schema and gets recorded, but nothing ever acts on it — there is
  no rollback.
- Coordinates for `move_mouse` come from a text description of the screen, not from the image
  itself, so they are guesses. `move_and_click_text` (OCR) is the reliable way to hit a target.
