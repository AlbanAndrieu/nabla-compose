# Inventaire technique H11 — scripts opérateur et diagnostics

**Complément technique, non une nouvelle ADR.** La décision d'ownership
est unique : [ADR-0003 — limites des dépôts et diagnostics](../adr/0003-repository-ownership-and-diagnostics.md).
Cet inventaire conserve les observations et candidates du 14 novembre 2026
de la PR #386, sans transfert ou suppression effectifs.

La décision de créer `nabla-pfsense` et un éventuel submodule demeure
conditionnelle à un usage Build/Apply consommant un SHA épinglé, conformément
à l'ADR canonique. Ni le volume du code ni des noms communs ne prouvent
une duplication fonctionnelle, une économie ou la santé du runtime.

## État vérifié dans le code

| Origine | Volume Git (fichiers ; octets, sans submodules) | Observation |
| --- | --- | --- |
| `scripts/workstation/` Compose | 55 ; 389 056 | 43 scripts liés par nom à OpenClaw/LiteLLM/cron (307 054 octets). Les 12 autres concernent pfSense/CrowdSec, DefectDojo, FastAPI, Nexus et UX workstation. Le classement nominal doit être confirmé par lecture de chaque consommateur. |
| `scripts/pfsense/` Compose | 18 ; 211 799 | Diagnostic, API identities, posture, HAProxy/Unbound, PHP-FPM, upgrade et recovery ; certains chemins sont mutateurs et privilégiés. |
| `scripts/truenas/` Compose | 199 ; 1 485 737 | 99 fichiers dont le nom signale audit/check/diagnose/smoke/reconcile/probe : 773 742 octets. Ce n'est pas une mesure de duplication réelle. |
| `scripts/observability/` Compose | 6 ; 59 020 | Tests de chaîne OTLP/syslog, scrapes, dashboards et configuration dédiée. |
| `apps/openclaw` | gitlink `160000` existant | Submodule **déjà configuré** dans `.gitmodules` pour `AlbanAndrieu/nabla-openclaw`. Ne pas créer un second submodule. |

Cinq noms sont déjà présents dans les deux dépôts, avec **contenu différent** :
`check-openclaw-runtime-alignment.py`, `diagnose-openclaw-digest-top.py`,
`openclaw-heartbeat-gitops.py`, `openclaw-host-context.py`,
`reconcile-openclaw-digest-cron.py`.
Leur comparaison doit porter sur les arguments CLI, codes retour, schémas JSON,
garde-fous, effets de bord, dépendances et tests ; mêmes noms ne signifient pas
même contrat. Exemples de consommateurs Compose : `justfile`,
`tests/test_openclaw_policy_relocation.py`, `tests/test_openclaw_heartbeat_gitops.py`
et `ops/openclaw-workstation/`.

Le [plan existant dans ansible-workstation](https://github.com/AlbanAndrieu/ansible-workstation/blob/master/docs/workstation-ownership-option-a.md)
place l'OS Ubuntu dans Ansible ; le [plan OpenClaw](https://github.com/AlbanAndrieu/nabla-openclaw/blob/master/docs/migration.md)
a déjà importé une partie des scripts. Les indications historiques disant
« submodule futur » sont **obsolètes** : le gitlink existe.
Le dépôt `AlbanAndrieu/nabla-pfsense` n'existe pas à la date de cette revue.
`fastapi-sample/scripts/pfsense/diagnose-recover.sh` est déjà un wrapper de
renvoi vers Compose, **pas** un deuxième outil de restauration.

**Attention aux métriques :** les octets Git décrivent la masse maintenue dans
*un* dépôt, pas la complexité cyclomatique ni des économies totales. Déplacer
~519 ko (43 scripts OpenClaw + le répertoire pfSense) diminuerait la taille de
Compose **après** suppression des anciennes implémentations, mais ne réduirait
pas à lui seul la taille totale des dépôts ; wrappers, tests et outils encore
utilisés restent à comptabiliser. Aucune économie acquise n'est déclarée.


## Diagnostic : éviter la surveillance en double

| Couche | Propriétaire / source de vérité | Contrat ; économies et complémentarité |
| --- | --- | --- |
| Déclaré | Compose `x-nabla`, config Gatus/Prometheus | Comparaison statique, sans réseau ni secrets ; ne mesure pas la disponibilité |
| Surveillance **continue** | Gatus (HTTP/TCP/DNS), Prometheus (`up`, exporter, historiques) | **Un scheduler et un scrape par cible/vantage/cadence** ; éviter curl répétitif depuis chaque wrapper, exporteurs pfREST coûteux |
| Interprétation | FastAPI Sample sur TrueNAS `/api/homelab/status`, `/api/homelab/health` | Privileges internes, rapprochement, cache et fraîcheur ; HTTP 200 n'est pas santé fonctionnelle |
| Outside-in | FastAPI Cloud `/sickz` | Vantage PaaS distinct, preuve DNS/TLS/Access/WAN ; `DENIED` normal attendu possible, aucune preuve LAN déduite |
| Smoke **ponctuel** | Compose `verify-stack.sh`, smokes OTLP/syslog, CSI RWX, restore PostgreSQL | Conserver : prouve les chemins bout-en-bout et les capacités non visibles par une sonde récurrente |
| Administration et réparation | Nouveau dépôt pfSense, Compose pour TrueNAS/Talos, OpenClaw pour Gateway | Séparé de toute sonde continue, identité dédiée, opt-in et rollback |

**Candidates à l'amincissement, après preuve :**

1. `scripts/truenas/diagnose-service-readiness.py` : Docker et contrat local
   utiles ; centraliser les observations HTTP/Gatus/Prometheus déjà offertes
   par les deux FastAPI. Pas de nouveau polling continu.
2. `scripts/truenas/diagnose-fastapi-stack.py` : conserver les tests
   LiteLLM/OpenRAG et les assertions d'intégration ; remplacer la
   relecture générique de dashboard/Prometheus par snapshot daté.
3. `scripts/truenas/audit-app-lifecycle.sh` (1 673 lignes) :
   extraire seulement les blocs spécialisés avec tests, privilégier les
   primitives `scripts/lib/` existantes ; **garder** les preuves Docker,
   montages, permissions et secrets que FastAPI ne doit pas exposer.
4. `scripts/observability/verify-stack.sh` : garder comme test d'intégration,
   pas comme moniteur permanent ; éviter de relancer `/metrics?target=...`
   de l'exporter pfSense : **Prometheus seul** doit déclencher son scrape
   récurrent (300 s, collection sérialisée, selon runbook actuel).
5. `scripts/quality/service-observer-evidence.py` : garder le routeur
   mince, non un second moteur HTTP, avec verdict `NOT_RUN` distant.
   **L'association Cloud `/sickz` URL ↔ service `entityRef` reste à
   valider** sur le contrat et la source déployée avant verdict nominal.

**Ne pas supprimer** le contrôle de restauration isolée G1/H02,
les tests CSI H01, la preuve de non-exposition WAN, ni les smokes OTLP
de bout en bout ; aucun outil de supervision ne démontre ces propriétés.

## Frontières de privilèges et charges

| Profil | Accès minimal | Interdit / preuve |
| --- | --- | --- |
| Codex distant / CI | Git + tests hermétiques + catalogue public | Aucun LAN, SSH, `sudo`, clé ni exécution runtime ; `NOT_RUN` |
| PUBLIC outside-in | DNS/TLS/HTTP externe expurgé | Pas d'IP LAN, ports privés, secrets ou conclusion `DOWN` sur 403 Access |
| SERVICE observer | Jeton read-only, endpoint allowlist, scope et cache dédiés | Pas d'identité appliance admin ; taux et TTL bornés |
| OWNER FastAPI | Identité et source réseau contrôlées, DTO détaillé | Pas de permission pfREST write ou TrueNAS app.redeploy |
| OPERATOR-READ | Workstation confirmée ; identités API/SSH **read-only distinctes** par équipement | Rapports expurgés, délais bornés, pas de mutation ou `set -x` |
| OPERATOR-WRITE | Session humaine explicite ; plan, sauvegarde, apply, vérification, rollback | Jamais déclenché depuis Gatus, Prometheus, FastAPI Cloud ou CI |

Pour Netgate 1100, limiter les requêtes pfREST : le contrat existant
`scripts/observability/README.md` prévoit Prometheus seul, intervalle
300 s, collecteurs essentiels, concurrence 1 ; ne pas multiplier des
`curl`/metrics à chaque clic d'interface ou check.

## Plan d'exécution sans perte de preuve — H11, H07, H05

1. **D0 inventaire (no-op)** : figer les appels `just`, tests, scripts,
   docs, chemins importés et un SHA de chaque dépôt. Relever `git grep`
   des anciens chemins et les entrées `.gitmodules`, plus les
   caractéristiques CLI et schémas de sortie. Quantifier *les appels
   réellement redondants*, et non uniquement les fichiers.
2. **D1 cinq scripts communs OpenClaw** : tests de parité sur arguments,
   exit code, `--check`, payload/secret, absence de mutation ; imposer
   `nabla-openclaw` comme source, conserver des wrappers Compose fins et
   échouer si submodule/checkout absent au lieu d'utiliser une copie obsolète.
3. **D2 autres scripts workstation** : classer au cas par cas (Gateway →
   OpenClaw, OS → Ansible, UX → dotfiles, liaison inter-hôtes →
   Compose). Déplacer les tests au propriétaire ; garder seulement
   les contrats croisés et la restauration Workstation tant qu'elle est
   officiellement un rollback.
4. **D3 pfSense** : créer le dépôt après validation, copier les scripts
   et tests dans une PR dédiée, puis adapter les consommateurs Compose et
   leurs gates. Ajouter le gitlink **après** validation de la CLI et de la
   sauvegarde ; retirer l'implémentation ancienne seulement après
   parité check/API/SSH et stratégie de rollback, sans accès prod pendant CI.
5. **D4 rationalisation observabilité** : un seul inventaire Gatus et
   Prometheus, un seul cache/provenance par observateur et une recette
   d'acceptation E2E par usage. Remplacer les duplications de transports
   seulement après tests négatifs `DENIED`/`STALE`/`NO_SAMPLE` et
   budget CPU/net/SLA. Les tests de recovery et sécurité sont conservés.

**Critères de clôture :** aucun consommateur orphelin, une source canonique
par fonction, aucun test supprimé sans équivalent, historique/rollback
préservés, diagnostics read-only non dépendants de privileges write,
`just quality` et gates du propriétaire au SHA exact, preuves runtime
séparées. Aucun déplacement ou nouveau dépôt n'est effectué par cet ADR.

