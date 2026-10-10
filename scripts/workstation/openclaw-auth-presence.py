#!/usr/bin/env python3
"""Read-only OpenClaw runtime environment presence check, no secrets emitted.

Inspect only this process's environment. Gateway systemd environment can differ.
"""
from __future__ import annotations

import os

KEYS = ("OPENAI_API_KEY", "LITELLM_API_KEY", "AZURE_OPENAI_API_KEY")
for key in KEYS:
    value = os.environ.get(key, "")
    if not value:
        state = "absent"
    elif value.startswith("${") and value.endswith("}"):
        state = "unexpanded_reference"
    elif value.strip() != value:
        state = "surrounding_whitespace"
    else:
        state = "present"
    print(f"{key}={state}")
print("NOTE: CLI environment is not the gateway systemd environment")
print("NOTE: presence does not prove an API key is valid or routed correctly")
