# pfSense : documentation, incidents et roadmap

Tout ce qui concerne le pare-feu pfSense (Netgate 1100, bientôt Netgate 4200 MAX) est regroupé ici depuis le 17/11/2026. Objectif : pouvoir extraire pfSense vers un dépôt GitHub `nabla-pfsense` sans tout retrier. L'étude D3 de H11 est dans la [roadmap Compose](../roadmap.md#h11--scission-des-scripts-opérateur-et-diagnostics-étude-d0d4), et la règle de propriété dans l'[ADR-0003](../adr/0003-repository-ownership-and-diagnostics.md).

## Contenu

- [Roadmap pfSense](roadmap.md) : sécurité, écarts H07, stabilisation H07b et remplacement du 1100, historique P0 du 15/11.
- Documentation :
  - [Diagnostic et reprise](pfsense-diagnose-recover.md)
  - [Upgrade 26.03.1 → 26.07](pfsense-upgrade-26-07.md)
  - [Observabilité des flux et mémoire](pfsense-flow-observability-memory.md)
  - [Durcissement PHP-FPM](pfsense-php-fpm-hardening.md)
- [Runbooks](runbooks/) :
  - [environnements de boot et 26.07](runbooks/pfsense-26.07-upgrade.md)
  - [politique d'exposition](runbooks/pfsense-ingress-exposure-policy.md)
  - [provenance des décisions CrowdSec](runbooks/crowdsec-pfsense-decision-provenance.md)
  - [cibles workstation obsolètes](runbooks/2026-11-14-pfsense-stale-workstation-targets.md)
- [Incidents](incidents/), du 08/09 au 17/11/2026 (WebConfigurator 502, Unbound OOM, pont du démarrage à froid, eMMC défaillante).
- [Preuves](evidence/) : instantané HAProxy expurgé, lu par `config/ingress-access-policy.json` et les tests.

## Périmètre d'une extraction vers `nabla-pfsense`

À déplacer ensemble, dans un même lot testé :

| Chemin | Volume au 17/11 |
|---|---|
| `docs/pfsense/` | ce dossier |
| `scripts/pfsense/` | 40 fichiers |
| `tests/test_pfsense_*.py` | 32 tests |
| Recettes `pfsense-*` du `justfile` | 31 |
| `.agents/skills/pfsense-api-debugging/` | 1 skill |

À trancher avant le déplacement, car ces fichiers lisent ou appellent `scripts/pfsense/` depuis le reste du dépôt :

- **Outils workstation** : `scripts/workstation/verify-crowdsec-pfsense.sh`, `diagnose-whatsapp-web-path.sh` et `inspect-nexus-haproxy-frontend.sh`.
- **Outils qualité** : `scripts/agent-quality-gate.sh`, `scripts/quality/code-hotspots.py` et `scripts/ops/plan-repository-split.py`.
- **Tests transverses** : `test_code_hotspots.py`, `test_nexus_haproxy_frontend_readonly.py` et `test_repository_split_plan.py`.
- **CI** : `.github/workflows/observability-ci.yml`.
- **Politique d'entrée** : `config/ingress-access-policy.json`, qui lit le relevé HAProxy de `evidence/`.

Restent dans `nabla-compose`, avec des liens vers le nouveau dépôt :

- les Apps TrueNAS liées : `apps/crowdsec` et `apps/akvorado` ;
- les cibles Prometheus, Gatus et Loki ;
- Cloudflare ;
- les secrets ;
- l'incident Talos du 14/11 (`docs/incidents/2026-11-14-talos-control-plane-public-wan-lease.md`) et les incidents split-DNS partagés avec Pi-hole.

Conditions préalables (H11, D3) :

- propriété validée ;
- sauvegarde chiffrée de `config.xml` ;
- CLI `plan/check/apply/rollback` ;
- historique conservé, par exemple `git filter-repo` avec les chemins ci-dessus ;
- wrappers temporaires tant qu'un consommateur appelle encore l'ancien chemin.
