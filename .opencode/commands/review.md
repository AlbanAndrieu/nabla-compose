---
description: Review the current diff with the read-only reviewer subagent
agent: build
---

Launch the `reviewer` subagent for the current diff.

Use its findings as evidence, not as automatic edits. Fix only concrete findings
that are within the current PR scope, then run the narrowest relevant local
contract. If there are no actionable findings, leave the diff unchanged.
