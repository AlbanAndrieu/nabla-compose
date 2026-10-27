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

# Dependency-free syntax-only fallback for disconnected development (L1, not publication).
offline:
    bash scripts/agent-offline-check.sh

# Fast iterative local-first loop: autofix + changed-file contracts only.
loop:
    mise run agent-loop

# Read-only repository policy check for external skills and TrueNAS/Talos decisions.
# No dependency installation, networking, containers or GitHub Actions.
agent-skills-check:
    python3 -m py_compile scripts/quality/check-agent-skill-precedence.py tests/test_agent_skill_precedence_contract.py
    python3 -m unittest discover -s tests -p 'test_agent_skill_precedence_contract.py' -v
    python3 scripts/quality/check-agent-skill-precedence.py

# Read-only, detailed generator drift report (no secrets or runtime calls).
topology-drift-check:
    bash scripts/quality/python-with-repo-deps.sh scripts/generate-service-topology.py --check

# All three generated contracts checked with the same existing worktree Python.
topology-generators-check:
    bash scripts/quality/python-with-repo-deps.sh scripts/generate-service-topology.py --check
    bash scripts/quality/python-with-repo-deps.sh scripts/generate-service-consumers.py --check
    bash scripts/quality/python-with-repo-deps.sh scripts/generate-catalog-v2-artifacts.py --check

topology-generator-test:
    bash scripts/quality/python-with-repo-deps.sh -m pytest -q tests/test_service_topology_generator.py tests/test_service_consumer_drift_diagnostic.py


# Single-command QA from an isolated worktree: pinned Python, read-only
# generators, unit tests, then canonical local quality gate. Stop on failure.
topology-qa:
    bash scripts/quality/with-worktree-python.sh bash scripts/quality/check-topology-worktree.sh

# Explicit source-of-truth regeneration. Development worktree ONLY.
# Never overwrite TrueNAS bind mounts or unpublished generated artifacts.
topology-artifacts-refresh:
    @test "$(id -u)" -ne 0 || { echo 'BLOCKED: do not regenerate as root' >&2; exit 2; }
    @test "$(pwd -P)" != /mnt/cpool/compose/nabla-compose || { echo 'BLOCKED: canonical TrueNAS checkout' >&2; exit 2; }
    @branch="$(git branch --show-current)"; test -n "$branch" && test "$branch" != master || { echo 'BLOCKED: use isolated feature worktree' >&2; exit 2; }
    @git diff --quiet -- catalog/service-topology.json catalog/services.json catalog/generated apps/homarr/generated apps/autokuma/static/generated-monitors.json apps/gatus/config/config.yml || { echo 'BLOCKED: preserve local generated edits' >&2; exit 2; }
    @git diff --cached --quiet -- catalog/service-topology.json catalog/services.json catalog/generated apps/homarr/generated apps/autokuma/static/generated-monitors.json apps/gatus/config/config.yml || { echo 'BLOCKED: preserve staged generated edits' >&2; exit 2; }
    bash scripts/quality/python-with-repo-deps.sh scripts/generate-service-topology.py
    bash scripts/quality/python-with-repo-deps.sh scripts/generate-service-consumers.py
    bash scripts/quality/python-with-repo-deps.sh scripts/generate-catalog-v2-artifacts.py
    just topology-generators-check

# Offline terminal-safety contracts; does not call Github or TrueNAS.
pr274-local-quality-test:
    bash -n scripts/workstation/run-pr274-local-quality.sh
    python3 -m unittest discover -s tests -p 'test_pr274_local_quality_runner_contract.py' -v

# Read-only Backstage v2 / icon parity check. Pass --site-generated separately
# when the sibling website checkout is available (no network fetch).
catalog-convergence-check:
    python3 -m py_compile scripts/quality/check-site-catalog-convergence.py tests/test_site_catalog_convergence_contract.py
    python3 -m unittest discover -s tests -p 'test_site_catalog_convergence_contract.py' -v
    python3 scripts/quality/check-site-catalog-convergence.py

# Explicit physical read-only OTP2 metadata check on secondary 22916048.
# This proves only slot programmed/empty; NEVER proves HMAC-SHA1 or KeePassXC.
# Status remains NO-GO even when this recipe exits successfully.
yubikey-otp2-secondary-readonly:
    python3 scripts/workstation/inspect-yubikey-recovery-readonly.py --otp2-secondary

# GnuPG Assuan GETINFO only. Uses --no-autostart and never handles secrets.
yubikey-gpg-agent-test:
    python3 -m py_compile scripts/workstation/inspect-gpg-agent-readonly.py tests/test_yubikey_gpg_agent_readonly.py
    python3 -m unittest discover -s tests -p 'test_yubikey_gpg_agent_readonly.py' -v

yubikey-gpg-agent-readonly:
    python3 scripts/workstation/inspect-gpg-agent-readonly.py

# One command: all hermetic YubiKey contract groups, then one public snapshot
# on the secondary only. Never re-runs OTP2/F9/PIV82 hardware reads.
yubikey-diagnostics-all-secondary:
    just yubikey-recovery-test
    just yubikey-applications-test
    just yubikey-workstation-test
    just yubikey-diagnostics-test
    just yubikey-gpg-agent-test
    python3 scripts/workstation/diagnose-yubikey-readonly-batch.py --hardware --serial 22916048 --gpg-agent-probe

# Concurrent software readiness: five hermetic suites + host and GPG probes.
# NO-GO even when all gates PASS; never mutates keys, PAM, SOPS or GPG.
yubikey-parallel-test:
    python3 -m py_compile scripts/workstation/run-yubikey-parallel-readonly.py tests/test_yubikey_parallel_readonly.py
    python3 -m unittest discover -s tests -p 'test_yubikey_parallel_readonly.py' -v

# Host-only: GPG/scdaemon/PCSC process presence, SSH-agent public identities,
# PostgreSQL recovery tool availability. No credentials, signing or hardware.
yubikey-dependencies-test:
    python3 -m py_compile scripts/workstation/inspect-yubikey-dependencies-readonly.py tests/test_yubikey_dependencies_readonly.py
    python3 -m unittest discover -s tests -p 'test_yubikey_dependencies_readonly.py' -v

yubikey-dependencies-readonly:
    python3 scripts/workstation/inspect-yubikey-dependencies-readonly.py

# Synthetic PostgreSQL-only recovery: tests and a non-mutating local image check.
# Requires NABLA_POSTGRES_FIXTURE_IMAGE_SHA256 to reference a cached local image.
yubikey-postgres-fixture-test:
    bash -n scripts/workstation/verify-postgres-fixture-recovery.sh
    python3 -m unittest discover -s tests -p 'test_yubikey_postgres_fixture_recovery.py' -v

# Isolated software-only age/SOPS roundtrip, never uses any real escrow,
# private identity, .sops.yaml or YubiKey; key generated in temp directory.
yubikey-software-recovery-test:
    python3 -m py_compile scripts/workstation/verify-yubikey-software-age-sops-fixture.py tests/test_yubikey_software_age_sops_fixture.py
    python3 -m unittest discover -s tests -p 'test_yubikey_software_age_sops_fixture.py' -v

# Tools presence only, no software crypto and no hardware.
yubikey-software-recovery-check:
    python3 scripts/workstation/verify-yubikey-software-age-sops-fixture.py --check

# Synthetic-only encrypted header parser contracts, no real secret or NFS.
yubikey-escrow-age-header-test:
    python3 -m py_compile scripts/workstation/inspect-yubikey-escrow-age-header.py tests/test_yubikey_escrow_age_header.py
    python3 -m unittest discover -s tests -p 'test_yubikey_escrow_age_header.py' -v

# Stat-only local source preflight. Does NOT read the ciphertext header.
yubikey-escrow-age-header-check:
    python3 scripts/workstation/inspect-yubikey-escrow-age-header.py --check

# Reads only the first 8192 bytes of the existing encrypted file. Does NOT
# decrypt, display recipient arguments, expose secrets, copy or write data.
yubikey-escrow-age-header-inspect:
    python3 scripts/workstation/inspect-yubikey-escrow-age-header.py --inspect --acknowledge INSPECT_EXISTING_ENCRYPTED_AGE_HEADER_ONLY

# Existing SanDisk LUKS2 escrow: identify UUID from redacted lsblk metadata.
# No USB unlock, age identity read, decryption, mount or mutation.
yubikey-escrow-usb-status:
    python3 scripts/workstation/diagnose-age-escrow-usb-presence.py --check

# Synthetic USB discovery contracts. No real USB, LUKS, age key or sudo used.
yubikey-escrow-usb-test:
    python3 -m py_compile scripts/workstation/diagnose-age-escrow-usb-presence.py tests/test_age_escrow_usb_presence.py
    python3 -m unittest discover -s tests -p 'test_age_escrow_usb_presence.py' -v

# Original SanDisk MUST already be physically connected and LUKS unlocked.
# Only inspect metadata of expected recovery age identity on the known ext4.
yubikey-escrow-usb-identity-check:
    python3 scripts/workstation/inspect-age-escrow-usb-identity.py --check

# Synthetic-only metadata gate (never reads a real USB age identity).
yubikey-escrow-usb-identity-test:
    python3 -m py_compile scripts/workstation/inspect-age-escrow-usb-identity.py tests/test_age_escrow_usb_identity_metadata.py
    python3 -m unittest discover -s tests -p 'test_age_escrow_usb_identity_metadata.py' -v

# Legacy existing LUKS UUID script, check-only mode; may display lsblk data.
# Prefer the redacted yubikey-escrow-usb-status recipe for routine triage.
yubikey-escrow-usb-legacy-check:
    bash scripts/workstation/manage-age-escrow-usb.sh --luks-uuid 3742c7b9-ccb7-4b5e-b1db-18bcf916c548 --check

# Private terminal prompts for two existing .age backups. Does not print paths,
# read data, decrypt, require USB, or assert physical independence.
yubikey-escrow-pair-test:
    python3 -m py_compile scripts/workstation/inspect-yubikey-escrow-pair-interactive.py tests/test_yubikey_escrow_pair_interactive.py
    python3 -m unittest discover -s tests -p 'test_yubikey_escrow_pair_interactive.py' -v

# No paths collected or files accessed.
yubikey-escrow-pair-check:
    python3 scripts/workstation/inspect-yubikey-escrow-pair-interactive.py --check

# Auto-discover matching *.age basenames only in known local source and
# mounted-backup directories. Read-only stat checks, no paths printed.
yubikey-escrow-pair-discover:
    python3 scripts/workstation/inspect-yubikey-escrow-pair-interactive.py --discover

# Report only directory availability, bounded age-file counts and whether the
# effective HOME matches the current account. No filenames or file contents.
yubikey-escrow-pair-diagnose:
    python3 scripts/workstation/inspect-yubikey-escrow-pair-interactive.py --diagnose

# Validate TrueNAS NFS visibility contracts without contacting workstation
# mounts, archive data, SSH services, or real credentials.
yubikey-escrow-nfs-test:
    python3 -m py_compile scripts/workstation/inspect-yubikey-escrow-nfs-server.py tests/test_yubikey_escrow_nfs_server.py
    python3 -m unittest discover -s tests -p 'test_yubikey_escrow_nfs_server.py' -v

# Inspect mount-source identity and local age basename metadata only.
# No remote network access.
yubikey-escrow-nfs-check:
    python3 scripts/workstation/inspect-yubikey-escrow-nfs-server.py --check

# Optional server-side read-only metadata query via existing SSH credentials;
# enforces known_hosts; no password prompt, key, age decryption or write.
yubikey-escrow-nfs-probe:
    python3 scripts/workstation/inspect-yubikey-escrow-nfs-server.py --probe --ssh-target albandrieu@172.17.0.24 --acknowledge INSPECT_NFS_SERVER_METADATA_ONLY

# Snapshot history check: 3 dataset-level roots, 32 snapshots per root per
# page, at most 1024 directory entries inventoried per root per probe.
# No archive content read, no write, no privileged ZFS command.
yubikey-escrow-history-test:
    python3 -m py_compile scripts/workstation/inspect-yubikey-escrow-nfs-history.py tests/test_yubikey_escrow_nfs_history.py
    python3 -m unittest discover -s tests -p 'test_yubikey_escrow_nfs_history.py' -v

# Local preflight only: no SSH, ZFS queries, age reads or hardware access.
yubikey-escrow-history-check:
    python3 scripts/workstation/inspect-yubikey-escrow-nfs-history.py --check

# Contracts only. Runs a simulated write on a temporary local directory,
# never real NFS, existing backup or YubiKey.
yubikey-escrow-copy-test:
    python3 -m py_compile scripts/workstation/create-yubikey-escrow-nfs-copy.py tests/test_yubikey_escrow_nfs_copy.py
    python3 -m unittest discover -s tests -p 'test_yubikey_escrow_nfs_copy.py' -v

# Metadata-only check; does not open archive contents or create files.
# No automatic "copy-run" recipe: writing requires a separately supervised
# explicit command documented in the recovery runbook.
yubikey-escrow-copy-check:
    python3 scripts/workstation/create-yubikey-escrow-nfs-copy.py --check

# Existing age escrow postcopy contracts only. Never touches the real files.
yubikey-escrow-postcopy-test:
    python3 -m py_compile scripts/workstation/verify-yubikey-escrow-nfs-postcopy.py tests/test_yubikey_escrow_nfs_postcopy.py
    python3 -m unittest discover -s tests -p 'test_yubikey_escrow_nfs_postcopy.py' -v

# Metadata-only gate: no encrypted data reads, no SSH, no writes.
yubikey-escrow-postcopy-check:
    python3 scripts/workstation/verify-yubikey-escrow-nfs-postcopy.py --check

# Explicitly rereads ciphertext and checks TrueNAS visibility via read-only
# SSH. Does not prove NFSv4 ACL or age/SOPS restoration.
yubikey-escrow-postcopy-verify:
    python3 scripts/workstation/verify-yubikey-escrow-nfs-postcopy.py --verify --acknowledge RECHECK_EXISTING_AGE_ESCROW_CIPHERTEXT_AND_TRUENAS

# TrueNAS native ACL metadata inspection, synthetic-only test.
yubikey-escrow-acl-test:
    python3 -m py_compile scripts/workstation/inspect-yubikey-escrow-truenas-acl.py tests/test_yubikey_escrow_truenas_acl.py
    python3 -m unittest discover -s tests -p 'test_yubikey_escrow_truenas_acl.py' -v

# Check expected NFS mount and unique encrypted source file; no SSH.
yubikey-escrow-acl-check:
    python3 scripts/workstation/inspect-yubikey-escrow-truenas-acl.py --check

# Read native ACL metadata via TrueNAS filesystem.getacl over trusted SSH.
# Never prints raw ACL, account identifiers or encrypted bytes.
yubikey-escrow-acl-probe:
    python3 scripts/workstation/inspect-yubikey-escrow-truenas-acl.py --probe --acknowledge INSPECT_EXISTING_TRUENAS_AGE_ESCROW_ACL_READONLY

# Explicit supervised read-only TrueNAS snapshot metadata inventory via SSH.
# Does NOT use sudo/zfs CLI, restore, copy, decrypt, or export private names.
yubikey-escrow-history-probe:
    python3 scripts/workstation/inspect-yubikey-escrow-nfs-history.py --probe --acknowledge INSPECT_AGE_ESCROW_ZFS_HISTORY_ONLY

# Continue to the next bounded window, e.g.:
# just yubikey-escrow-history-page 1
# Page 0..31, lexicographic snapshot-name order (not chronological).
yubikey-escrow-history-page page:
    python3 scripts/workstation/inspect-yubikey-escrow-nfs-history.py --probe --page {{page}} --acknowledge INSPECT_AGE_ESCROW_ZFS_HISTORY_ONLY

# Synthetic contracts only, never touch real backups or YubiKeys.
yubikey-escrow-compare-test:
    python3 -m py_compile scripts/workstation/compare-yubikey-escrow-pair-readonly.py tests/test_yubikey_escrow_pair_compare.py
    python3 -m unittest discover -s tests -p 'test_yubikey_escrow_pair_compare.py' -v

# No backup read, no device probe.
yubikey-escrow-compare-check:
    python3 scripts/workstation/compare-yubikey-escrow-pair-readonly.py --check

# Explicitly READ two existing encrypted backups, compare byte-for-byte,
# never print contents or digests, never decrypt or change anything.
yubikey-escrow-compare-run:
    python3 scripts/workstation/compare-yubikey-escrow-pair-readonly.py --compare --acknowledge COMPARE_EXISTING_ENCRYPTED_ESCROWS

# Optional: manual pairing with two hidden TTY prompts when automatic
# discovery misses. Same metadata gate, no decrypted content or writes.
yubikey-escrow-compare-manual:
    python3 scripts/workstation/compare-yubikey-escrow-pair-readonly.py --compare-manual --acknowledge COMPARE_EXISTING_ENCRYPTED_ESCROWS

# Explicitly request private local paths via hidden interactive TTY prompts.
# Never reads content or proves decryption. Returns NO-GO even on success.
yubikey-escrow-pair-inspect:
    python3 scripts/workstation/inspect-yubikey-escrow-pair-interactive.py --inspect --acknowledge INSPECT_EXISTING_ESCROW_METADATA

# Explicit synthetic test with disposable age key and JSON only.
yubikey-software-recovery-run:
    python3 scripts/workstation/verify-yubikey-software-age-sops-fixture.py --run --acknowledge SYNTHETIC_SOFTWARE_ONLY

yubikey-postgres-fixture-check:
    bash scripts/workstation/verify-postgres-fixture-recovery.sh --check

# Opt-in: ephemeral container, no network, no ports, no production backup.
yubikey-postgres-fixture-run:
    bash scripts/workstation/verify-postgres-fixture-recovery.sh --run --acknowledge SYNTHETIC_ONLY

# Five YubiKey backup workstreams prepared in parallel; NO configuration writes.
yubikey-backup-five-test:
    python3 -m py_compile scripts/workstation/prepare-yubikey-backup-five.py tests/test_yubikey_backup_five_workstreams.py
    python3 -m unittest discover -s tests -p 'test_yubikey_backup_five_workstreams.py' -v

yubikey-backup-five-readonly:
    python3 scripts/workstation/prepare-yubikey-backup-five.py

# A single 22916048 must be connected; hardware metadata only, after host checks.
yubikey-backup-five-secondary-readonly:
    python3 scripts/workstation/prepare-yubikey-backup-five.py --secondary-public-inventory

# SSH FIDO backup enrollment on workstation only. Never touches PIV, OTP2,
# existing SSH keys, authorized_keys, hosts or SOPS. Card serial checked first.
yubikey-backup-ssh-test:
    python3 -m py_compile scripts/workstation/enroll-yubikey-backup-ssh-fido2.py tests/test_yubikey_backup_ssh_fido2_enrollment.py
    python3 -m unittest discover -s tests -p 'test_yubikey_backup_ssh_fido2_enrollment.py' -v

yubikey-backup-ssh-check:
    python3 scripts/workstation/enroll-yubikey-backup-ssh-fido2.py --check

# Offline contracts for existing key only; never generate another SSH credential.
yubikey-backup-ssh-signature-test:
    python3 -m py_compile scripts/workstation/verify-yubikey-backup-ssh-fido2-signature.py tests/test_yubikey_backup_ssh_fido2_signature.py
    python3 -m unittest discover -s tests -p 'test_yubikey_backup_ssh_fido2_signature.py' -v

# Public key fingerprint/permissions only. No USB, no signing.
yubikey-backup-ssh-signature-check:
    python3 scripts/workstation/verify-yubikey-backup-ssh-fido2-signature.py --check

# Explicit local fixture sign + verify, supervised PIN/passphrase/touch.
# Does not authenticate to any server or change existing SSH keys.
yubikey-backup-ssh-signature-run:
    python3 scripts/workstation/verify-yubikey-backup-ssh-fido2-signature.py --sign --acknowledge SIGN_EXISTING_FIDO2_BACKUP_22916048

# Explicit interactive hardware enrollment; no auto-retry or overwrites.
yubikey-backup-ssh-enroll:
    python3 scripts/workstation/enroll-yubikey-backup-ssh-fido2.py --enroll --acknowledge ENROLL_SSH_FIDO2_BACKUP_22916048

# OpenPGP public transport only. --probe may auto-start scdaemon (opt-in).
yubikey-backup-openpgp-test:
    python3 -m py_compile scripts/workstation/probe-yubikey-backup-openpgp.py tests/test_yubikey_backup_openpgp_probe.py
    python3 -m unittest discover -s tests -p 'test_yubikey_backup_openpgp_probe.py' -v

yubikey-backup-openpgp-check:
    python3 scripts/workstation/probe-yubikey-backup-openpgp.py --check

# Single backup YubiKey and interactive TTY required, no PIN or private keys.
yubikey-backup-openpgp-probe:
    python3 scripts/workstation/probe-yubikey-backup-openpgp.py --probe --acknowledge QUERY_OPENPGP_BACKUP_22916048

yubikey-parallel-host-readonly:
    python3 scripts/workstation/run-yubikey-parallel-readonly.py

# Public inventory only; a single secondary must be attached. Device access
# follows the parallel host gates and NEVER runs concurrently with another probe.
yubikey-parallel-secondary-readonly:
    python3 scripts/workstation/run-yubikey-parallel-readonly.py --secondary

# One-shot read-only snapshot. Never asks PIN, challenge, writes or decrypts.
yubikey-diagnostics-test:
    python3 -m py_compile scripts/workstation/diagnose-yubikey-readonly-batch.py tests/test_yubikey_readonly_batch.py
    python3 -m unittest discover -s tests -p 'test_yubikey_readonly_batch.py' -v

yubikey-diagnostics-host-readonly:
    python3 scripts/workstation/diagnose-yubikey-readonly-batch.py

yubikey-diagnostics-secondary-readonly:
    python3 scripts/workstation/diagnose-yubikey-readonly-batch.py --hardware --serial 22916048

yubikey-diagnostics-primary-readonly:
    python3 scripts/workstation/diagnose-yubikey-readonly-batch.py --hardware --serial 23501671

# Public applet/PIV metadata only. Connect exactly one selected YubiKey.
# These observations NEVER authorize provisioning, PIN input, OTP challenge or reset.
yubikey-applications-secondary-readonly:
    python3 scripts/workstation/inspect-yubikey-applications-readonly.py --serial 22916048

yubikey-applications-primary-readonly:
    python3 scripts/workstation/inspect-yubikey-applications-readonly.py --serial 23501671

# Local tool and file-metadata readiness; never opens secrets or connects a token.
yubikey-workstation-readonly:
    python3 scripts/workstation/inspect-yubikey-workstation-readonly.py

yubikey-workstation-test:
    python3 -m py_compile scripts/workstation/inspect-yubikey-workstation-readonly.py tests/test_yubikey_workstation_readonly.py
    python3 -m unittest discover -s tests -p 'test_yubikey_workstation_readonly.py' -v

# No device required; hermetic allowlist, transport and metadata contracts.
yubikey-applications-test:
    python3 -m py_compile scripts/workstation/inspect-yubikey-applications-readonly.py tests/test_yubikey_applications_readonly.py
    python3 -m unittest discover -s tests -p 'test_yubikey_applications_readonly.py' -v

# Offline, no-hardware YubiKey recovery contracts (stdlib only).
yubikey-recovery-test:
    python3 -m py_compile scripts/workstation/inspect-yubikey-recovery-readonly.py tests/test_yubikey_recovery_readonly.py tests/test_yubikey_pr274_readonly_runner.py
    bash -n scripts/workstation/run-age-yubikey-pr274-readonly.sh
    python3 -m unittest discover -s tests -p 'test_yubikey_recovery_readonly.py' -v
    python3 -m unittest discover -s tests -p 'test_yubikey_pr274_readonly_runner.py' -v

# Full local quality gate without publishing. Invoke the canonical checker
# directly to avoid outdated TrueNAS mise auto-lock/download side effects.
quality:
    bash scripts/quality/with-worktree-python.sh bash scripts/agent-quality-gate.sh

# Apply deterministic local fixes and generated artifacts.
fix:
    mise run agent-fix

# Strict full local publication gate.
pre-push:
    mise run agent-pre-push

# Strict validation without pushing or merging.
publish:
    mise run agent-publish

# Read-only post-reboot FastAPI/TrueNAS dependency orchestration.
truenas-fastapi-check:
    python3 scripts/truenas/diagnose-fastapi-integrations.py

# Fast, offline manifest hygiene gate, including duplicate hooks/repos.
# Mirrors Bababou's local-first workflow; does not install hooks or start CI.
precommit-config-test:
    python3 -m py_compile scripts/quality/check-precommit-config.py
    python3 scripts/quality/check-precommit-config.py
    python3 -m pytest -q tests/test_precommit_integrity.py

# Bababou parity: offline local quality-gate contracts, not hosted Actions.
quality-contracts-test:
    bash -n scripts/quality-gate.sh
    python3 -m py_compile scripts/quality/check-precommit-config.py
    python3 scripts/quality/check-precommit-config.py
    python3 -m pytest -q tests/test_precommit_integrity.py tests/test_quality_gate_content_scope.py

# Validate Anthropic-first Hermes route and scoped LiteLLM budgets offline.
# No upstream LLM call, TrueNAS restart, API key or Actions minutes.
hermes-opus-routing-test:
    python3 -m py_compile scripts/truenas/check-litellm-hermes-credentials.py
    python3 -m pytest -q tests/test_hermes_opus_routing_contract.py tests/test_hermes_litellm_budget_contract.py tests/test_hermes_contract.py tests/test_hermes_preflight.py tests/test_hermes_cloud_credential_preflight.py

# Offline model alias contract and optional authenticated TrueNAS inventory.
openclaw-truenas-model-keys-test:
    python3 -m py_compile scripts/workstation/ensure-openclaw-truenas-litellm-tunnel.py scripts/workstation/preflight-truenas-litellm-openclaw.py scripts/workstation/openclaw-route-metadata.py tests/test_openclaw_truenas_ssh_tunnel.py tests/test_truenas_litellm_openclaw_preflight.py tests/test_openclaw_route_metadata.py
    python3 -m unittest discover -s tests -p 'test_truenas_litellm_openclaw_preflight.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_route_metadata.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_truenas_ssh_tunnel.py' -v

# Always safe and offline: compare intended model names to git-declared TrueNAS routing.
openclaw-truenas-model-keys-check:
    python3 scripts/workstation/preflight-truenas-litellm-openclaw.py

# Opt-in: requires existing SSH tunnel 127.0.0.1:14000 to TrueNAS LiteLLM.
# Never transmit an admin key over plaintext LAN: only local encrypted transport.
openclaw-truenas-model-keys-tunnel:
    python3 scripts/workstation/preflight-truenas-litellm-openclaw.py --tunnel

# One-time hidden TTY input, no exported master credential; requires pre-existing SSH tunnel.
openclaw-truenas-model-keys-tunnel-prompt:
    python3 scripts/workstation/preflight-truenas-litellm-openclaw.py --tunnel --prompt-admin

# Owner-only verified SSH forward; never starts a duplicate or kills a process.
openclaw-truenas-tunnel-check:
    python3 scripts/workstation/ensure-openclaw-truenas-litellm-tunnel.py --check

# Create a tunnel only when 14000 is free and the SSH alias targets TrueNAS:9922.
# Reuse a verifiable existing ssh -L and never expose a credential.
openclaw-truenas-tunnel-ensure:
    python3 scripts/workstation/ensure-openclaw-truenas-litellm-tunnel.py --ensure

# Explicitly choose the existing named variable, never expose its contents.
# The operator must first confirm LITELLM_MASTER_KEY belongs to TrueNAS.
openclaw-truenas-model-keys-tunnel-existing-master:
    python3 scripts/workstation/preflight-truenas-litellm-openclaw.py --tunnel --master-env LITELLM_MASTER_KEY

# Dedicated TrueNAS environment name is preferred when available.
openclaw-truenas-model-keys-tunnel-dedicated:
    python3 scripts/workstation/preflight-truenas-litellm-openclaw.py --tunnel --master-env LITELLM_TRUENAS_MASTER_KEY

# No API call, SSH requirement, secret readback, or network access.
openclaw-truenas-master-env-check:
    python3 scripts/workstation/preflight-truenas-litellm-openclaw.py --master-env LITELLM_TRUENAS_MASTER_KEY --check-master-env

# Explicit exceptional read-only GETs for a true non-sk master key.
# Never use if format check says looks_like_reference, empty or invalid.
openclaw-truenas-model-keys-tunnel-dedicated-nonstandard:
    python3 scripts/truenas/dispatch-openclaw-litellm-keys.py --mode status



# Read-only 429 attribution: OpenClaw auth cooldown vs LiteLLM budget/key.
# No chat, embeddings, RPM reset, systemd restart or secret disclosures.
openclaw-429-triage-test:
    python3 -m py_compile scripts/workstation/diagnose-openclaw-litellm-429.py tests/test_openclaw_litellm_429_diagnostic.py scripts/workstation/diagnose-openclaw-model-cooldowns.py tests/test_openclaw_model_cooldowns.py
    python3 -m unittest discover -s tests -p 'test_openclaw_litellm_429_diagnostic.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_model_cooldowns.py' -v

# Inference-free. CLI models status MAY query provider usage metadata.
# --admin only queries hashed virtual key metadata on loopback LiteLLM.
openclaw-429-triage:
    python3 scripts/workstation/diagnose-openclaw-model-cooldowns.py
    python3 scripts/workstation/diagnose-openclaw-litellm-429.py --admin
    python3 scripts/workstation/openclaw-route-metadata.py

# Lightweight path when LiteLLM master key is not exported.
openclaw-429-triage-no-admin:
    python3 scripts/workstation/diagnose-openclaw-model-cooldowns.py
    python3 scripts/workstation/diagnose-openclaw-litellm-429.py
    python3 scripts/workstation/openclaw-route-metadata.py

# Job definition audit only: GET cron metadata, never run/edit the job or models.
# A nonzero check is expected until the live job has an explicit integer --top.
openclaw-digest-top-test:
    python3 -m py_compile scripts/workstation/diagnose-openclaw-digest-top.py tests/test_openclaw_digest_top.py
    python3 -m unittest discover -s tests -p 'test_openclaw_digest_top.py' -v

openclaw-digest-top-check:
    python3 scripts/workstation/diagnose-openclaw-digest-top.py

# Static non-secret digest manifest: no cron creation, delivery or inference.
openclaw-digest-gitops-test:
    python3 -m unittest discover -s tests -p 'test_openclaw_digest_gitops_policy.py' -v

# Native cron-agent session cleanup; report is redacted, no direct SQLite edits.
openclaw-cron-session-maintenance-test:
    python3 -m py_compile scripts/workstation/openclaw-cron-session-maintenance.py tests/test_openclaw_cron_session_maintenance.py
    python3 -m unittest discover -s tests -p 'test_openclaw_cron_session_maintenance.py' -v

openclaw-cron-session-maintenance-check:
    python3 scripts/workstation/openclaw-cron-session-maintenance.py --check

# Opt-in, native Gateway maintenance; only agent 'cron', not the main agent.
openclaw-cron-session-maintenance-apply:
    python3 scripts/workstation/openclaw-cron-session-maintenance.py --apply

# Read-only cron-parent session catalog: no transcript output or SQLite mutation.
openclaw-cron-parent-test:
    python3 -m py_compile scripts/workstation/diagnose-openclaw-cron-parent.py tests/test_openclaw_cron_parent.py
    python3 -m unittest discover -s tests -p 'test_openclaw_cron_parent.py' -v

openclaw-cron-parent-check:
    python3 scripts/workstation/diagnose-openclaw-cron-parent.py

# Historical schedules retained as a reviewed proposal; heartbeat stays dormant.
openclaw-legacy-heartbeat-test:
    python3 -m unittest discover -s tests -p 'test_openclaw_heartbeat_legacy_recovery_contract.py' -v

# Local-only: inventory historical HEARTBEAT copies by metadata, never extract archive.
openclaw-heartbeat-copies-test:
    python3 -m py_compile scripts/workstation/inspect-openclaw-heartbeat-copies.py tests/test_openclaw_heartbeat_copies.py
    python3 -m unittest discover -s tests -p 'test_openclaw_heartbeat_copies.py' -v

openclaw-heartbeat-copies-check:
    python3 scripts/workstation/inspect-openclaw-heartbeat-copies.py --check

# No content reads, no file mode changes. Explicit mode-only apply is separate.
openclaw-heartbeat-modes-test:
    python3 -m py_compile scripts/workstation/secure-openclaw-heartbeat-copies.py tests/test_openclaw_heartbeat_mode_repair.py
    python3 -m unittest discover -s tests -p 'test_openclaw_heartbeat_mode_repair.py' -v

openclaw-heartbeat-modes-check:
    python3 scripts/workstation/secure-openclaw-heartbeat-copies.py --check

# Opt-in permission-only change to owner 0600 on three existing, verified files.
# This never extracts or changes the archive content or Gateway/session state.
openclaw-heartbeat-modes-apply:
    python3 scripts/workstation/secure-openclaw-heartbeat-copies.py --apply

# Read-only legacy git-crypt inventory: never decrypt/copy tracked OpenClaw secrets.
openclaw-nabla-migration-test:
    python3 -m py_compile scripts/workstation/audit-openclaw-nabla-migration.py tests/test_openclaw_nabla_migration_audit.py
    python3 -m unittest discover -s tests -p 'test_openclaw_nabla_migration_audit.py' -v

openclaw-nabla-migration-check:
    python3 scripts/workstation/audit-openclaw-nabla-migration.py --check

# Classify only the known auth error; never disable LiteLLM model authentication.
litellm-workstation-auth-contracts:
    python3 -m py_compile scripts/truenas/diagnose-workstation-litellm-upstream-auth.py tests/test_workstation_litellm_upstream_auth_preflight.py
    python3 -m unittest discover -s tests -p 'test_openrag_litellm_nonbillable_probe_contract.py' -v
    bash scripts/quality/run-pytest-local.sh -q tests/test_litellm_dashboard_auth_failure.py
    python3 -m unittest discover -s tests -p 'test_workstation_litellm_upstream_auth_preflight.py' -v

# TrueNAS-only: no model calls or secret output, no service restart.
litellm-workstation-upstream-auth-check:
    sudo python3 scripts/truenas/diagnose-workstation-litellm-upstream-auth.py --check

# OpenClaw cron SecretRef contract: no Gateway, network, token or stored plan required.
openclaw-cron-secret-plan-test:
    python3 -m py_compile scripts/workstation/diagnose-openclaw-secrets-plan.py scripts/workstation/cutover-openclaw-cron-secret.py tests/test_openclaw_secrets_plan_diagnostic.py tests/test_openclaw_gateway_cron_env_contract.py tests/test_openclaw_cron_secret_cutover.py
    python3 -m unittest discover -s tests -p 'test_openclaw_secrets_plan_diagnostic.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_gateway_cron_env_contract.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_cron_secret_cutover.py' -v

# Plan-only verification for importing the existing cron dotenv secret to a file.
openclaw-cron-file-cutover-check:
    python3 scripts/workstation/cutover-openclaw-cron-secret.py --check

# Explicitly authorized mutation: key file, private backups, native SecretRef apply.
# No Gateway restart, no deletion from dotenv, no paid Actions.
openclaw-cron-file-cutover:
    python3 scripts/workstation/cutover-openclaw-cron-secret.py --apply --reload-gateway

# Native OpenClaw dry-run and redaction. Fail closed if dotenv scrub would occur.
# Separate radio association, IPv4 route, public DNS and local DNS without pfSense mutations.
pfsense-wifi-path-test:
    python3 -m py_compile scripts/workstation/diagnose-wifi-path.py tests/test_workstation_wifi_path.py
    python3 -m unittest discover -s tests -p 'test_workstation_wifi_path.py' -v

pfsense-wifi-path:
    python3 scripts/workstation/diagnose-wifi-path.py --check

# Pure offline regressions: no pfSense access or GitHub Actions.
pfsense-console-test:
    bash -n scripts/pfsense/console.sh
    bash -n scripts/workstation/verify-crowdsec-pfsense.sh
    python3 -m unittest discover -s tests -p 'test_pfsense_console_output.py' -v

# Read-only Netgate 1100 lifecycle evidence: no pfSense mutation or paid CI.
# Read-only generator, generated pool, true nginx children and DNS readiness.
pfsense-php-fpm-check:
    bash scripts/pfsense/reconcile-php-fpm.sh --check

pfsense-php-fpm-test:
    sh -n scripts/security/harden-pfsense-php-fpm.sh
    bash -n scripts/pfsense/reconcile-php-fpm.sh
    python3 -m unittest discover -s tests -p 'test_pfsense_php_fpm_hardening_contract.py' -v
    python3 -m unittest discover -s tests -p 'test_pfsense_php_fpm_reconcile_contract.py' -v

# Controlled PHP-FPM/GUI changes. Explicit confirmation required.
# Keep serial console access; preflight requires healthy Unbound.
pfsense-php-fpm-apply:
    bash scripts/pfsense/reconcile-php-fpm.sh --apply

# Emergency rollback to saved pfSense PHP-FPM generator, independently guarded.
pfsense-php-fpm-restore:
    bash scripts/pfsense/reconcile-php-fpm.sh --restore

# Local-only, no SSH and no paid CI; validates PHP-FPM and Snort/CrowdSec posture.
pfsense-security-capacity-test:
    just pfsense-php-fpm-test
    bash -n scripts/pfsense/audit-posture.sh
    python3 -m unittest discover -s tests -p 'test_pfsense_capacity_posture_contract.py' -v

# Read-only capacity + posture audit; review gates before reducing security coverage.
pfsense-security-capacity-audit:
    bash scripts/pfsense/reconcile-php-fpm.sh --check
    bash scripts/pfsense/diagnose-unbound-restart-cause.sh --check
    bash scripts/pfsense/audit-posture.sh --ssh "${PFSENSE_SSH_TARGET:-home.albandrieu.com}"

# Post-cutover receipt: PHP-FPM profile/worker count, Unbound + historical OOM,
# Snort/DNSBL/CrowdSec posture, then a new instantaneous memory observation.
# This intentionally performs no restart, rebuild, update or configuration write.
pfsense-php-fpm-postcheck:
    just pfsense-security-capacity-audit
    just pfsense-memory-sample

pfsense-unbound-restart-test:
    bash -n scripts/pfsense/diagnose-unbound-restart-cause.sh
    bash -n scripts/pfsense/sample-oom-pressure.sh
    bash -n scripts/pfsense/console.sh
    python3 -m py_compile scripts/pfsense/probe-unbound-lan-dns.py
    python3 -m unittest discover -s tests -p 'test_pfsense_lan_dns_watch.py' -v
    python3 -m unittest discover -s tests -p 'test_pfsense_unbound_restart_cause_contract.py' -v
    python3 -m unittest discover -s tests -p 'test_pfsense_console_output.py' -v
    python3 -m unittest discover -s tests -p 'test_pfsense_oom_sampler_contract.py' -v
    python3 -m unittest discover -s tests -p 'test_pfsense_unbound_snapshot_compare.py' -v
    bash -n scripts/pfsense/capture-unbound-snapshot.sh
    python3 -m unittest discover -s tests -p 'test_pfsense_unbound_snapshot_capture.py' -v

# Lightweight Netgate memory observation, without changing daemon configuration.
pfsense-memory-sample-test:
    bash -n scripts/pfsense/sample-oom-pressure.sh
    python3 -m unittest discover -s tests -p 'test_pfsense_oom_sampler_contract.py' -v

pfsense-memory-sample:
    PFSENSE_OUTPUT=verbose bash scripts/pfsense/sample-oom-pressure.sh --check

# Start manually shortly before the Snort 02:09 scheduled task.
# 13 readings at 15 s intervals span 180 s, one SSH session.
pfsense-memory-window:
    PFSENSE_OUTPUT=verbose bash scripts/pfsense/sample-oom-pressure.sh --check --samples 13 --interval-seconds 15

# One safe read-only SSH capture, persisted in a private workstation directory.
# It prints the exact saved path for use as PFSENSE_BEFORE/PFSENSE_AFTER.
# Workstation-only, bounded A-record probes to explicit pfSense resolver.
# Run from LAN shortly before the next scheduled DNSBL stop/start.
# Caller must choose an actual split-DNS name; no default hidden domain.
pfsense-unbound-lan-dns-watch:
    python3 scripts/pfsense/probe-unbound-lan-dns.py --check --resolver 172.17.0.1 --public-name example.com --private-name "${PFSENSE_PRIVATE_DNS_NAME:?set PFSENSE_PRIVATE_DNS_NAME to a verified LAN-only FQDN}" --private-expected-ip "${PFSENSE_PRIVATE_DNS_EXPECTED_IP:?set PFSENSE_PRIVATE_DNS_EXPECTED_IP to the verified IPv4 A value}" --pihole-resolver 172.17.0.24 --samples 45 --interval-seconds 2 --timeout-seconds 1

pfsense-unbound-lan-dns-test:
    python3 -m py_compile scripts/pfsense/probe-unbound-lan-dns.py
    python3 -m unittest discover -s tests -p 'test_pfsense_lan_dns_watch.py' -v

# CrowdSec central: exercises shell classification with mocked Loki responses.
# Offline only: no Docker, SSH, runtime mutation or GitHub CI.
# CrowdSec central LAPI cutover checks from workstation; no pfSense changes.
# Preflight WARNs while the old engine is intentionally still running.
# Offline contract gate: tests only parser/auth shell syntax, no SSH.
crowdsec-bouncer-config-test:
    bash -n scripts/workstation/verify-crowdsec-pfsense.sh
    sh -n scripts/pfsense/check-central-crowdsec-bouncer.sh
    python3 -m py_compile tests/test_crowdsec_bouncer_url_parser.py
    python3 -m unittest discover -s tests -p 'test_crowdsec_bouncer_url_parser.py' -v
    bash -n scripts/truenas/check-crowdsec-candidate-bouncer.sh
    python3 -m py_compile tests/test_crowdsec_candidate_bouncer_auth.py
    python3 -m unittest discover -s tests -p 'test_crowdsec_candidate_bouncer_auth.py' -v

# On TrueNAS only, sudo/known private runtime secret; no pfSense changes.
crowdsec-candidate-auth-check:
    sudo bash scripts/truenas/check-crowdsec-candidate-bouncer.sh

crowdsec-pfsense-preflight:
    bash scripts/workstation/verify-crowdsec-pfsense.sh --preflight

# Post-cutover only: engine stopped, remote LAPI URL, PF bouncer healthy.
crowdsec-pfsense-accept:
    bash scripts/workstation/verify-crowdsec-pfsense.sh --accept

crowdsec-loki-evidence-test:
    bash -n scripts/truenas/diagnose-crowdsec-cutover.sh
    python3 -m py_compile tests/test_crowdsec_loki_evidence_contract.py
    python3 tests/test_crowdsec_loki_evidence_contract.py -v

# Fail closed on stale/different worktrees: direct execution cannot report
# 0 tests as success when the expected test module is absent.
nexus-private-ingress-test:
    test -f tests/test_nexus_private_ingress_contract.py
    python3 -m py_compile tests/test_nexus_private_ingress_contract.py
    python3 tests/test_nexus_private_ingress_contract.py -v
    test -f tests/test_nexus_haproxy_frontend_readonly.py
    bash -n scripts/workstation/inspect-nexus-haproxy-frontend.sh
    python3 -m py_compile tests/test_nexus_haproxy_frontend_readonly.py
    python3 tests/test_nexus_haproxy_frontend_readonly.py -v
    test -f docs/evidence/pfsense/haproxy-2026-10-27.generated.redacted.cfg
    test -f tests/test_pfsense_haproxy_policy_audit.py
    python3 -m py_compile scripts/pfsense/audit-haproxy-ingress.py tests/test_pfsense_haproxy_policy_audit.py
    python3 tests/test_pfsense_haproxy_policy_audit.py -v
    test -f tests/test_ingress_public_dns_evidence.py
    python3 -m py_compile scripts/ingress/collect-public-dns-evidence.py tests/test_ingress_public_dns_evidence.py
    python3 tests/test_ingress_public_dns_evidence.py -v

# Read-only: public DNS from two independent public recursors.
# Output can be merged into the optional external evidence JSON.
ingress-public-dns-evidence:
    python3 scripts/ingress/collect-public-dns-evidence.py

# Read-only: compare current generated pfSense HAProxy with the reviewed,
# redacted 2026-10-27 baseline. Unverified DNS/Tunnel/PF is NOT success.
pfsense-haproxy-policy-check:
    python3 scripts/pfsense/audit-haproxy-ingress.py --strict

pfsense-haproxy-policy-live:
    python3 scripts/pfsense/audit-haproxy-ingress.py --live

pfsense-unbound-capture:
    bash scripts/pfsense/capture-unbound-snapshot.sh --check

# Compare two saved redacted output files entirely locally. No SSH.
# Set PFSENSE_BEFORE and PFSENSE_AFTER to the operator-controlled report paths.
pfsense-unbound-compare:
    python3 scripts/pfsense/compare-unbound-snapshots.py --before "${PFSENSE_BEFORE:?set PFSENSE_BEFORE}" --after "${PFSENSE_AFTER:?set PFSENSE_AFTER}"

pfsense-unbound-restart-check:
    bash scripts/pfsense/diagnose-unbound-restart-cause.sh --check

# Fast operator entrypoint: includes categorized download failures and file-size warnings.
# This deliberately reuses the single read-only Unbound/pfBlockerNG/Snort collector.
pfsense-feed-pressure-check:
    PFSENSE_OUTPUT=compact bash scripts/pfsense/diagnose-unbound-restart-cause.sh --check

pfsense-unbound-wifi-test:
    bash -n scripts/pfsense/diagnose-pfblocker-unbound-whatsapp.sh
    bash -n scripts/pfsense/audit-posture.sh
    bash -n scripts/workstation/diagnose-whatsapp-web-path.sh
    python3 -m unittest discover -s tests -p 'test_pfsense_console_output.py' -v
    python3 -m unittest discover -s tests -p 'test_pfsense_unbound_whatsapp_contract.py' -v
    python3 -m unittest discover -s tests -p 'test_pfsense_pflow_posture_contract.py' -v
    bash -n scripts/workstation/run-pr274-after-reboot.sh
    python3 -m unittest discover -s tests -p 'test_pr274_worktree_recovery.py' -v

# Read-only Akvorado static metadata preflight. Runtime load remains unverified.
akvorado-metadata-test:
    bash scripts/quality/python-with-repo-deps.sh -m pytest -q tests/test_akvorado_metadata_config.py tests/test_akvorado_static_ifindex_contract.py

akvorado-metadata-check:
    bash scripts/quality/python-with-repo-deps.sh scripts/truenas/check-akvorado-metadata-config.py --check

# Read-only probes run on a workstation that can reach pfSense via SSH.
pfsense-unbound-check:
    bash scripts/pfsense/diagnose-pfblocker-unbound-whatsapp.sh --check

# Read-only WhatsApp Web IPv4/IPv6 edge path, with no browser-session access.
whatsapp-web-path-check:
    bash scripts/workstation/diagnose-whatsapp-web-path.sh --check

# Operator-only: requires private cron-plan.json on the Ubuntu workstation.
openclaw-cron-secret-plan-check:
    python3 scripts/workstation/diagnose-openclaw-secrets-plan.py

# Compare two native dry-runs, with ephemeral owner-private no-scrub plan.
# Read-only for OpenClaw runtime; exit 2 is expected while scrub remains unsafe.
openclaw-cron-secret-plan-compare:
    python3 scripts/workstation/diagnose-openclaw-secrets-plan.py --compare-no-scrub

# Opt-in read-only presence hints from the projected dotenv and current Gateway PID.
# Never proves a restart-safe source; intended exit code is 2.
openclaw-cron-secret-plan-provenance:
    python3 scripts/workstation/diagnose-openclaw-secrets-plan.py --compare-no-scrub --inspect-gateway-env

# Print operator commands only. Does not contact TrueNAS or start migrations.
migration-20261024-commands:
    bash scripts/truenas/finish-migrations-20261024.sh --next-commands

# Explicit local-only consolidation of the five review gates.
# The script stops on first failed recipe; no GitHub Actions or TrueNAS apply.
migration-20261024-local-gates:
    bash scripts/truenas/finish-migrations-20261024.sh --local-gates

# Offline migration, FastAPI LAN collector and Akvorado regressions.
# No TrueNAS mutation or GitHub Actions.
migration-20261024-test:
    bash -n scripts/truenas/finish-migrations-20261024.sh
    bash -n scripts/truenas/diagnose-sentry-consumers.sh
    bash -n scripts/truenas/diagnose-defectdojo.sh
    bash -n scripts/truenas/reconcile-openrag-opensearch-secret.sh
    bash -n scripts/truenas/diagnose-akvorado-config.sh
    bash -n scripts/truenas/diagnose-openrag-startup.sh
    bash -n scripts/truenas/verify-fastapi-lan-probes.sh
    python3 -m pytest -q tests/test_finish_migrations_20261024.py tests/test_sentry_consumers_diagnostic.py tests/test_fastapi_lan_probe_contract.py tests/test_akvorado_flow_deltas.py tests/test_akvorado_flow_diagnostic.py tests/test_akvorado_static_ifindex_contract.py tests/test_akvorado_config_bind_diagnostic.py tests/test_openrag_secret_migration_metadata.py tests/test_openrag_startup_preflight.py tests/test_openrag_opensearch_secret_comparator.py tests/test_defectdojo_diagnostic_contract.py

# Maintained runtime/version review is read-only, no registry or paid Actions.
upgrade-runtime-audit:
    python3 scripts/quality/audit-supported-runtimes.py

# Local-only contracts for platform pins, PHP/Python runtime detection and Talos safety.
upgrade-runtime-test:
    python3 -m py_compile scripts/quality/audit-supported-runtimes.py scripts/talos/preflight-supported-upgrade.py scripts/truenas/audit-live-language-runtimes.py
    python3 -m pytest -q tests/test_supported_runtime_policy.py tests/test_talos_supported_upgrade.py tests/test_live_language_runtime_audit.py

# Inventory running TrueNAS container interpreter patches without image pulls/restarts.
truenas-live-language-audit:
    python3 scripts/truenas/audit-live-language-runtimes.py --check

# Requires authenticated Talos and Kubernetes CLI; this does not upgrade nodes.
talos-upgrade-preflight:
    python3 scripts/talos/preflight-supported-upgrade.py --check

# Fast operator-acknowledged upgrade paths; check prints immutable hashes only.
fast-talos-plan image:
    python3 scripts/talos/fast-batch-upgrade.py --check --installer-image "{{image}}"

fast-truenas-plan scope="applications" parallel="6":
    python3 scripts/truenas/fast-bulk-redeploy-apps.py --check --scope "{{scope}}" --parallel "{{parallel}}"

fast-maintenance-test:
    python3 -m py_compile scripts/talos/fast-batch-upgrade.py scripts/truenas/fast-bulk-redeploy-apps.py
    python3 -m pytest -q tests/test_fast_batch_talos_upgrade.py tests/test_fast_bulk_truenas_redeploy.py

# Read-only, redacted AI service recovery: no secret values, no deployments.
truenas-ai-recovery-check:
    sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check

truenas-ai-recovery-test:
    python3 -m py_compile scripts/truenas/diagnose-ai-secret-recovery.py
    python3 -m pytest -q tests/test_ai_secret_recovery_diagnostic.py

# Functional acceptance: TrueNAS state + Docker health + semantic HTTP/PromQL.
# Fail nonzero if an App is BLOCKED, DEGRADED or UNKNOWN, even when TrueNAS
# app.query returns RUNNING. Use the nonblocking report for status-only review.
truenas-readiness-check:
    sudo python3 scripts/truenas/diagnose-service-readiness.py --check --strict

truenas-readiness-report:
    sudo python3 scripts/truenas/diagnose-service-readiness.py --check

truenas-readiness-test:
    python3 -m py_compile scripts/truenas/diagnose-service-readiness.py
    python3 -m pytest -q tests/test_service_readiness_diagnostic.py tests/test_compact_ops_diagnostics.py tests/test_gatus_api_diagnostic.py tests/test_prometheus_config_access_repair.py tests/test_openrag_dependencies_diagnostic.py tests/test_prometheus_rules_access_repair.py

# Read-only OpenRAG backend/frontend/Langflow/OpenSearch dependency diagnosis.
truenas-openrag-dependencies-check:
    sudo bash scripts/truenas/diagnose-openrag-dependencies.sh --check

truenas-openrag-dependencies-test:
    python3 -m pytest -q tests/test_openrag_dependencies_diagnostic.py tests/test_openrag_startup_preflight.py

# Read-only prerequisites: App lifecycle, root-owned secrets, ZFS corpus and shared endpoints.
truenas-openrag-startup-check:
    sudo bash scripts/truenas/diagnose-openrag-startup.sh --check

truenas-openrag-startup-test:
    bash -n scripts/truenas/diagnose-openrag-startup.sh
    bash -n scripts/truenas/reconcile-openrag-opensearch-secret.sh
    python3 -m unittest discover -s tests -p 'test_openrag_litellm_nonbillable_probe_contract.py' -v
    bash scripts/quality/run-pytest-local.sh -q tests/test_openrag_startup_preflight.py tests/test_openrag_opensearch_secret_comparator.py

# Read-only host preflight; --apply remains a separate, explicit operator action.
truenas-prometheus-config-check:
    sudo bash scripts/truenas/repair-prometheus-config-access.sh --check

# Rule-tree check is read-only; repair demands explicit approval and unchanged count.
truenas-prometheus-rules-check:
    sudo bash scripts/truenas/repair-prometheus-rules-access.sh --check

truenas-prometheus-rules-test:
    bash -n scripts/truenas/repair-prometheus-rules-access.sh
    python3 -m pytest -q tests/test_prometheus_rules_access_repair.py

# Offline TrueNAS restart planning tests. Never contacts TrueNAS or invokes Actions.
# Requires a locally installed pytest; no package install, runner, or deployment.
truenas-catalog-v2-test:
    python3 -m py_compile scripts/truenas/plan-catalog-v2-restart.py scripts/truenas/restart-catalog-v2-apps.py scripts/truenas/catalog_v2_restart_dependencies.py scripts/secrets/inventory_vaultwarden.py
    python3 -m pytest -q tests/test_catalog_v2_restart_plan.py tests/test_catalog_v2_restart_waves.py tests/test_catalog_v2_restart_dependencies.py tests/test_catalog_v2_core_guard.py tests/test_vaultwarden_inventory_contract.py

# Read-only local contracts for Actions usage and budget reporting; no hosted runners.
actions-usage-test:
    python3 -m py_compile scripts/github-actions-usage.py
    python3 -m pytest -q tests/test_github_actions_usage.py

# Original repository quality gate, kept separate from the agent-first path.
quality-gate:
    mise run quality

# Refresh/review dagger.lock explicitly before running the PoC.
dagger-sync:
    mise run dagger-sync

# List the bounded experimental Dagger checks; this is not the publication gate.
dagger-list:
    mise run dagger-list

# Run the experimental ShellCheck + Biome Dagger PoC.
dagger-poc:
    mise run dagger-poc

# Run the native reference checks used for Dagger parity.
dagger-native-parity:
    mise run dagger-native-parity

# Benchmark warm native-vs-Dagger paths without clearing shared caches.
dagger-bench:
    mise run dagger-bench

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

# Generate outside-in Synthetic Open Schema YAML from the exposure catalog.
sos-generate:
    python scripts/generate-synthetic-open-schema.py

# Validate the deterministic SOS generator contract without network probes.
sos-test:
    python -m pytest -q tests/test_synthetic_open_schema_generation.py

# Read-only public/private DNS check on any host (no local Docker inspection).
sample-dns:
    bash scripts/ingress/diagnose-sample-dns.sh --check

# TrueNAS variant: inspect local Pi-hole container configuration, read-only.
sample-dns-truenas:
    bash scripts/ingress/diagnose-sample-dns.sh --truenas

# Run from the workstation (NetworkManager + active DNS/DHCP evidence).
sample-dns-workstation:
    bash scripts/ingress/diagnose-sample-dns.sh --workstation

# Offline mock-contracts, no real DNS or Docker requests.
sample-dns-test:
    python3 -m unittest discover -s tests -p test_sample_dns_diagnostic.py -v

# Read-only service diagnostics; NO quality gate, CI, restart or deployment.
homelab-diagnostics-plan:
    python3 scripts/truenas/diagnose-service-bundle.py --plan --section all

homelab-diagnostics-observability:
    sudo -n python3 scripts/truenas/diagnose-service-bundle.py --check --section observability

homelab-diagnostics-applications:
    sudo -n python3 scripts/truenas/diagnose-service-bundle.py --check --section applications

homelab-diagnostics-contracts:
    python3 -m pytest -q tests/test_service_diagnostic_bundle.py

# Gatus latest probe results (read-only): statuses, staleness, catalogue parity.
gatus-monitor-failures:
    python3 scripts/truenas/diagnose-gatus-monitors.py --check

gatus-monitor-contracts:
    python3 -m pytest -q tests/test_gatus_monitor_failures.py tests/test_service_diagnostic_bundle.py

# Offline compatibility: always use Node 22 AND bundled npm 10 from one install.
# The npm shim on PATH can be npm 12 even when mise exec selects Node 22.
node22-fast:
    @node_root="$(mise where node@22 2>/dev/null)" || { echo 'Node 22 missing; install separately with mise install node@22' >&2; exit 2; }; \
      node_bin="$node_root/bin/node"; npm_cli="$node_root/lib/node_modules/npm/bin/npm-cli.js"; \
      test -x "$node_bin" && test -f "$npm_cli" || { echo 'Node22 bundled npm missing; no download attempted' >&2; exit 2; }; \
      node_major="$("$node_bin" -p 'process.versions.node.split(".")[0]')"; \
      npm_major="$("$node_bin" "$npm_cli" --version | cut -d. -f1)"; \
      test "$node_major" = 22 && test "$npm_major" = 10 || { echo "Expected Node22/npm10, found $node_major/$npm_major" >&2; exit 2; }; \
      PATH="$node_root/bin:$PATH" "$node_bin" "$npm_cli" --offline run test:fast:node22

# On-demand standalone APISIX service; isolated from default deployment.
apisix-contract:
    python3 -m unittest discover -s tests -p 'test_apisix_contract.py' -v

apisix-up:
    bash scripts/truenas/apisix.sh up

apisix-smoke:
    bash scripts/truenas/apisix.sh smoke

# Safe process metadata, never logs, credentials or HTTP data.
apisix-check:
    bash scripts/truenas/apisix.sh check

apisix-down:
    bash scripts/truenas/apisix.sh down

# TrueNAS only: replay the seven known failed gates; read-only/private.
critical-failures-triage:
    sudo -n bash scripts/truenas/triage-critical-failures.sh --check

# TrueNAS: focused Prometheus/Akvorado acceptance, no unnecessary OpenRAG probes.
# Read-only stopped Talos VM inventory on TrueNAS; not a Kubernetes upgrade.
talos-stopped-vms-check:
    sudo -n python3 scripts/truenas/resume-stopped-talos-vms.py --check

# Intentional Talos VM start; never upgrade Talos while VMs are stopped.
talos-stopped-vms-start:
    sudo -n python3 scripts/truenas/resume-stopped-talos-vms.py --start --acknowledge I_ACCEPT_STARTING_EXISTING_TALOS_VMS

# Read-only audit of ALL canonical runtime secrets and directory modes.
runtime-secret-modes-check:
    sudo -n python3 scripts/truenas/audit-runtime-secret-permissions.py --check

# Scoped, deliberate mode-only fix; preserves owner, group, group read.
runtime-secret-modes-apply:
    sudo -n python3 scripts/truenas/audit-runtime-secret-permissions.py --apply --acknowledge I_ACCEPT_SCOPED_SECRET_MODE_REPAIR

# Read-only test of an already-approved private PDF, no indexing or upload.
openrag-private-pdf-check file:
    sudo -n bash scripts/truenas/check-openrag-private-pdf.sh --check --file "{{file}}"

# Kubernetes-only, read-only controller ReplicaSet and terminated Pod correlation.
talos-csi-controller-pods-check:
    python3 scripts/talos/diagnose-truenas-csi-controller-pods.py --check

# Read-only Docling App/container/host/Docker-network readiness; no PDF bytes.
docling-readiness-check:
    sudo -n python3 scripts/truenas/diagnose-docling-readiness.py --check

# Offline fixture and response-contract tests. No network or corpus reads.
docling-synthetic-test:
    python3 -m py_compile scripts/truenas/smoke-docling-synthetic-pdf.py tests/test_docling_synthetic_pdf.py
    python3 -m unittest discover -s tests -p 'test_docling_synthetic_pdf.py' -v
    python3 scripts/truenas/smoke-docling-synthetic-pdf.py --check

# Explicit conversion on private LAN only. Does not index an OpenRAG corpus.
docling-synthetic-apply:
    python3 scripts/truenas/smoke-docling-synthetic-pdf.py --apply

# Check the TrueNAS Docling Custom App include, cached image and networks.
docling-deploy-check:
    sudo -n bash scripts/truenas/deploy-docling.sh --check

# Deliberate single-App creation/update; no bulk restore or implicit image pull.
docling-deploy-apply:
    sudo -n bash scripts/truenas/deploy-docling.sh --apply

# Offline acceptance contracts for staged infrastructure and private-document probes.
migration-recovery-contracts:
    python3 -m unittest discover -s tests -p 'test_talos_stopped_vm_resume.py' -v
    python3 -m unittest discover -s tests -p 'test_runtime_secret_permission_audit.py' -v
    python3 -m unittest discover -s tests -p 'test_openrag_private_pdf_readiness.py' -v
    python3 -m unittest discover -s tests -p 'test_docling_readiness_diagnostic.py' -v
    python3 -m unittest discover -s tests -p 'test_docling_synthetic_pdf.py' -v
    python3 -m unittest discover -s tests -p 'test_docling_deploy_preflight.py' -v
    python3 -m unittest discover -s tests -p 'test_truenas_csi_controller_pods.py' -v
    bash -n scripts/truenas/check-openrag-private-pdf.sh

critical-remaining-triage:
    sudo -n bash scripts/truenas/triage-critical-failures.sh --check --remaining

# Offline private-migration report triage; prints only bounded categories/counts.
migration-session-triage-test:
    python3 -m py_compile scripts/truenas/triage-migration-session.py tests/test_migration_session_triage.py
    python3 -m unittest discover -s tests -p 'test_migration_session_triage.py' -v

# Unified, redacted H-05/H-06 report: LAN-only; never restarts services.
# Exit 0 = PASS, 1 = confirmed scrape/metadata fault, 2 = UNVERIFIED.
observability-evidence-lan:
    sudo python3 scripts/truenas/collect-observability-evidence.py --check --scope remaining --observe-seconds 20 --report-dir /mnt/cpool/var/nabla/observability

# No LAN or Docker required: synthetic Prometheus/Akvorado contract checks.
observability-evidence-test:
    python3 -m unittest discover -s tests -p 'test_collect_observability_evidence.py' -v
    python3 -m pytest -q tests/test_prometheus_failed_scrapes_diagnostic.py tests/test_akvorado_flow_deltas.py

# Classify the latest TrueNAS lifecycle failures; log text is never printed.
truenas-lifecycle-recent:
    sudo python3 scripts/truenas/triage-app-lifecycle-log.py --check --since 2026-10-20

# Repair stored Scrutiny app definition, preserving its existing InfluxDB token.
truenas-scrutiny-reconcile:
    sudo env SCRUTINY_CUTOVER_APPROVED=1 bash scripts/truenas/deploy-scrutiny.sh --apply

# Install existing FastAPI metrics token into the Prometheus bind source.
truenas-prometheus-metrics-credential-install:
    sudo python3 scripts/truenas/reconcile-fastapi-metrics-credential.py --apply --acknowledge I_APPROVE_FASTAPI_SCRAPE_CREDENTIAL_INSTALL

# Offline scripts and fixtures: no TrueNAS API or secrets.
truenas-lifecycle-recovery-test:
    bash -n scripts/truenas/deploy-scrutiny.sh
    python3 -m pytest -q tests/test_truenas_lifecycle_recovery.py tests/test_fastapi_prometheus_credential_contract.py tests/test_fastapi_metrics_source_triage.py

# Classify one LiteLLM auth failure JSON without printing key hashes or IPs.
litellm-dashboard-auth-test:
    python3 -m pytest -q tests/test_litellm_dashboard_auth_failure.py

# Validate DefectDojo private login HTML with TLS verification and pinned LAN SNI.
defectdojo-login-lan:
    bash scripts/workstation/check-defectdojo-login-lan.sh --check

# Offline DefectDojo login and LiteLLM dashboard regression tests.
private-login-contracts:
    bash -n scripts/workstation/check-defectdojo-login-lan.sh
    python3 -m pytest -q tests/test_defectdojo_login_lan_probe.py tests/test_litellm_dashboard_auth_failure.py

# Canonical DefectDojo non-secret metadata: check without mutation.
defectdojo-runtime-env-inspect:
    sudo python3 scripts/truenas/prepare-defectdojo-runtime-env.py --inspect

# Compare existing Django admin password hash with canonical runtime secret.
defectdojo-admin-password-check:
    sudo python3 scripts/truenas/reconcile-defectdojo-admin-password.py --check

# Explicitly update the EXISTING admin hash from canonical secrets, not Vaultwarden.
defectdojo-admin-password-apply:
    sudo python3 scripts/truenas/reconcile-defectdojo-admin-password.py --apply --acknowledge I_APPROVE_EXISTING_DEFECTDOJO_ADMIN_PASSWORD_SYNC

# Read-only HTTP origin vs HTTPS SNI, Traefik labels and Docker network.
defectdojo-private-route-check:
    sudo python3 scripts/truenas/diagnose-defectdojo-https-route.py --check

# No pytest dependency: portable workstation split-DNS regression contracts.
defectdojo-workstation-dns-test:
    bash -n scripts/workstation/diagnose-defectdojo-lan.sh
    python3 -m py_compile tests/test_defectdojo_workstation_lan_dns.py
    python3 -m unittest discover -s tests -p 'test_defectdojo_workstation_lan_dns.py' -v

# Verify both pfSense DNS and the actual workstation system resolver.
defectdojo-workstation-dns-check:
    bash scripts/workstation/diagnose-defectdojo-lan.sh --check

# Read-only pfSense DNS UDP/TCP, NetworkManager, resolved and NSS evidence.
workstation-split-dns-check:
    python3 scripts/workstation/homelab-split-dns.py --check

# Explicit workstation-only recovery; fails closed if pfSense UDP DNS is unverified.
workstation-split-dns-repair:
    python3 scripts/workstation/homelab-split-dns.py --apply --acknowledge I_APPROVE_WORKSTATION_SPLIT_DNS_REPAIR

# Offline standard-library tests. Does not need pytest, LAN or root.
workstation-split-dns-test:
    python3 -m py_compile scripts/workstation/homelab-split-dns.py tests/test_homelab_split_dns_recovery.py
    python3 -m unittest discover -s tests -p 'test_homelab_split_dns_recovery.py' -v

# Hermetic suite: no LAN, root, database or secret access required.
defectdojo-recovery-test:
    python3 -m pytest -q tests/test_defectdojo_existing_admin_reconcile.py tests/test_defectdojo_https_route_triage.py tests/test_defectdojo_runtime_credential_contract.py

# Investigate TrueNAS memory pressure, ZFS ARC and DefectDojo container working sets.
truenas-defectdojo-memory-check:
    sudo python3 scripts/truenas/diagnose-defectdojo-memory-pressure.py --check --observe-seconds 20

# Inspect only the DefectDojo database in shared PostgreSQL (no DROP/CREATE).
truenas-defectdojo-db-reset-plan:
    sudo python3 scripts/truenas/inspect-defectdojo-db-reset.py --check

# Fixture-only tests: no Docker, SQL, LAN or TrueNAS API calls.
truenas-defectdojo-memory-test:
    python3 -m pytest -q tests/test_defectdojo_memory_pressure.py tests/test_defectdojo_db_reset_inventory.py

# One-shot private Backstage-aligned RAM/GPU/ZFS resource inventory (never runs in CI).
truenas-service-resources:
    sudo install -d -o root -g root -m 0700 /mnt/cpool/var/nabla/service-resources
    sudo python3 scripts/truenas/collect-service-resource-evidence.py --check --host truenas --output "/mnt/cpool/var/nabla/service-resources/resources-$(date -u +%Y%m%dT%H%M%SZ).json"

# Hermetic resource identity/memory/storage/GPU contracts; no LAN or Docker.
truenas-service-resources-test:
    python3 -m pytest -q tests/test_service_resource_evidence.py

# Read-only: classify a DefectDojo app stuck in DEPLOYING without printing logs.
defectdojo-deploying-check:
    sudo python3 scripts/truenas/diagnose-defectdojo-deploying.py --check

# Read-only: classify bounded recent initializer/backend logs, no raw lines.
defectdojo-deploying-log-classes:
    sudo python3 scripts/truenas/diagnose-defectdojo-deploying.py --check --include-log-classes

# Read-only Vaultwarden cache vs root runtime equality as the unlocked operator.
vaultwarden-runtime-parity:
    python3 scripts/secrets/compare_vaultwarden_runtime_readonly.py --check --app defectdojo

# Read-only seven-job Prometheus scrubber (no scrape URI, body or token).
prometheus-remaining-scrapes:
    python3 scripts/prometheus/diagnose-failed-scrapes.py --check --scope remaining

# Offline regression checks for bounded seven-gate recovery diagnostics.
critical-failures-contracts:
    python3 -m unittest discover -s tests -p 'test_critical_triage_contract.py' -v
    python3 -m unittest discover -s tests -p 'test_ai_secret_recovery_scope.py' -v

# Stable migration operator: no runtime probes on --help.
postmigration-check:
    sudo -n bash scripts/truenas/migration-operator.sh --check --section postmigration

migration-operator-help:
    bash scripts/truenas/migration-operator.sh --help

# Offline migration and APISIX rollback contracts. No Docker/TrueNAS required.
migration-operator-contracts:
    python3 -m pytest -q tests/test_finish_migrations_20261024.py
    python3 -m unittest discover -s tests -p 'test_apisix_contract.py' -v

# Parallel read-only TrueNAS evidence: secret syntax, container provenance and DB flag.
# Requires passwordless sudo for python3 on TrueNAS; never prints secret material.
openclaw-truenas-secret-provenance:
    python3 scripts/workstation/check-truenas-litellm-secret-provenance.py


# Discover the existing TrueNAS Compose deployment without changing it.
openclaw-truenas-litellm-recreate-plan:
    ssh -o BatchMode=yes truenas 'sudo -n python3 -' < scripts/truenas/recreate-litellm-env.py

# Explicit one-service recreation; no change to unrelated containers.
openclaw-truenas-litellm-recreate-apply:
    ssh -o BatchMode=yes truenas 'sudo -n python3 - --apply' < scripts/truenas/recreate-litellm-env.py

# TrueNAS provisioning with existing runtime key values; no secret output.
# Plan is read-only and uses the local TrueNAS LiteLLM API.
openclaw-truenas-virtual-keys-plan:
    python3 scripts/truenas/dispatch-openclaw-litellm-keys.py --mode plan

# Explicitly create the two OpenClaw virtual keys (budget 2 each).
openclaw-truenas-virtual-keys-apply:
    python3 scripts/truenas/dispatch-openclaw-litellm-keys.py --mode apply

# Works from either canonical TrueNAS checkout or Workstation; no tunnel required.
openclaw-truenas-virtual-keys-status:
    python3 scripts/truenas/dispatch-openclaw-litellm-keys.py --mode status

# Offline stdlib contracts; require no Docker, SSH, API key, or CI.
openclaw-truenas-virtual-keys-test:
    python3 -m py_compile scripts/truenas/dispatch-openclaw-litellm-keys.py scripts/truenas/provision-openclaw-litellm-keys.py tests/test_openclaw_litellm_execution_dispatch.py
    python3 -m unittest discover -s tests -p 'test_openclaw_litellm_execution_dispatch.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_litellm_429_diagnostic.py' -v

# These commands never change TrueNAS services or send credentials.
protected-http-diagnostics:
    sudo -n python3 scripts/truenas/diagnose-protected-service-http.py --check

protected-http-contracts:
    python3 -m pytest -q tests/test_protected_service_http.py

# Read-only LiteLLM per-key quota, scope and spend inspection; works on both hosts.
openclaw-truenas-virtual-keys-quota:
    python3 scripts/truenas/dispatch-openclaw-litellm-keys.py --mode quota-audit

# Run only on Workstation: sanitized config/model routes + TrueNAS budget evidence.
# No LLM completion or Gateway restart. Return 1/2 if the quota audit detects an issue.
openclaw-429-attribution:
    python3 scripts/workstation/openclaw-route-metadata.py
    python3 scripts/workstation/diagnose-openclaw-litellm-429.py --admin
    python3 scripts/truenas/dispatch-openclaw-litellm-keys.py --mode quota-audit
    python3 scripts/workstation/diagnose-openclaw-auth-cooldowns.py

# Targeted local-only contracts for 429 attribution; no real model or SSH calls.
openclaw-429-attribution-test:
    python3 -m py_compile scripts/workstation/openclaw-route-metadata.py scripts/workstation/diagnose-openclaw-auth-cooldowns.py scripts/truenas/provision-openclaw-litellm-keys.py scripts/truenas/dispatch-openclaw-litellm-keys.py tests/test_openclaw_auth_cooldowns.py tests/test_openclaw_route_metadata.py tests/test_openclaw_litellm_execution_dispatch.py tests/test_openclaw_litellm_429_diagnostic.py
    python3 -m unittest discover -s tests -p 'test_openclaw_auth_cooldowns.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_route_metadata.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_litellm_execution_dispatch.py' -v


# Offline generic LiteLLM catalogue parity without professional upstream routes.
# Run on Workstation. No TrueNAS restart, API call, or hosted CI.
litellm-truenas-generic-alignment-test:
    python3 -m py_compile tests/test_litellm_truenas_generic_alignment.py
    python3 -m unittest discover -s tests -p 'test_litellm_truenas_generic_alignment.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_litellm_execution_dispatch.py' -v


# Workstation-only. Validate both policies and safe backup/install semantics offline.
openclaw-morning-briefing-test:
    python3 -m py_compile scripts/workstation/openclaw-heartbeat-gitops.py tests/test_openclaw_briefing_gitops.py
    python3 -m unittest discover -s tests -p 'test_openclaw_briefing_gitops.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_litellm_execution_dispatch.py' -v

# Compare source policy and briefing to the live OpenClaw workspace.
openclaw-morning-briefing-check:
    python3 scripts/workstation/openclaw-heartbeat-gitops.py --check
    python3 scripts/workstation/openclaw-heartbeat-gitops.py --briefing-check

# Deploy the reviewed heartbeat policy and daily briefing with local private backups.
# No cron/automation created; no gateway restart or embedding rebuild.
openclaw-morning-briefing-apply:
    python3 scripts/workstation/openclaw-heartbeat-gitops.py --apply
    python3 scripts/workstation/openclaw-heartbeat-gitops.py --briefing-apply


# Local-only, read-only 429 collection: workstation LiteLLM spend API and
# redacted OpenClaw/systemd/Docker counters. No user exports or model calls.
openclaw-429-auto:
    python3 scripts/workstation/diagnose-openclaw-429-auto.py --hours 2

# Hermetic contracts; no CI credits, model calls, or service restart.
openclaw-429-fix-test:
    python3 -m py_compile scripts/workstation/diagnose-openclaw-429-auto.py scripts/workstation/repair-openclaw-429.py tests/test_openclaw_429_auto.py tests/test_openclaw_429_repair.py
    python3 -m unittest discover -s tests -p 'test_openclaw_429_auto.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_429_repair.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_route_metadata.py' -v

# Preflight only: validate that cron's existing scoped key permits GPT-4.1.
openclaw-429-fix-plan:
    python3 scripts/workstation/repair-openclaw-429.py

# Explicit one-shot fix on the Workstation. Back up, isolate cron key, cap
# global concurrency, then restart/recheck Gateway or roll back.
# Never touches memory.search, virtual-key budgets, or TrueNAS LiteLLM.
openclaw-429-fix-apply:
    python3 scripts/workstation/repair-openclaw-429.py --apply --restart-gateway


# Single Workstation entrypoint. Tests + preflight gate the one-shot
# mutation. Diagnostic is optional evidence, not a reason to block local fix.
# No remote CI, no budget changes, no embedding reindex.
openclaw-429-fix-all:
    just openclaw-429-fix-test
    just openclaw-429-fix-plan
    just openclaw-429-fix-apply
    python3 scripts/workstation/openclaw-route-metadata.py
    python3 scripts/workstation/diagnose-openclaw-429-auto.py --hours 2 || echo 'WARN: 429 evidence unavailable; runtime fix already processed'


# Inspect the exact npm debug log from the failed 2026-10-25 OpenClaw update.
# Read-only; output is limited to known error categories and version metadata.
openclaw-update-npm-triage:
    python3 scripts/workstation/diagnose-openclaw-update-npm.py --log-name 2026-10-25T19_43_24_104Z-debug-0.log

openclaw-update-npm-test:
    python3 -m py_compile scripts/workstation/diagnose-openclaw-update-npm.py tests/test_openclaw_update_npm_diagnostic.py
    python3 -m unittest discover -s tests -p 'test_openclaw_update_npm_diagnostic.py' -v

# Workstation-only recovery gate. No npm install, no GitHub CI, no LLM request.
openclaw-update-recovery-local:
    just openclaw-update-npm-test
    just openclaw-429-fix-test
    python3 scripts/workstation/diagnose-openclaw-update-npm.py --log-name 2026-10-25T19_43_24_104Z-debug-0.log || echo 'WARN: npm update root cause not verified; do not rerun update blindly'


# Install the patched Node runtime into the existing user-owned mise store.
# Explicit mutation: downloads only Node, not OpenClaw; does not change
# system Node, npm prefix, Gateway unit, config, or any embeddings.
openclaw-node24-runtime-install:
    MISE_SAFE=1 mise lock node@24.22.1
    mise install --locked node@24.22.1
    mise exec node@24.22.1 -- node --version


# Rootless OpenClaw 2026.10.7 recovery on the existing Ubuntu Workstation.
# No CI, no model calls, and no edits to TrueNAS LiteLLM or memory embeddings.
openclaw-upgrade-local-test:
    python3 -m py_compile scripts/workstation/upgrade-openclaw-mise.py tests/test_upgrade_openclaw_mise.py
    python3 -m unittest discover -s tests -p 'test_upgrade_openclaw_mise.py' -v
    bash -c "umask 0002; python3 -m unittest discover -s tests -p 'test_upgrade_openclaw_mise.py' -v"

# Read-only service and package owner inspection.
openclaw-upgrade-local-plan:
    python3 scripts/workstation/upgrade-openclaw-mise.py --plan

# Side-by-side npm install under the NEW mise Node prefix; old Gateway stays up.
openclaw-upgrade-local-stage:
    python3 scripts/workstation/upgrade-openclaw-mise.py --stage

# Explicit maintenance action: stop Gateway, create consistent state backup,
# install dedicated systemd override and start new OpenClaw version.
# On migration failure, retain backup for manual recovery.
openclaw-upgrade-local-activate:
    python3 scripts/workstation/upgrade-openclaw-mise.py --activate

# No billable request; check installed package, systemd owner, /readyz,
# Doctor lint and main/cron memory statuses.
openclaw-upgrade-local-verify:
    python3 scripts/workstation/upgrade-openclaw-mise.py --verify


# One explicit operator workflow: offline contracts, inspect, isolated npm
# staging, backed-up maintenance cutover, then redacted functional checks.
# May stop/restart the user Gateway; does NOT run model inference.
openclaw-upgrade-local-all:
    just openclaw-upgrade-local-test
    just openclaw-upgrade-local-plan
    just openclaw-upgrade-local-stage
    just openclaw-upgrade-local-activate
    just openclaw-upgrade-local-verify


# OpenClaw 2026.10.7: repair managed service Node only, not the npm stage.
# No project backup, no CI runner, no LiteLLM model requests.
openclaw-gateway-node-test:
    python3 -m py_compile scripts/workstation/repair-openclaw-gateway-node.py tests/test_repair_openclaw_gateway_node.py scripts/workstation/diagnose-openclaw-gateway-readiness.py tests/test_openclaw_gateway_readiness.py scripts/workstation/diagnose-openclaw-gateway-service-failure.py tests/test_openclaw_gateway_service_failure.py scripts/workstation/diagnose-openclaw-gateway-doctor-lint.py tests/test_openclaw_gateway_doctor_lint.py scripts/workstation/diagnose-openclaw-gateway-listener.py tests/test_openclaw_gateway_listener.py scripts/workstation/diagnose-openclaw-state-owner.py tests/test_openclaw_state_owner.py
    bash -n scripts/workstation/recover-openclaw-managed-gateway.sh
    python3 -m unittest discover -s tests -p 'test_repair_openclaw_gateway_node.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_gateway_readiness.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_gateway_service_failure.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_state_owner.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_gateway_doctor_lint.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_gateway_start_once.py' -v
    python3 -m unittest discover -s tests -p 'test_openclaw_gateway_listener.py' -v
    bash -n scripts/workstation/start-openclaw-gateway-once.sh
    bash -c "umask 0002; python3 -m unittest discover -s tests -p 'test_repair_openclaw_gateway_node.py' -v"

# Read-only. Distinguish HTTP liveness, startup and admission readiness
# without exposing channel identities, database contents or secrets.
openclaw-gateway-readiness:
    python3 scripts/workstation/diagnose-openclaw-gateway-readiness.py

# Read-only TCP listener, IPv4/IPv6 loopback and UI root diagnosis.
# Does not restart the Gateway, probe models or expose raw responses.
openclaw-gateway-listener:
    python3 scripts/workstation/diagnose-openclaw-gateway-listener.py

# Read-only classification of failed systemd process and recent journal.
# Exposes only fixed codes; never prints actual log lines or credentials.
openclaw-gateway-service-failure:
    python3 scripts/workstation/diagnose-openclaw-gateway-service-failure.py

# Read-only: correlate last logged state owner with live /proc PID and
# fuser owners of SQLite, WAL and SHM. Historical logs alone are not proof.
openclaw-state-owner:
    python3 scripts/workstation/diagnose-openclaw-state-owner.py

# Read-only, no repairs or model requests: parse pinned OpenClaw Doctor
# structured lint as sanitized categories for EX_CONFIG 78.
openclaw-gateway-doctor-lint:
    python3 scripts/workstation/diagnose-openclaw-gateway-doctor-lint.py

# Explicit one-time operator recovery after exit 78. No retry or npm.
# Run only after checking Doctor's structured findings; active units
# are diagnosed, not stopped or restarted.
openclaw-gateway-start-once:
    bash scripts/workstation/start-openclaw-gateway-once.sh --once

# Explicit scoped hardening when the Node 24.22.1 npm package is
# group-writable because of workstation umask 0002. Never chmod shared
# paths or reinstall packages. Requires an owned user systemd drop-in.
openclaw-gateway-package-permissions:
    python3 scripts/workstation/repair-openclaw-gateway-node.py --harden-installed-permissions

# Read-only: print a fixed error category if package verification fails.
openclaw-gateway-node-plan:
    python3 scripts/workstation/repair-openclaw-gateway-node.py --select-installed-plan

# The next step does NOT invoke npm or openclaw update. It selects the
# existing, independently validated OpenClaw 2026.10.7 installation
# under mise Node 24.22.1 for the managed systemd Gateway.
# No project backup, model request, new staged installation or CI.
openclaw-gateway-select-installed:
    bash scripts/workstation/recover-openclaw-managed-gateway.sh --apply

# Backwards-compatible recipe name; the operation is package selection,
# not a package-manager update. Retained for existing workstation commands.
openclaw-gateway-node-update:
    just openclaw-gateway-select-installed
