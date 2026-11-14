# Exécution des agents — Workstation locale ou Codex distant

**Autorité :** [AGENTS.md](../AGENTS.md). Ce document est chargé uniquement
pour l'outillage, les diagnostics, la reprise de PR ou une question sur le
contexte d'exécution. Une capacité *déclarée* ne prouve jamais un accès réel.

## Choisir le mode avant les outils

| Capacité | Claude Code sur Ubuntu Workstation | Codex distant / GitHub API sans hôte |
| --- | --- | --- |
| Sources, branches, PR | Git local et worktree dédiés | GitHub connector, branche et blob SHA attendus |
| Exécution | `mise`, `just`, Python/Node, containers **si présents et autorisés** | Tests hermétiques dans l'environnement distant **s'ils existent** ; sinon AST/lint/source |
| Diagnostic de services | Endpoints locaux, SSH/TrueNAS, Docker, systemd, DNS **si l'hôte et les droits sont vérifiés** | **NOT_RUN** : ne pas inventer un résultat depuis README, logs anciens ou manifestes |
| Secrets et hardware | Contrôle expurgé, lecture seule par défaut ; mutation explicite et tracée | **Jamais** exporter les secrets, sessions, clés, PIN/PUK/PIV ni manipuler la carte |
| Publication | L1 ciblé → `agent-loop` → `agent-fix` → commit → `agent-pre-push` | Un patch borné, syntaxe/tests disponibles ; marquer L2/L3 **NOT_RUN** et demander gate local avant fusion |
| Coût | Réutiliser GPU/CPU/RAM **pour les tests du sujet**, pas pour un scan global systématique | Réduire les appels aux connecteurs et ne jamais déclencher CI/déploiement pour obtenir l'accès hôte |

`Claude Code` ne prouve pas automatiquement qu'on tourne sur la Workstation ;
`Codex` peut disposer d'un checkout/test local isolé sans accès au homelab.
**Tester les capacités effectivement présentes**, puis choisir le niveau de
preuve. `--mode workstation` n'autorise pas à lui seul sudo, SSH, Docker, BW ou
des changements de configuration. Ne jamais escalader silencieusement.

## Boucle compacte et critères d'arrêt

1. **Cadrer** : une PR choisie, état (merged/draft), HEAD et fichiers touchés ;
   au besoin lire seulement le runbook associé. Ne pas recharger les 30 kB
   d'instructions et toute la roadmap à chaque itération.
2. **Plan ciblé** : `python3 scripts/quality/agent-diagnostics.py --scope
   policy|compose|openclaw|secrets|services --mode workstation|remote`. Ce plan est
   *read-only*, n'exécute rien et fournit des états `NOT_RUN`.
3. **Local** : `--execute` n'exécute que les contrats offline explicitement
   sélectionnés. Les diagnostics réseau/TrueNAS restent dans les recettes
   `just` existantes, sur l'hôte autorisé, avec validation des prérequis.
   Ne jamais lancer `just quality` dans une boucle de petits changements.
4. **Distant** : éditer uniquement source/tests/docs, puis valider
   syntaxe et contrats dans son propre environnement si possible ;
   sinon déposer une PR Draft avec les commandes ciblées pour Workstation.
   Un statut `BLOCKED`/outil absent est `UNVERIFIED`, pas `PASS` ni `DOWN`.
5. **Publier** : comparer le HEAD exact, ne pas écraser un concurrent ;
   pas de mutation sur `master`, pas de merge/CI supplémentaire sans feu vert.
   Donner un compte rendu compact : fichiers, preuves L0/L1/L2/L3,
   conditions GO/NO-GO et prochain test local.

## Économie de contexte et de ressources

- Lire `AGENTS.md` une seule fois, puis **un seul skill pertinent** et au
  besoin sa référence conditionnelle. Les adaptateurs `CLAUDE.md` et
  `agent.md` ne répliquent pas les règles du dépôt.
- `rg` / diff ciblé / lignes bornées, pas de récursion dans submodules,
  archives, rapports générés ou données utilisateur. Logs : première erreur,
  maximum un extrait borné ; compléter uniquement si insuffisant.
- Tests : ciblé L1 en premier ; `agent-loop` sur batch ; `agent-fix`
  une fois ; `agent-pre-push` une fois sur le commit. Ne pas affaiblir les
  gates de sécurité, ne pas masquer un échec par un skip.
- Les sondes coûteuses (Docker, SSH, Prometheus, API, navigateur, modèles)
  ne doivent pas être répétées si le snapshot/cadence est encore pertinent.
  Ne pas provoquer de requêtes LLM payantes pendant la validation offline.
- Le mode distant doit **produire du code vérifiable** plutôt que réclamer
  indéfiniment un accès impossible. La confirmation runtime reste une tâche
  d'exécution Workstation séparée, non simulée.

## Sources d'autorité à charger selon le sujet

| Sujet | Source ciblée |
| --- | --- |
| Qualité / publication | [skill local-first-quality](../.agents/skills/local-first-quality/SKILL.md) |
| Architecture stockage / secrets | [architecture](agent-skills-architecture.md), `homelab-secrets` |
| TrueNAS live | `homelab-runtime-status`, runbook du service |
| Compose / catalogue v2 | `docker-compose-orchestration`, `nabla-service-catalog` |
| pfSense / réseau | `pfsense-api-debugging` |
| Ubuntu / YubiKey matériel | `ansible-workstation` / `nabla-yubikey` respectivement |

Une interruption temporaire du homelab est acceptable **quand la mutation est
autorisée** ; secrets, intégrité des données, réseau/WAN et permissions restent
protégés. Aucun changement hardware YubiKey sans accord explicite.

## Sources de diagnostic — ordre de confiance

1. **TrueNAS, interne (priorité)** : `http://172.17.0.24:8091/api/homelab/status` puis `/api/homelab/health`. L'API hébergée sur TrueNAS observe les sondes et fournisseurs internes autorisés. Examiner également le timestamp, le cache et les erreurs d'authentification.
2. **FastAPI Cloud, externe (indépendant)** : `https://fastapi-sample.fastapicloud.dev/sickz`. Le processus FastAPI Cloud effectue des sondes **outside-in** depuis un environnement hors LAN. Recevoir HTTP 200 du domaine Cloud ne prouve ni l'exposition ni la santé des services cibles.
3. **Approfondissement ciblé** : sondes directes TrueNAS, Gatus, Prometheus, pfSense uniquement lorsque les deux observateurs ne suffisent pas. Aucune connexion directe implicite vers une IP extraite du catalogue.

Les états `DENIED` (401/403), `UNVERIFIED` (timeout, erreurs transport ou formats), `STALE` et `NOT_RUN` sont **distincts** de `DOWN`. Aucun résultat de diagnostic runtime n'est supposé depuis un Codex distant. Le collecteur `scripts/quality/service-observer-evidence.py` affiche seulement des champs allowlistés et limite la collecte à trois endpoints et trois services.

Commande workstation : `AGENT_EXECUTION_MODE=workstation bash scripts/agent-diagnostics.sh --runtime gatus prometheus`. Plan sans requête : `python3 scripts/quality/agent-diagnostics.py --scope services` ; contrat hermétique : `just agent-diagnostics-tests`.
