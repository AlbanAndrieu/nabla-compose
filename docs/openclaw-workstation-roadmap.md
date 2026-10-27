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
| Auth /v1/models | Probe OpenRAG corrigé vers /health/liveliness ; classifieur `MISSING_CLIENT_API_KEY` | LiteLLM 16/16 + OpenRAG 18/18 PASS le 27/10 | Source exacte User-Agent `litellm/1.106.4` non attribuée ; proxy non attesté fonctionnel |
| Récupération ancienne config `nabla` | Inventaire limité aux politiques, pas de secrets | 5/5 PASS ; fichiers disponibles dans clone git-crypt déverrouillé | Pas de copie ou application |
| Digest | Manifeste non secret et diagnostic du skill | 3/3 manifeste PASS ; diagnostic upstream 16 tests non revalidés après dernière édition | Job réel conservé ; réussite éditoriale à confirmer |
| Sessions `cron` | Diagnostic complet, nettoyage natif borné prévisualisable | 5/5 parent PASS ; 21 sessions, `agent:cron:main` absent dans catalogue complet | Nettoyage non encore exécuté ; `/chat/cron` non accepté |
| HEARTBEAT | Politique native non générative ; briefing séparé, récupération historique documentée | 3/3 contrats PASS | Jobs anciens non restaurés |
| Copies historiques | Inspection privée et correction opt-in `0600` | 4/4 inspection + 6/6 tests initiaux PASS | Bloqué par symlink parent de `~/w/nabla` ; aucun chmod jusqu'au dernier relevé |
| LiteLLM TrueNAS cutover | Préflight et rollback déclarés | Contrats seulement | NON AUTORISÉ avant fermeture P0 Workstation |

**Limites probatoires :** les contrats unitaires ne prouvent ni
le fonctionnement effectif du Gateway ni l'authentification de
`/v1/models`. Chaque `ACCEPTED runtime` requiert une nouvelle
preuve datée sur la machine concernée.

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
- [ ] `just openclaw-heartbeat-modes-test`.
- [ ] `just openclaw-heartbeat-modes-check`.
- [ ] **Opt-in** `just openclaw-heartbeat-modes-apply`
  lorsque les trois identités attendues sont reconnues.
- [ ] `just openclaw-heartbeat-copies-check` → exit 0 et
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
