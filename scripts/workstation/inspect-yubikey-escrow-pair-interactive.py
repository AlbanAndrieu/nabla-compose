#!/usr/bin/env python3
"""Prompt for two existing age escrow paths without leaking them to shell history.

Only metadata (lstat) of the supplied files is examined. Never opens,
decrypts, copies or rewrites the files. Two filesystems != independent media.
"""
from __future__ import annotations

import argparse
import getpass
import importlib.util
import json
import os
from pathlib import Path
import sys

SOURCE = Path(__file__).with_name("inspect-yubikey-recovery-readonly.py")
ACK = "INSPECT_EXISTING_ESCROW_METADATA"


def read_escrow_state(a: Path, b: Path) -> str:
    """Delegate existing symlink-safe stat-only policy. No raw path output."""
    try:
        spec = importlib.util.spec_from_file_location("nabla_escrow_metadata", SOURCE)
        if spec is None or spec.loader is None:
            return "METADATA_INSPECTOR_UNAVAILABLE"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return str(module.escrow_inventory(a, b))
    except (OSError, AttributeError, ValueError, ImportError, TypeError):
        return "METADATA_INSPECTOR_UNAVAILABLE"


def classify_inputs(first: str, second: str) -> str:
    if not isinstance(first, str) or not isinstance(second, str):
        return "INVALID_INPUT"
    if (not first or not second or len(first) > 4096 or len(second) > 4096
            or "\x00" in first + second or "\n" in first + second):
        return "INVALID_INPUT"
    a, b = Path(first), Path(second)
    if not a.is_absolute() or not b.is_absolute() or a.suffix != ".age" or b.suffix != ".age":
        return "INVALID_INPUT"
    if a == b:
        return "SAME_FILE"
    return read_escrow_state(a, b)


def inspect(*, tty: bool, reader=None) -> str:
    if not tty:
        return "INTERACTIVE_TERMINAL_REQUIRED"
    if reader is None:
        reader = getpass.getpass
    try:
        first = reader("Escrow age A (chemin absolu, saisie masquée) : ")
        second = reader("Escrow age B (chemin absolu, saisie masquée) : ")
        return classify_inputs(first, second)
    except (EOFError, KeyboardInterrupt, OSError, UnicodeError):
        return "INPUT_UNAVAILABLE"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    opts = parser.add_mutually_exclusive_group(required=True)
    opts.add_argument("--check", action="store_true")
    opts.add_argument("--inspect", action="store_true")
    parser.add_argument("--acknowledge")
    args = parser.parse_args(argv)
    if args.check and args.acknowledge:
        parser.error("acknowledgment accepted only for --inspect")
    if args.inspect and args.acknowledge != ACK:
        parser.error("explicit metadata-only acknowledgment required")
    state = ("PATHS_NOT_COLLECTED" if args.check else
             inspect(tty=os.isatty(0) and os.isatty(2)))
    print(json.dumps({
        "mode": "EXISTING_ESCROW_PAIR_METADATA_ONLY",
        "status": "NO-GO", "state": state,
        "paths_disclosed": False, "files_opened": False,
        "decryption_attempted": False, "independent_media_verified": False,
        "restoration_verified": False,
        "hardware_mutation_authorized": False,
    }, sort_keys=True))
    return 0 if state in ("PATHS_NOT_COLLECTED",
                           "TWO_FILES_DIFFERENT_FILESYSTEMS_UNVERIFIED") else 3


if __name__ == "__main__":
    sys.exit(main())
