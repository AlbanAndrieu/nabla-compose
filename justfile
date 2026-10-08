# Canonical short commands for local-first repository work.
# This coexists with the legacy Makefile; nothing here calls its default Docker build.
set shell := ["bash", "-euo", "pipefail", "-c"]

# List documented tasks without running any build or deployment.
default:
    @just --list

# Install the existing canonical Git hooks.
hooks:
    mise run hooks

# Show bounded branch/change context and suggested repository skills.
context:
    mise run agent-context

# Cheap Git-only safety gate before dependency/setup work.
preflight:
    mise run agent-preflight

# Fast iterative local-first loop: autofix + changed-file contracts only.
loop:
    mise run agent-loop

# Full local quality gate without publishing.
quality:
    mise run agent-quality

# Apply deterministic local fixes and generated artifacts.
fix:
    mise run agent-fix

# Strict full local publication gate.
pre-push:
    mise run agent-pre-push

# Strict validation without pushing or merging.
publish:
    mise run agent-publish

# Original repository quality gate, kept separate from the agent-first path.
quality-gate:
    mise run quality

# List the bounded experimental Dagger checks; this is not the publication gate.
dagger-list:
    mise run dagger-list

# Run the experimental ShellCheck + Biome Dagger PoC.
dagger-poc:
    mise run dagger-poc

# Test this justfile and the Betterleaks toolchain contracts.
tooling-test:
    python -m unittest tests.test_dev_tooling_contract -v

# Scan current files for secrets; findings are redacted, not sent to providers.
secrets:
    betterleaks dir . --config .gitleaks.toml --redact

# Inspect staged changes only (same target as Pre-commit).
secrets-staged:
    betterleaks git . --pre-commit --staged --config .gitleaks.toml --redact

# Full Git history scan, explicitly opt-in due to cost.
secrets-history:
    betterleaks git . --config .gitleaks.toml --redact

# Legacy Makefile is deliberately retained.
make-help:
    make help
