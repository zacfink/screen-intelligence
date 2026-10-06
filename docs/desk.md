# How `desk` works

`desk` gives Claude Code eyes and hands on the Mac. Claude decides what to do and reads the screen; `desk` only
captures and acts. Every round trip to Claude costs 5–15 seconds, so the goal is to send whole batches and only
look again when something goes wrong.

## The loop, before and after

```mermaid
flowchart LR
  subgraph before[Before: look after almost every step]
    direction TB
    b1[Claude: click] --> b2[screenshot ~1,200 tokens] --> b3[Claude reads it] --> b4[Claude: type] --> b5[screenshot] --> b6[Claude reads it] --> b7[...]
  end
  subgraph after[After: one batch, checked as it runs]
    direction TB
    a1["Claude: run 'click; expect; type; type; click; ui --find Saved'"] --> a2{batch finished?}
    a2 -- yes --> a3[one cheap look, ~40 tokens] --> a4[next batch]
    a2 -- "stopped at step N" --> a5[screenshot only now] --> a6[Claude fixes step N] --> a1
  end
```

## What happens inside one `desk run`

```mermaid
flowchart TD
  start([desk run 'step; step; step']) --> split[Split on ; outside quotes]
  split --> next{Next step}
  next -- click --> move[Move mouse to target, wait 0.15s<br/>so hover effects settle]
  move --> win[Find the window under the cursor]
  win --> snap1[Before frame: that window only,<br/>grey, 640px wide, ~160ms]
  snap1 --> press[Click]
  press --> poll{Window changed?<br/>check every 0.15s, up to 1.5s}
  poll -- "yes (40+ pixels differ)" --> next
  poll -- no --> stop([Stop: step N, click changed nothing])
  next -- expect TEXT --> ax{Label with TEXT in the<br/>accessibility tree within 3s?}
  ax -- yes --> next
  ax -- no --> stop2([Stop: step N, TEXT never appeared])
  next -- type --> paste[Paste via clipboard,<br/>restore old clipboard]
  paste --> next
  next -- "type --keys" --> keys[Real keystrokes<br/>for menus and pickers] --> next
  next -- "key / scroll / wait / ui" --> other[Do it] --> next
  next -- none left --> done([Batch finished])
```

## Why the change check doesn't get fooled

| Noise | How it's handled |
|---|---|
| The terminal next to it (Claude's spinner, scrolling output) | Only the clicked window is compared. |
| Hover highlights on the target | The mouse moves there first, and the "before" frame is taken after the hover. |
| Blinking text caret (~15 px) | A change needs 40+ pixels. An opened form or menu is thousands. |
| Menu-bar clock | Only matters when no window is under the click (Dock, desktop), and then the menu bar is blanked. |

## What it catches, and what it doesn't

```mermaid
flowchart LR
  c1[Click missed the button] --> caught[Caught by the change check]
  c2[Form or modal never opened] --> caught
  c3[Click only focused the window] --> caught
  c4[The wrong thing opened] --> exp[Caught by expect]
  c5[Page went somewhere unexpected] --> exp
  c6[Dropdown picked the wrong item] --> look[Caught by the final look]
  c7[Something opened in a different window] --> look
```

A very small change (a single checkbox tick) can read as "changed nothing." That stops the batch, which is the safe
way to be wrong: Claude takes a screenshot instead of carrying on blind.

## Safety around all of it

```mermaid
flowchart LR
  call[Any desk click/type/key/run] --> idle{Acted in the<br/>last 5 minutes?}
  idle -- no --> warn[macOS notification + Ping,<br/>3-second pause] --> act[Act]
  idle -- yes --> act
  act --> moved{Cursor where desk<br/>left it after the step?}
  moved -- yes --> nextstep[Next step]
  moved -- "no: you moved it" --> yours([Stop cleanly: the step finished,<br/>the rest of the batch doesn't run])
  act --> abort[Slam the cursor into a<br/>screen corner to abort instantly]
```

Moving the mouse yourself is the gentle stop: `desk` finishes the step it's on, then hands the mouse back. Claude
never moves the cursor between steps, so any move there is you. The check costs well under a millisecond per step.
The corner slam is the emergency stop, and it can interrupt mid-step.

Submitting, sending, buying and deleting are still one click at a time, after asking in chat.

## Costs

| | Time | Tokens |
|---|---|---|
| Change check per click | ~0.3–1.5 s | 0 |
| `expect` | ≤ 3 s | 0 |
| `ui --find` look | < 1 s | ~40 |
| Screenshot look | ~1 s | ~1,200 |
| One Claude round trip | 5–15 s | the screenshot plus reasoning |

Today a LinkedIn "add project" form took about 6 round trips. Batched with these checks it should take about 2 (an estimate, not yet measured).
