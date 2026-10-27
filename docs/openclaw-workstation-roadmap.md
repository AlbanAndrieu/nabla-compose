# OpenClaw Workstation — roadmap opérationnelle dédiée

> Mise à jour : **27 octobre 2026** · propriétaire : **nabla-compose** ·
> statut : **PR #289 Draft, changements non déployés**.
> Périmètre : OpenClaw Workstation (agents `main`/`cron`), LiteLLM
> Workstation en amont, politiques et tâches planifiées. Le runtime
> TrueNAS et ses secrets restent distincts. Cette roadmap ne remplace
> pas `docs/roadmap.md` pour l'infrastructure générale.

## État et preuves

| Chantier | Code | Validation locale | Validation runtime |
| --- | --- | --- | --- |
| Auth /v1/models | Probe OpenRAG corrigé ; classifieur `MISSING_CLIENT_API_KEY`, préflight upstream fail-closed | 16/16 LiteLLM + 18/18 OpenRAG PASS avant extension du préflight | Nouvel appel sans clé depuis TrueNAS ; clés runtime et auteur SDK non attribués |
| Récupération ancienne config `nabla` | Inventaire limité aux politiques, pas de secrets | 5/5 PASS ; fichiers disponibles dans clone git-crypt déverrouillé | Pas de copie ou application |
| Digest | Manifeste non secret et diagnostic du skill | 3/3 manifeste PASS ; diagnostic upstream 16 tests non revalidés après dernière édition | Job réel conservé ; réussite éditoriale à confirmer |
| Sessions `cron` | Diagnostic complet, maintenance native `--dry-run`/`--enforce` | 5/5 parent + 6/6 maintenance PASS | **ACCEPTED maintenance** : 21 → 21, `pruned=0` ; parent toujours absent |
| HEARTBEAT | Politique native non générative ; briefing séparé, récupération historique documentée | 3/3 contrats PASS | Jobs anciens non restaurés |
| Copies historiques | Inspection privée et correction opt-in `0600` | 4/4 inspection + 8/8 tests PASS | **ACCEPTED** : 3 fichiers en 0600 ; inspection finale 3 `private` |
| LiteLLM TrueNAS cutover | Préflight et rollback déclarés | Contrats seulement | NON AUTORISÉ avant fermeture P0 Workstation |

**Limites probatoires :** les contrats unitaires ne prouvent ni
le fonctionnement effectif du Gateway ni l'authentification de
`/v1/models`. Chaque `ACCEPTED runtime` requiert une nouvelle
preuve datée sur la machine concernée.

## Réception opérateur — permissions et sessions (27/10, soirée)

- **PERMISSIONS ACCEPTED runtime :** nouvelle suite `8/8 PASS`,
  `openclaw-heartbeat-modes-apply` a modifié les **trois**
  fichiers `0644/0666 → 0600` ; contrôle ultérieur
  `openclaw-heartbeat-copies-check` affiche **trois `private`**
  et aucune extraction/modification de contenu. Clore le gate
  `mode bits` ; revue ACL étendue facultative et distincte.
- **CRON MAINTENANCE ACCEPTED runtime :** suite `6/6 PASS`,
  `--dry-run` puis `--enforce` retournent
  `beforeCount=21, afterCount=21, pruned=0, capped=0,
  missing=0`. La maintenance a été exécutée sans erreur
  mais n'a pas supprimé de session, conformément à la
  politique de rétention active.
- **PARENT ENCORE ABSENT :** `openclaw-cron-parent-check`
  renvoie `absent_in_reported_complete_catalog` sur les
  21 sessions. Ne pas qualifier le nettoyage de restauration
  de `agent:cron:main`. L'historique pouvant être perdu,
  une **suppression ciblée** avec prévisualisation reste
  facultative ; identifier au préalable le mécanisme UI
  de création de nouvelle session, sans réinitialiser les clés.
- **LITELLM TOUJOURS EN ÉCHEC :** un nouvel événement
  `No api key passed in.`, `user_api_key=null`,
  zéro token, UA `litellm/1.106.4`, IP source
  `172.17.0.24`. Un `GET /v1/models` anonyme
  **n'est pas** un événement 429. L'attribution exacte
  exige un contrôle des variables **dans le conteneur
  TrueNAS** et du client SDK.
- Le nouveau préflight `diagnose-workstation-litellm-upstream-auth.py`
  **bloque explicitement** les clés d'upstream manquantes et
  fournit la version du SDK LiteLLM du conteneur, sans afficher
  les valeurs ni envoyer de requêtes de modèles. Un match
  de version avec l'UA serait une **corrélation**, non une
  identification certaine de l'appelant.

```bash
# Workstation : suite offline, pas de modèle
just litellm-workstation-auth-contracts

# TrueNAS : depuis un checkout de la PR à jour, sans inférence
just litellm-workstation-upstream-auth-check
```

**Pas de cutover avant les preuves runtime.** Un statut
`all_present_unvalidated` indique seulement que les deux
variables sont non vides ; il ne prouve pas validité, scopes
ou injection d'un Bearer sur le client fautif.

## P0 — Stabiliser LiteLLM Workstation

- [x] Corriger le GET anonyme `/v1/models` du diagnostic OpenRAG
  (code #289, pas encore déployé sur TrueNAS).
- [x] Définir classificateur sans secrets `MISSING_CLIENT_API_KEY`.
- [x] Valider les tests locaux : 16/16 LiteLLM et 18/18 OpenRAG.
- [ ] **Attribuer la trace** `GET /v1/models`, source
  `172.17.0.24`, User-Agent `litellm/1.106.4` :
  rechercher le client TrueNAS exact avant de modifier ses clés.
  Ni User-Agent ni IP ne prouvent le composant.
- [ ] Vérifier liveness/readiness depuis les deux hôtes et
  la présence des variables d'upstream avec
  `just litellm-workstation-upstream-auth-check` sur TrueNAS.
- [ ] Qualifier séparément le 429 du chat `main` (clé scoped,
  quotas, spend, fenêtre, origine exacte et modèle), sans augmentation
  de budget ni appel modèle de diagnostic.
- [ ] Fin P0 : clients connus authentifiés, aucune sonde anonyme
  sur endpoint protégé, chat `main` accepté et preuve de 429 attribuée
  ou disparue sur fenêtre d'observation définie.

## P1 — Sessions : nettoyage maîtrisé (perte historique acceptée)

**Décision du propriétaire le 27/10** : le contenu historique des
sessions peut être perdu. Cela **n'autorise pas** la suppression des
identités, credentials, automatisations et caches vectoriels.

- [x] Lire catalogue `cron` complet : 21 sessions, `hasMore=false`,
  session principale `agent:cron:main` absente.
- [x] Définir un mécanisme natif `openclaw sessions cleanup`
  limité à l'agent `cron` dans un script redacted et des recettes
  explicites `--check` / `--apply` (PR #289).
- [ ] Exécuter le **plan de nettoyage** sur Workstation ;
  inspecter les compteurs et refuser tout état ambigu.
- [ ] Appliquer la maintenance `--agent cron --enforce`
  uniquement après validation du plan et hors tâche en cours.
- [ ] Vérifier que les jobs `daily-tech-news-digest`, les
  connexions et le modèle `cron` restent configurés.
- [ ] Si `/chat/cron` échoue encore, créer une nouvelle session
  via le parcours UI supporté plutôt qu'un lien parent invalide.
  **La maintenance ne crée pas `agent:cron:main`.**
- [ ] Option ultérieure : suppression individuelle ciblée via
  `openclaw sessions delete <clé> --agent cron --dry-run`,
  puis `--yes` ; jamais de reset config+creds+sessions, ni
  `rm -rf ~/.openclaw`.

## P1 — Sécuriser les copies HEARTBEAT

- [x] Inventorier les trois fichiers sans lire leur contenu :
  `.before-fix` écrivable par d'autres ; heartbeat historique
  et archive 993 378 302 octets lisibles par d'autres.
- [x] 6/6 tests du premier garde `0600` PASS.
- [ ] Confirmer le correctif du répertoire parent lié symboliquement
  dans le clone `nabla` (revue stricte de chemin canonique/inode).
- [x] `just openclaw-heartbeat-modes-test` : **8/8 PASS**.
- [ ] `just openclaw-heartbeat-modes-check`.
- [x] **Opt-in** `just openclaw-heartbeat-modes-apply`
  lorsque les trois identités attendues sont reconnues.
- [x] `just openclaw-heartbeat-copies-check` → exit 0 et
  trois classes `private`, puis examen des ACL supplémentaires
  si nécessaires.

## P2 — Migration non secrète `nabla` → `nabla-compose`

- [x] Identifier `git-crypt` dans le dépôt privé et les fichiers
  historiques localement lisibles.
- [x] Récupérer **les fonctions** du heartbeat : workboard,
  CalDAV, santé, observabilité, Gmail/WhatsApp, rapports périodiques ;
  aucune tâche lancée automatiquement par cette récupération.
- [x] Séparer Workboard `openclaw workboard list` et Tasks
  `openclaw tasks list` dans `MORNING_BRIEFING.md`.
- [ ] Revoir `AGENTS.md`, `SOUL.md`, `TOOLS.md`, les skills
  et leurs dépendances, puis créer de nouvelles versions
  expurgées dans `apps/openclaw/workstation/`.
- [ ] Préserver `IDENTITY.md`, `USER.md`, `.env`, modèles
  de clés, profils, bases SQLite et listes de contacts/sources
  privées **hors Git public**.
- [ ] Préparer le reconcileur GitOps de cron idempotent
  (`list / diff / apply` séparés) et les tests de non-duplication.
- [ ] Pin versions/hash des skills et ACL MCP ; aucun chargement
  automatique d'un MCP non approuvé dans l'agent `cron`.

## P2 — Workboard, briefing et HEARTBEAT

- [x] Reprendre les rubriques de l'ancien briefing :
  métriques, agendas, alertes, workboard, actions effectuées.
- [ ] Inventorier les timers/cron réellement actifs
  (ne pas confondre intention du document ancien et état runtime).
- [ ] Planifier, un par un, des collecteurs **déterministes**
  (Gatus/Prometheus, CalDAV et éventuellement WhatsApp)
  avec identité, ACL, journal de résultat et borne temporelle.
- [ ] Créer au besoin un unique briefing quotidien isolé et
  plafonné, avec sources datées ; coût et succès éditorial suivis.
- [ ] Maintenir le heartbeat natif non génératif jusqu'à
  preuve de stabilité de la facturation LiteLLM. Ne pas réactiver
  les cadences de 15 min / 30 min / 1 h directement dans le modèle.

## P3 — Migration contrôlée LiteLLM Workstation → TrueNAS

- [ ] Confirmer aliases `gpt-4.1`, `gpt-4.1-mini` réellement
  exposés par TrueNAS, clés `main`/`cron` distinctes persistées
  et budgets/quotas mesurés.
- [ ] Préflight authentifié et scopes sans publication des clés,
  aucune inférence de sonde routinière.
- [ ] Cutover **explicite** des providers OpenClaw avec point de
  rollback Workstation, puis vérification des jobs.
- [ ] Migration des embeddings/indices et RAG traitée séparément ;
  aucune substitution silencieuse des modèles vectoriels.

## Commandes opérateur

```bash
just litellm-workstation-auth-contracts
just truenas-openrag-startup-test
just openclaw-cron-parent-check
just openclaw-cron-session-maintenance-test
just openclaw-cron-session-maintenance-check
just openclaw-heartbeat-modes-test
just openclaw-heartbeat-modes-check
```

Voir également [runbook GitOps/workstation](runbooks/openclaw-workstation-gitops-migration-20261027.md),
[runbook digest](runbooks/openclaw-tech-digest-invalid-top-20261027.md)
et [récupération heartbeat](../apps/openclaw/workstation/LEGACY_HEARTBEAT_RECOVERY.md).

Aucun marqueur « DONE runtime » ne peut être posé à partir d'un
`[skip ci]` ou d'un test unitaire exécuté hors de la machine.
