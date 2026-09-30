# Inventory keyboard focus provenance

At baseline commit `586b1b08d9be93ed276bdff19760cc0c278dffae`, actual Google
Chrome Tab/Enter selection of D2, D3 and E1 changed the displayed case but left
`document.activeElement` on `BODY`. Pending requests disable inventory buttons;
successful rendering also replaces those buttons. A controlled failed selection
likewise left focus on the body after controls were re-enabled.

The client now captures the focused inventory case and the focus-event generation
before disabling controls. Inventory buttons carry a case ID so the replacement
button can be found without relying on list position. Once the request finishes
and controls are enabled, focus returns to that case only if no later focus event
occurred and focus is still on the body. A successful or rejected selection keeps
the keyboard position. An explicit focus choice while the request is pending
supersedes the saved inventory focus, including when the user subsequently
chooses the page body. The client never restores a superseded focus target.

`python3 focus-check.py --expect fixed` starts a separate CPU-only desk and uses
actual Chrome with `--disable-gpu`. It verifies three repeated Tab/Enter case
selections, a delayed successful response with later keyboard focus on the review
checkbox, a controlled HTTP 409 failure, and a real stale-version 409 after a
second client changes the selection. In the stale case, a later checkbox/body
focus choice remains authoritative.

Separate evidence files are `artifacts/keyboard-focus-failure.json` and
`artifacts/keyboard-focus-fixed.json`. The failure evidence was captured before
the fix and is never overwritten by the script. Existing capture, evaluation,
raw model outputs and frozen source fixtures remain unchanged. No inference or
real-machine operation occurs during these checks.
