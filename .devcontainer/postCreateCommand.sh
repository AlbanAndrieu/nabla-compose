#!/bin/bash
set -euxo pipefail
# Repository tooling is declared in pyproject.toml and locked in uv.lock.
uv sync --frozen
echo "Done!"
