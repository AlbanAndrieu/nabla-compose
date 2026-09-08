# pfSense operator command contract

This file is part of the `pfsense-api-debugging` skill and specializes the command-generation rules for commands copied directly into the interactive pfSense shell.

## Interactive shell invariant

The pfSense operator shell is `csh`/`tcsh`, not Bourne shell. Commands generated for direct copy/paste must therefore be valid when the outer parser is `tcsh`.

A recurring failure mode is a multiline Bourne wrapper such as:

```text
/bin/sh -c '
...
'
```

When pasted interactively, `tcsh` can parse the first physical line before the closing quote arrives and report:

```text
Unmatched '''.
```

Do not generate that form for interactive pfSense diagnostics.

## Required generation rules

1. Prefer one command per fenced code block.
2. Prefer a single physical line per command.
3. Never emit a multiline `/bin/sh -c ' ... '` payload for direct interactive copy/paste.
4. If POSIX shell syntax, pipelines, `2>/dev/null`, `$(...)`, loops, or compound tests are needed, wrap the complete command in a **single physical line**.
5. A one-line `/bin/sh -c "..."` wrapper is suitable when the payload contains no shell variables that the outer `tcsh` could expand.
6. If the inner Bourne command contains `$var`, `${var}` or `$(...)`, prefer a **single-line single-quoted** `/bin/sh -c '...'` payload so `tcsh` does not consume the `$` expressions. The important invariant is one physical line, not avoiding single quotes entirely.
7. For simple commands that do not require Bourne syntax, emit native `csh`/`tcsh`-compatible syntax directly.
8. Avoid trailing backslash continuations in operator-facing commands.
9. Keep diagnostic output bounded with `tail`, targeted `grep`, `sed`, or similarly narrow filters.
10. Never infer that a command failed functionally when the observed error is a shell-parsing error; correct the command form first and rerun the read-only diagnostic.

## Preferred wrapper forms

No inner shell variables:

```csh
/bin/sh -c "grep -Ei 'unbound|resolver|pfblocker' /var/log/system.log 2>/dev/null | tail -200"
```

Compound read-only diagnostic without `$` expansion:

```csh
/bin/sh -c "sysctl kern.ipc.maxsockbuf; grep -nE 'so-sndbuf|so-rcvbuf|num-threads' /var/unbound/unbound.conf || true"
```

Inner Bourne variables or command substitution: keep the whole payload on one physical line and single-quote it:

```csh
/bin/sh -c 'pid=$(pgrep -x unbound | head -1); [ -n "$pid" ] && procstat -b "$pid" || true'
```

Do not split that last form across lines in an interactive pfSense session.

## pfSense service-control invariant

Do not use the generic FreeBSD rc.d wrapper as a substitute for the pfSense service manager when diagnosing pfSense-managed services.

In particular, avoid:

```csh
service unbound onestart
```

That command can launch Unbound with the stock FreeBSD configuration path `/usr/local/etc/unbound/unbound.conf` instead of pfSense's generated resolver configuration under `/var/unbound/unbound.conf`. It can therefore create a misleading runtime that listens only on localhost while the pfSense UI still reports DNS Resolver down.

Prefer the pfSense service playback interface:

```csh
pfSsh.php playback svc restart unbound
```

After service control, validate the exact daemon command line and listeners. The healthy pfSense DNS Resolver instance is expected to use the pfSense-generated configuration and the configured LAN interfaces; a process started with `/usr/local/etc/unbound/unbound.conf` is not proof that the pfSense-managed resolver is healthy.
