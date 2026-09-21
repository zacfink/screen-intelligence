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
   from a fixed action vocabulary defined in `actions/actionList/actionList.json`
   (`move_mouse`, `left_click`, `scroll`, keyboard input, and so on — each with its arguments,
   preconditions and expected visible effect).
4. **Act and verify** — runs each step, takes a before and after screenshot around it, and compares
   them to check the action actually did something.
5. **Recover** — if the screen didn't change the way the step predicted, it reasons about the
   failure and alters the remaining steps rather than blindly continuing.

Steps the model marks `requires_confirmation` pop a dialog and wait for you before running. There
is also an OCR fallback (`searchScreenText`) for finding a target by its on-screen text when
coordinates aren't reliable, and a running log of every step taken in `actionTracking/`.

## Layout

- `desktop-intelligence/` — the agent. Start at `main.py`.
- `intelligence-tracking/` — an earlier experiment: asking clarifying questions up front and
  breaking a requested action into its parts before doing anything.

## Running it

Needs Python 3.10, an OpenAI API key, and Tesseract installed for the OCR fallback.

```bash
pip install -r requirements.txt
echo "OPENAI_API_KEY=sk-..." > .env
python desktop-intelligence/main.py
```

Run it from the repository root — the paths in `main.py` are relative to it. macOS will ask for
Screen Recording and Accessibility permission the first time, because the agent genuinely does take
over the mouse and keyboard.

The instruction is currently hardcoded at the top of `main()`; uncomment `getUsersInput()` to be
prompted for it instead.

## Known rough edges

- The instruction is hardcoded rather than prompted for by default.
- Paths are relative to the repository root, so it only runs from there.
- Which steps ask for confirmation is decided by the model, not by you, so a step it judges safe
  runs without asking. Watch it while it runs.
- `undo_tag` is part of the plan schema and gets recorded, but nothing ever acts on it — there is
  no rollback.
