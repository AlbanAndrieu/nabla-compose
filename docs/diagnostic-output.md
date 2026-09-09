# Diagnostic output policy

Large read-only checks and diagnostics keep interactive terminal output compact.

## Default behavior

When a supported script is run from an interactive terminal, the detailed
stdout/stderr stream is written to a private report under `/tmp` by default:

```text
/tmp/<script-name>-YYYYmmdd-HHMMSS.XXXXXX.log
```

The wrapper never changes the mode or ownership of an existing shared log
directory such as `/tmp`. It allocates each default report with `mktemp`, so
root and non-root diagnostics cannot collide on a predictable timestamp-only
name.

The report is created mode `0600`. The terminal prints only:

- the script exit code;
- counts of OK / failed / warning / skipped findings;
- at most the last important warning/failure lines;
- the detailed report path.

Example:

```text
📋 audit-app-lifecycle: exit=1 ok=38 failed=2 warnings=1 skipped=4
Key findings:
  ❌ Sentry consumers unhealthy: ...
  ⚠️ OpenRAG ingestion: Docling is not reachable
Detailed report: /tmp/audit-app-lifecycle-20260908-210000.A1b2C3.log
```

CI and other non-interactive executions keep their full output so GitHub Actions
logs remain self-contained.

`scripts/truenas/diagnose-sentry.sh` uses the same shared policy, so its
container inventory, lifecycle jobs and Snuba/Kafka diagnostics stay in the
private detailed report instead of flooding the terminal.

## Overrides

Show the complete output directly in the terminal:

```bash
DIAGNOSTIC_FULL_OUTPUT=1 \
  bash scripts/truenas/audit-app-lifecycle.sh
```

Force compact capture even when stdout is not a TTY:

```bash
DIAGNOSTIC_COMPACT_OUTPUT=1 \
  bash scripts/observability/verify-stack.sh
```

Change the report directory:

```bash
DIAGNOSTIC_LOG_DIR=/tmp/nabla-diag \
  bash scripts/talos/validate-cluster.sh
```

Use one explicit report path:

```bash
DIAGNOSTIC_LOG_FILE=/tmp/talos-check.log \
  bash scripts/talos/validate-cluster.sh
```

Limit how many warning/failure lines are echoed in the terminal summary:

```bash
DIAGNOSTIC_SUMMARY_LINES=5 \
  bash scripts/truenas/audit-app-lifecycle.sh
```

## Covered scripts

The shared wrapper is used by the large TrueNAS lifecycle/performance reports,
security audits, observability verifiers, Talos validators/smokes and
infrastructure preflights/probes. Deployment/bootstrap scripts keep their normal
interactive output because their progress and prompts are part of the action
being performed.
