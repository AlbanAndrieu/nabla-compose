#!/usr/bin/env python3
"""Find and normalize superfluous quoting in runtime dotenv files, never printing values.

Run as root on TrueNAS (directly or via `ssh truenas 'sudo -n python3 - [--apply]'`).
`--check` (default) lists, per file, the key names whose line Docker Compose and our
line parsers read differently: a quoted value followed by an inline comment, quotes a
bare value does not need, or a line Compose itself would read ambiguously (malformed).
`--apply` rewrites only fixable lines to `KEY=value` (bare when safe, single-quoted
otherwise), moves an inline comment to its own line above, keeps a private 0600
backup and replaces the file atomically after proving every value is unchanged.
Malformed lines are reported and left byte-identical for an operator.
"""
import argparse
import datetime
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path("/mnt/cpool/secrets/runtime")
SAFE_BARE = re.compile(r"[A-Za-z0-9_./:@%+,=-]+")
ASSIGNMENT = re.compile(r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def dotenv_value(raw):
    """Value as Docker Compose reads it: one quoted string, or bare text up to ` #`.

    None when Compose could read the line differently (unterminated quote, text
    after the closing quote, backslash escapes): callers fail closed.
    """
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        rest = raw[end + 1:].lstrip() if end > 0 else "?"
        if (rest and not rest.startswith("#")) or "\\" in raw[1:end]:
            return None
        return raw[1:end]
    return re.split(r"\s+#", raw, maxsplit=1)[0].rstrip()


def inline_comment(raw):
    """Inline comment text after the value, without the `#`, or None."""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        tail = raw[raw.find(raw[0], 1) + 1:].strip()
        return tail[1:].strip() if tail.startswith("#") else None
    match = re.search(r"\s+#(.*)$", raw)
    return match.group(1).strip() if match else None


def literal(value):
    """Shortest form Compose reads back unchanged, or None when it needs review."""
    if SAFE_BARE.fullmatch(value):
        return value
    if "'" in value or "\\" in value or "\n" in value:
        return None
    return "'" + value + "'"


def normalize(text):
    """Return (new_text, findings) where findings is [(key, issue)]; values untouched."""
    lines, findings = [], []
    for line in text.splitlines():
        match = ASSIGNMENT.match(line)
        if not match:
            lines.append(line)
            continue
        prefix, key, raw = match.groups()
        value = dotenv_value(raw)
        shortest = literal(value) if value is not None else None
        if shortest is None:
            if raw.strip()[:1] in ("'", '"') or value is None:
                findings.append((key, "malformed" if value is None else "needs_review"))
            lines.append(line)
            continue
        comment = inline_comment(raw)
        canonical = f"{prefix}{key}={shortest}"
        if comment is None and line.rstrip() == canonical:
            lines.append(line)
            continue
        findings.append((key, "inline_comment" if comment is not None else "unnecessary_quotes"))
        if comment:
            lines.append(f"{prefix[:len(prefix) - len(prefix.lstrip())]}# {comment}")
        lines.append(canonical)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), findings


def values(text):
    result = {}
    for line in text.splitlines():
        match = ASSIGNMENT.match(line)
        if match:
            result[match.group(2)] = dotenv_value(match.group(3))
    return result


def atomic_write(path, data, mode, uid, gid):
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        os.fchown(fd, uid, gid)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def runtime_files(root=ROOT):
    return sorted(p for p in root.glob("*/.env*")
                  if p.is_file() and not p.is_symlink() and ".bak" not in p.name and not p.name.endswith(".tmp"))


def run(apply, root=ROOT, now=None):
    pending = 0
    for path in runtime_files(root):
        text = path.read_text(encoding="utf-8")
        new_text, findings = normalize(text)
        if not findings:
            continue
        fixable = [f for f in findings if f[1] in ("inline_comment", "unnecessary_quotes")]
        for key, issue in findings:
            print(f"{path} {key} {issue}")
        if apply and fixable:
            if values(new_text) != values(text):
                print(f"{path} result=refused_values_would_change")
                pending += len(findings)
                continue
            stat = path.stat()
            stamp = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
            atomic_write(path.with_name(f"{path.name}.bak-{stamp}"), text, 0o600, stat.st_uid, stat.st_gid)
            atomic_write(path, new_text, stat.st_mode & 0o777, stat.st_uid, stat.st_gid)
            print(f"{path} result=normalized lines={len(fixable)}")
            pending += len(findings) - len(fixable)
        else:
            pending += len(findings)
    print(f"dotenv_quoting_pending={pending}")
    return 1 if pending else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    if args.root == ROOT and os.geteuid() != 0:
        print("privileges=root_required")
        return 2
    return run(args.apply, args.root)


if __name__ == "__main__":
    sys.exit(main())
