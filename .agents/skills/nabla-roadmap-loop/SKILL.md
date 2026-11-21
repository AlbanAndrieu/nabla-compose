---
name: nabla-roadmap-loop
description: Advance every Nabla roadmap fast in owner-approved homelab sprint mode. Implement, apply, deploy and restart without per-step approval, one PR per repository, questions only after five full passes, and a reconciliation cycle every third pass.
---

# Nabla roadmap loop

Owner decision (21/11/2026): the homelab holds no critical data and has no
external users. When asked to implement or advance the roadmap, run this loop
instead of stopping for approvals.

## Authority in sprint mode

Do without asking:

- implement items;
- apply OpenTofu/Terragrunt plans;
- run versioned `check` then `apply` scripts on TrueNAS;
- create, redeploy or restart Apps, and update the TrueNAS deployment checkout;
- create the services, Garage keys and GitHub Apps the roadmap needs.

Downtime and the loss of re-creatable data are acceptable.

Still never:

- print or commit a secret;
- bypass a hook, gate or scanner;
- write to `master`, or force-push without an exact lease;
- merge a PR: the owner merges;
- open a new public exposure or weaken authentication without an owner decision;
- destroy Vaultwarden data, `/mnt/cpool/secrets/runtime/`, or the last recovery copy of anything.

A step that needs one of these becomes a parked question. Keep going with the rest.

## One PR per repository

Fold all work into the open PR of each repository: the PR of the checkout's
current branch. With none, create `<type>/roadmap-<YYYYMMDD>`.

1. Replay finished side branches onto that PR branch (`git cherry-pick`). Drop
   commits that `origin/master` already contains.
2. Rebuild conflicting roadmap text with a three-way `git merge-file`, from each
   branch's final version. Never resolve by a line union: it keeps every
   intermediate wording of an evolving bullet.
3. Run the full pre-push gate once on the exact HEAD, then push.
4. Never merge.

## The loop

A pass walks every roadmap:

- `docs/roadmap-portfolio.md`, the cross-repository index;
- `docs/roadmap.md` and the sub-roadmaps it links (`docs/*roadmap*.md`, `docs/pfsense/roadmap.md`, ...);
- the roadmaps of fastapi-sample, nabla-site-alban and nabla-openclaw, for the rows they own.

For each item:

1. Run `git fetch`. Skip what `origin/master` or another session already did.
2. Implement the smallest complete change with its test, and run the L1 test.
3. Apply or deploy it, then observe the result read-only: Gatus, Prometheus,
   `app.query`, `curl`. Record `CODED`, `TESTED`, `DEPLOYED` or `ACCEPTED`,
   with the SHA.
4. If it is blocked by a credential, hardware or an owner decision, add the
   question to `docs/runbooks/<date>-roadmap-pass-blockers.md` and move on.

Ask the parked questions only after five full passes, once, in plain text.

Every third pass, run a reconciliation cycle, in this order:

1. Roadmaps: one row per ID, close done items, merge duplicates, and align the
   sub-roadmaps with the portfolio.
2. Skills and agent instructions: fold the lessons of the passes into the
   matching skill or `AGENTS.md`, and delete what proved wrong.
3. Docs: update the runbooks and READMEs the changes made stale.
4. Refactor: remove the dead code and duplication the passes exposed, with tests.

## Pitfalls the passes hit

- Never edit the clone while the pre-push gate runs: it fails on a dirty
  tree. Run it in the background and work on runtime checks or another
  repository meanwhile.
- Services of one TrueNAS App share one x-nabla `status`; keep an optional
  service on a Compose profile instead (`dsomm-baseline`).
- Root on TrueNAS (`systemd-run`): set `HOME` and pass `safe.directory`
  through `GIT_CONFIG_COUNT/KEY_0/VALUE_0`, or root git refuses the checkout.
- Ansible against TrueNAS: `ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o BatchMode=yes"`
  (no `ControlPersist`) reuses the YubiKey ControlMaster of `~/.ssh/config`.
- Sample's TrueNAS observer needs its diagnostics key:
  `sudo bash scripts/truenas/read-sample-observer.sh [path]` on the host.
- IO pressure: read the txg cadence in `/proc/spl/kstat/zfs/cpool/txgs`
  before blaming the top writer. A txg every second or less means forced
  syncs (overlay copy-up through `O_TMPFILE`, fsync storms); a SMART long test
  on one disk slows every raidz2 read.
- Over `ssh host '…'`, `pkill -f PATTERN` matches the remote shell itself, and
  `sudo tail $(ls …)` waits on stdin when the glob fails: add `< /dev/null`.
- A Compose `tmpfs` mount is `root:700`: chown it in the root entrypoint when
  the process drops privileges (ntopng).
- A consumer that forbids extra fields (Sample's `DeclaredService`) must
  accept a new catalog field and ship before the generator emits it.
- Once only credential-blocked items remain, a pass re-tests the blocker and
  moves on: do not investigate the same item again.

## Keep state outside the context

Track the pass counter, the current item and the parked questions in
`docs/runbooks/<date>-roadmap-loop-state.md` on the PR branch. Update it after
each item: context compaction and reboots lose everything else.

Independent repositories can run in parallel subagents, each on its own
repository's PR.
