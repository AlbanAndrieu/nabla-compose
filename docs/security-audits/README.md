# Security audits

Rapports de sécurité source-first conservés pour comparaison et revalidation.

- [2026-10-01 — Cloudflare security-audit-skill one-shot](./2026-10-01-cloudflare-security-audit/REPORT.md)
  — profil quick, couverture partielle, aucun finding confirmé, un lead Scanopy
  à valider.

Un rapport `incomplete` ne doit jamais être interprété comme une attestation
d'absence de vulnérabilités. Les runs suivants doivent réutiliser le ledger et les
fingerprints lorsque la source est comparable.


## Validation locale

Every committed audit directory containing `findings.json` and
`coverage-ledger.json` is validated by the vendored Cloudflare validators via
`tests/test_security_audit_skill_contract.py` and the
`security-audit-skill-contract` Pre-commit hook.

For a focused check:

```bash
node .agents/skills/security-audit/validate-findings.cjs \
  docs/security-audits/2026-10-01-cloudflare-security-audit/findings.json

node .agents/skills/security-audit/validate-coverage-ledger.cjs \
  docs/security-audits/2026-10-01-cloudflare-security-audit/coverage-ledger.json

python -m pytest -q tests/test_security_audit_skill_contract.py
```

This validates artifact structure and semantics only. It does not upgrade an
`incomplete` audit into complete coverage and does not replace independent
verification or sandboxed reproduction.
