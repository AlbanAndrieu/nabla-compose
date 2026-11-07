# Runbooks — index opérationnel

> Mise à jour le 6 novembre 2026. Ce répertoire conserve les **procédures courantes** et les **cas d'échec mémorisables**. Les commandes d'un ancien incident ne sont pas un ordre de redéploiement. Source d'autorité des tâches : [roadmap active](../roadmap.md).

## Opérations actives

| Opération | Document de référence | Gate |
| --- | --- | --- |
| Remédiations des sondes et Apps TrueNAS après PR #326 | [Sondes — tâches restantes](2026-11-04-probe-remediation.md) | Parité `x-nabla` et santé runtime réelle |
| Opérateur de migration TrueNAS | [Migration contrôlée](truenas-migration-operator.md) | `--check` / plan / rollback, accord explicite |
| Migration des Apps du catalogue TrueNAS vers Compose | [Plan de migration](2026-11-06-catalog-apps-to-compose.md) | Plan/read-only, sauvegarde, décision opérateur et rollback |
| Diagnostic runtime Gatus / Prometheus / OpenRAG | [Acceptation Homelab](homelab-runtime-acceptance.md) | Preuves read-only, sans fusionner `DENIED` et `DOWN` |
| FastAPI Sample et LiteLLM | [Diagnostic consolidé](fastapi-consolidated-diagnostics-20261030.md) | Identité, routes, métriques, secrets 0600 |
| OpenClaw et heartbeat | [Migration end-to-end](openclaw-end-to-end-migration-20261030.md) | Gateway cible, budget, logs et aucun double heartbeat |
| Home Assistant / Open WebUI | [Identité canonique](openwebui-homeassistant-canonical-rename.md) | Sauvegarde, middleware, Access et rollback |
| Secrets TrueNAS | [Clôture](truenas-secret-migration-closure.md) | Provenance et alignement runtime |
| Talos Kubernetes | [Préflight CSI](../kubernetes-csi-preflight.md) | `democratic-csi` et multi-nœuds |
| Sécurité et test de non-régression | [Registre des refactorings](homelab-refactoring-risk-register.md) | Tests négatifs et qualité L3 |
| Scripts de l'agent | [Skill local-first](../../.agents/skills/local-first-quality/SKILL.md) | Travail sur branche dédiée, pas de CI payante implicite |

Les services qui requièrent une licence, des droits spéciaux ou des données réelles (ntopng, Scanopy, Home Assistant, Vaultwarden) ne sont jamais déployés par le simple chargement du catalogue.

## Problèmes passés utiles à conserver

- [Retour d'expérience des migrations du 6 novembre](../incidents/2026-11-06-migrations-retour-experience.md) : App `STOPPED` mal appariée, WAF, OOM, OpenClaw, secrets et Pre-commit.
- [Archive approuvée au 24 octobre](../archive/roadmap-through-2026-10-24.md) : preuves historiques non applicables sans nouveau préflight.
- [Incident pfSense / Unbound](2026-10-24-pfsense-unbound-pfblocker-whatsapp.md) : distinguer OOM, réseau et cause effective.
- [DefectDojo — accès privé](defectdojo-private-ingress-acceptance.md) : résolution DNS, TLS/SNI et accès auth.
- [OpenClaw — attribution 429](openclaw-litellm-429-attribution.md) : séparer quota, identité effective et métadonnées réelles.

Les autres runbooks datés du répertoire restent consultables comme **matériau d'incident**, pas comme travaux à effectuer. Ils ne doivent pas être copiés dans la roadmap active.

## Maintenance documentaire

Une action non terminée apparaît **une seule fois** dans `docs/roadmap.md` et renvoie à son contrat d'exploitation. Un incident résolu ne conserve que *symptôme, cause, prévention, test de non-régression* ; les logs complets et secrets ne sont pas recopiés. `CODED` ne veut pas dire `ACCEPTED (runtime)`.
