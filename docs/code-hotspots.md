# Inventaire des hotspots de code — Homelab

> **Instantané GitHub du 14 novembre 2026**, sans accès runtime ni secrets.
> Sources: `nabla-compose` `c8d77abe3c7d2e98a6b7b3f04e2c1551f9d7075f` et
> `fastapi-sample` `34a97b923d33ef0c4871c1800b221b58a216d700`.
> **Volume = taille des blobs Git des fichiers de programmation** (`.py`, `.sh`, `.js`,
> `.ts`, `.mjs`, `.cjs` et apparentés), tests compris. Ce n'est **ni une
> mesure de LOC globales ni de complexité cyclomatique**. Les lignes indiquées
> ci-dessous ont, elles, été comptées directement sur le contenu des fichiers.

## Répartition mesurée

| Dépôt / zone | Fichiers source | Octets | Observation |
| --- | ---: | ---: | --- |
| Compose, ensemble des fichiers de programmation | 808 | 5 637 203 | 1 848 blobs suivis, formats de configuration et docs exclus |
| Compose, `tests/` | 369 | 2 330 053 | 41,3 % du volume de programmation : **ne pas supprimer en bloc** |
| Compose, `scripts/` | 418 | 3 118 773 | 55,3 %, en majorité orchestration/opérations |
| Compose, `scripts/truenas/` | 199 | 1 485 737 | 26,4 % : cycle de vie, déploiement, diagnostics, reboot |
| Compose, `scripts/workstation/` | 55 | 389 056 | 6,9 % : client local, OpenClaw, modèles |
| Compose, `scripts/pfsense/` | 17 | 209 391 | 3,7 % : audit et récupération |
| Compose, `scripts/talos/` | 20 | 153 497 | 2,7 % : Kubernetes/CSI |
| FastAPI, ensemble des fichiers de programmation | 703 | 3 938 960 | 1 188 blobs suivis, artefacts JSON/lock exclus |
| FastAPI, `nabla/` | 295 | 1 975 076 | 50,1 %, API et observabilité |
| FastAPI, `nabla/api/` | 206 | 1 634 227 | 41,5 % |
| FastAPI, `nabla/api/assets/` | 67 | 635 801 | 16,1 %, interfaces et projections |
| FastAPI, `tests/` | 303 | 1 563 269 | 39,7 %, contrats de sécurité et sondes |

Les manifestes Compose, `catalog/`, OpenTofu et les fichiers générés
ne sont pas inclus dans cette notion de *code source*. Ils constituent
un volume déclaratif distinct : `apps/` ≈ 1,34 Mo tous types confondus,
`catalog/` ≈ 1,02 Mo, `config/` ≈ 0,52 Mo dans Compose. Ne pas
refactorer le catalogue généré ou les lockfiles en fonction de leur taille.

## Plus gros fichiers — lignes physiques exactes

| Domaine | Chemin | Lignes | Cible de revue |
| --- | --- | ---: | --- |
| TrueNAS | `scripts/truenas/audit-app-lifecycle.sh` | 1 673 | Séparer collecte, invariants, rendu et conditions d'arrêt |
| Tests TrueNAS | `tests/test_truenas_app_lifecycle_contract.py` | 1 363 | Extraire fixtures communes sans réduire la couverture négative |
| pfSense | `scripts/pfsense/diagnose-recover.sh` | 1 258 | Séparer diagnostic **read-only** et restauration/mutation |
| Backstage V2 | `scripts/nabla_ops/catalog_v2.py` | 1 073 | Schémas, validation de références, projection et migration legacy |
| pfSense | `scripts/pfsense/audit-posture.sh` | 800 | Partager uniquement les primitives justifiées par contrats |
| TrueNAS | `scripts/truenas/reboot-homelab.sh` | 849 | Orchestration vs preuves/rollback, conserver l'idempotence |
| Catalogue | `scripts/generate-service-topology.py` | 854 | Parcours du graphe, sérialisation, déterminisme |
| FastAPI UI | `nabla/api/assets/home-operations.js` | 1 275 | Transport/cadence distincts des projections et du rendu |
| FastAPI UI | `nabla/api/assets/api-service-detail-drawer.js` | 1 088 | Contrôleur d'état et accessibilité distincts des panneaux |
| FastAPI UI | `nabla/api/assets/api-service-operator-diagnostics.js` | 942 | Niveaux de preuve, logique des onglets et gestion des erreurs |
| FastAPI UI | `nabla/api/assets/api-probe-fanout-dashboard.js` | 935 | Contrôle de cadence, affichage des délais et statut des vagues |
| FastAPI UI | `nabla/api/assets/home-operations-model.js` | 856 | Modèle pur : préserver, tester plutôt que dupliquer |
| FastAPI runtime | `nabla/api/health_board.py` | 608 | Cache single-flight/stale, échéances des providers |
| FastAPI TrueNAS | `nabla/integrations/truenas_client.py` | 576 | Transport WS, gestion d'erreurs et preuves d'identité |

Les lignes physiques incluent commentaires et blancs. Les gros fichiers
`nabla/_version.py` et les JSON générés ne sont **pas** des candidats
de refactoring manuel.

## Priorisation de la dette — sans changer l'ordre validé

**P0 opérationnel inchangé : H02/G1 → H01 → H05.** Les chantiers de
taille/découpage sont **P1 / H11**, sauf lorsqu'un défaut concret affecte
la couverture H05 ou le contrat H17.

1. **H11 · TrueNAS** : isoler l'observation sans effet de bord de
   `audit-app-lifecycle.sh` ; conserver les codes de retour, le JSON
   expurgé, les receipts et les tests existants. Résultat attendu :
   fonctions pures/partagées avec preuve d'identité et smoke ciblé.
2. **H07 + H11 · pfSense** : éviter la fusion du diagnostic et des
   chemins de récupération ; contrat fail-closed en cas de privilèges,
   DNS/SSH/API ou absence de snapshot, avec test négatif par mode.
3. **H17 · catalogue V2** : réduire la duplication entre
   `catalog_v2.py`, générateur de topologie et consommateurs ; préserver
   `entityRef`, `catalogRevision`, sorties déterministes et compatibilité
   tant que Site Alban n'est pas migré.
4. **H05 · FastAPI F03/F09** : séparer l'orchestration des preuves
   fraîches, les niveaux `DENIED`/`NO_SAMPLE`/`NOT_RUN`/`STALE`
   et le cache L1/L2. Probes internes **FastAPI TrueNAS** puis preuve
   **FastAPI Cloud outside-in** ; ne jamais inférer une panne d'un
   défaut de l'observateur.
5. **H06/H14 · interface** : fractionner les quatre gros contrôleurs
   JavaScript par responsabilité (fetch, état, DOM, accessibilité) avec
   tests navigateur FR/EN et mesure de latence ; ne pas relancer tout
   `/sickz` pour chaque rafraîchissement UI.
6. **Tests volumineux** : passer à des fixtures et validations
   paramétrées **après** mesure de couverture et vérification que les
   scénarios négatifs ne disparaissent pas. Aucun objectif de réduction
   aveugle du nombre de lignes.

## Mesure reproductible en local, sans accès aux services

Le script `scripts/quality/code-hotspots.py` utilise uniquement
`git ls-files -z` et les fichiers du checkout courant. Il ne sonde
aucun réseau/TrueNAS, n'installe rien, ne lit ni `.env` ni secrets
et ne suit pas les liens symboliques. Il compte séparément les
lignes physiques et les lignes non vides, les tests restant identifiés.

```bash
# Depuis un checkout de nabla-compose, même en mode Codex déconnecté :
python3 scripts/quality/code-hotspots.py --limit 20 --min-lines 500
python3 scripts/quality/code-hotspots.py --json --exclude-tests --limit 20

# Sur la workstation, quand le checkout frère est présent :
python3 scripts/quality/code-hotspots.py --root ../fastapi-sample --limit 20

# Vérifications hermétiques et tests sans installation :
python3 -m pytest -q tests/test_code_hotspots.py
python3 scripts/quality/check-roadmap-portfolio.py --check
```

Les sorties sont propres à la version et à l'état du checkout. Pour
comparer des PRs, noter les SHA, garder les mêmes extensions/exclusions
et distinguer la taille du code de la complexité réelle (couplage, risques,
variabilité de test et effets de bord). Aucune recette runtime n'est
acceptée sur la seule base de cette mesure.
