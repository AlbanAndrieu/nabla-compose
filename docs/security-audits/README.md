# Security audits

Rapports de sécurité source-first conservés pour comparaison et revalidation.

- [2026-10-01 — Cloudflare security-audit-skill one-shot](./2026-10-01-cloudflare-security-audit/REPORT.md)
  — profil quick, couverture partielle, aucun finding confirmé, un lead Scanopy
  à valider.

Un rapport `incomplete` ne doit jamais être interprété comme une attestation
d'absence de vulnérabilités. Les runs suivants doivent réutiliser le ledger et les
fingerprints lorsque la source est comparable.

## Validation locale

Chaque répertoire d'audit commité qui contient `findings.json` et
`coverage-ledger.json` est validé par les validateurs Cloudflare vendored via
`tests/test_security_audit_skill_contract.py` et le hook Pre-commit
`security-audit-skill-contract`.

Pour un contrôle ciblé :

```bash
node .agents/skills/security-audit/validate-findings.cjs \
  docs/security-audits/2026-10-01-cloudflare-security-audit/findings.json

node .agents/skills/security-audit/validate-coverage-ledger.cjs \
  docs/security-audits/2026-10-01-cloudflare-security-audit/coverage-ledger.json

python -m pytest -q tests/test_security_audit_skill_contract.py
```

Ce contrôle valide uniquement la structure et la sémantique des artefacts. Il
ne transforme pas un audit `incomplete` en couverture complète et ne remplace
ni la vérification indépendante ni la reproduction dans une sandbox conforme.
