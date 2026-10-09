# OpenClaw — stabilisation workstation puis migration TrueNAS

État initial : 2026-10-09. **Planifié, non exécuté**. Cette feuille de route est
distincte des transactions DSOMM/Sentry en cours et ne justifie aucun changement
automatique sur la workstation ou TrueNAS.

## Objectif et règles

Conserver la workstation comme instance de référence jusqu'à acceptance complète,
puis transférer configuration et état sur TrueNAS de manière contrôlée, réversible
et sans double traitement des messages. **Ne jamais copier les secrets ou l'état
réel dans Git**. Déploiement local-first, un changement à la fois, jamais de
merge automatique. Ne pas relancer GitHub Actions pour ce chantier.

États : `planned` = documenté ; `staged` = prêt sans trafic ; `accepted` =
vérifié en conditions réelles ; `cutover` = instance TrueNAS propriétaire
des canaux et automatisations. Ne pas confondre succès du dry-run et upgrade.

## Contrat fonctionnel — OpenClaw personnel / Hermes technique

**Destination souhaitée, non encore déployée.** Deux assistants distincts avec
des frontières explicites ; la migration d'hébergement ne doit pas fusionner
leurs rôles, secrets, mémoires, outils ou privilèges.

| Dimension | OpenClaw (personnel) | Hermes (technique) |
| --- | --- | --- |
| Mission | Trier et prioriser les messages Gmail et WhatsApp personnels ; préparer des synthèses et brouillons | Assistance développement, DevSecOps, cloud, infrastructure, cybersécurité et diagnostic |
| Sources | Boîte Gmail personnelle et conversations WhatsApp expressément autorisées | Repositories, documentation, logs techniques expurgés, outils de build et plateformes autorisées |
| Sorties | Briefs privés, labels/catégories proposés, réponses brouillon et rappels proposés | Analyses techniques, correctifs, runbooks, scripts et propositions de PR |
| Exécution | **Lecture seule par défaut** ; proposition avant archivage, étiquetage ou envoi | Read-only par défaut sur infra ; écriture Git explicite, changements runtime/production soumis à validation |
| Interdits | Accès implicite à SSH, pfSense, TrueNAS admin, Docker, Kubernetes, GitHub write, dépôt de secrets, communication à Hermes | Accès implicite aux mails/WhatsApp, contacts privés, sauvegardes personnelles et historique OpenClaw |
| Identités | Tokens Gmail/WhatsApp strictement dédiés ; stockage et logs privés | Identités dédiées GitHub/CI/cloud et permissions bornées |
| État | Sessions, historique de tri, règles personnelles, pièces jointes sous politique de rétention | Workspace de code, métriques et mémoire technique sans correspondance privée |

### Parcours personnel cible, par paliers de consentement

1. **P0 — observation** : connecter une seule source avec autorisations
   minimales ; inventorier métadonnées, dossiers et capacités réelles de
   l'intégration ; ne rien envoyer ni supprimer ; journaliser seulement les
   décisions et identifiants opaques nécessaires, pas les corps des messages.
2. **P1 — tri assisté** : proposer « urgent / à traiter / information /
   indésirable potentiel », avec justification courte, confiance et lien vers
   le message ; préserver les catégories et labels existants ; vérifier
   faux positifs, fils groupés, contacts importants, langue FR/EN et duplicats.
3. **P2 — brouillons privés** : préparer des réponses **sans envoi
   automatique** ; demander accord avant création/modification de brouillon
   et avant tout changement de label/archivage ; jamais de suppression
   automatique. Restreindre les destinataires et empêcher les réponses à
   des expéditeurs inconnus sans confirmation.
4. **P3 — routines explicites** : digest opt-in et alertes importantes
   configurables (pas de notification pour chaque message) ; déduplication
   et idempotence par source/compte/conversation/message ; aucune propagation
   des contenus personnels vers Slack, Discord, observabilité ou Hermes.
5. **WhatsApp** : vérifier les capacités et limites du canal réellement
   installé avant de promettre lecture exhaustive, marquage, archivage ou
   brouillons natifs. Démarrer par résumé et **proposition de réponse locale**,
   sans émission. Le statut de reconnexion 408 et la dérive de version du
   plugin sont des blocages fonctionnels jusqu'à résolution.

### Gouvernance, sécurité et contrôle qualité

- **Séparation stricte** : profils, identités système, volumes, bases/sessions,
  contextes LLM, mémoires et clés distincts ; aucun bus d'événements global
  partageant les corps des messages ; échanges inter-assistants désactivés
  sauf demande ponctuelle, expurgée et approuvée.
- **Données sensibles** : minimiser les scopes OAuth/Gmail, consentement
  explicite pour chaque compte, ne pas exporter les conversations dans Git
  ou dans des outils de télémétrie ; chiffrement au repos/en transit,
  redaction de PII et secrets, rétention limitée et export/suppression possibles.
- **Prompt injection** : considérer mail, HTML, liens, PDF et messages entrants
  comme entrées non fiables ; ils ne peuvent jamais déclencher outils admin,
  changements de permissions, achats, envois ou délégation à Hermes.
- **Modèles** : mesurer flux réels vers LiteLLM/proxy/providers (notamment
  logs, traces, embeddings et stockage éventuel de prompts). L'usage d'un
  modèle distant pour des messages privés nécessite une décision explicite ;
  préférer un traitement local/privé quand réalisable, et documenter le mode
  dégradé si le GPU de la workstation est indisponible.
- **Validation** : corpus synthétique Gmail/WhatsApp sans PII ; tests de
  classification, garde-fous de consentement, déduplication, absence de
  cross-tenant/cross-agent, comportements offline et rollback. Mesures
  pertinentes : précision du tri, taux de faux urgents, faux négatifs critiques,
  actions soumises à confirmation, zéro émission/suppression non autorisée.
- **Observabilité** : santé/intégrité des connecteurs, erreurs, latence et
  volumes agrégés seulement ; métriques Prometheus sans sujets, noms,
  adresses, numéros de téléphone, texte ou pièces jointes.
- **Hermes** : traiter séparément la roadmap de son déploiement technique ;
  ne pas lui accorder par héritage les privilèges ou connecteurs d'OpenClaw.
  Lors de la bascule TrueNAS, éprouver la séparation fonctionnelle en plus
  des tests runtime/reboot.

**Critère d'acceptation métier** : OpenClaw produit un digest de messages
personnels fiable, propose catégories et brouillons sans envoyer/supprimer ;
Hermes peut travailler sur code/cloud/sécurité sans voir les conversations
privées. Toute action mutatrice personnelle ou infrastructurelle nécessite
une autorisation limitée et traçable.

## Inventaire observé sur la workstation

- CLI/OpenClaw Gateway : `2026.9.5`; dry-run cible stable `2026.9.9`.
- Node CLI : `~/.local/share/mise/installs/node/24.18.1/bin/node`.
- Package et entrypoint effectifs :
  `~/.local/share/mise/installs/node/24.18.1/lib/node_modules/openclaw`.
- Service `~/.config/systemd/user/openclaw-gateway.service` actif :
  `ExecStart=/usr/bin/node .../openclaw/dist/index.js gateway --port 18789`.
  La différence entre Node systemd et Node `mise` explique le risque de
  sélection d'un préfixe npm étranger ; `/usr/lib/node_modules/openclaw` et
  `/usr/bin/openclaw` ne doivent **pas** être écrasés ou supprimés.
- Gateway seulement sur loopback `127.0.0.1:18789`, websocket probe OK.
- `doctor --non-interactive` a installé `@openclaw/firecrawl-plugin@2026.9.5` :
  **ne pas qualifier ce doctor de commande read-only**.
- Migration d'état Slack différée ; 29 anomalies SQLite ; une entrée
  `sessions.json` invalide ; aucune sauvegarde réussie enregistrée.
- WhatsApp plugin `2026.9.4` vs Gateway `2026.9.5` et reconnexion 408 ;
  un channel Discord non numérique ; `irc` hors de `plugins.allow`.
- `main` et `cron` : outils de messagerie absents pour certains canaux ;
  un cron en erreurs répétées, override modèle LiteLLM, et autorisation
  historique restrictive du job `daily-tech-news-digest`.
- Secrets en clair dans `openclaw.json` (Gateway, LiteLLM, Ollama, Slack) ;
  `browser.extensionRelay.allowLegacyAuth=true`.
- Skills `gemini`, `mcporter`, `summarize` indisponibles ; skill
  Vaultwarden invalide ; collisions de skills GitHub/GOG ; plugin
  `openclaw-code-agent` sans consentement de capacités.
- Le diagnostic recommande également un PATH systemd différent, et signale
  `device-pair` désactivé. **Ne pas ouvrir le Gateway sur LAN comme
  simple résolution de ce dernier avertissement**.

## P0 — workstation : sauvegarde et audit réversible

- [ ] Capturer sans secrets : versions Node/npm/OpenClaw, `systemctl --user cat`,
  `systemctl --user show`, service/Gateway status, inventaire des plugins,
  skills, canaux, crons et session migrations ; masquer tokens et variables.
- [ ] Réaliser une sauvegarde OpenClaw chiffrée ou à accès restreint, vérifier
  l'archive, puis faire un test de restauration **isolé**, sans livrer de
  messages, ni démarrer des connecteurs en double. Vérifier l'absence de
  credentials dans les logs, artifacts, Git et supports non chiffrés.
- [ ] Documenter explicitement les propriétaires de `/usr/bin/openclaw`,
  `/usr/lib/node_modules/openclaw`, du service et du préfixe npm.
  Conserver la cohabitation tant que le propriétaire de `/usr` est incertain.
- [ ] Conserver l'installation `mise` comme installation canonique ; aligner
  `ExecStart`, PATH, `NPM_CONFIG_PREFIX` et Node du service **après**
  sauvegarde et revue de l'unité, avec override systemd réversible si possible.
  Ne pas exécuter `gateway install --force` sans preuve d'ownership.
- [ ] Établir un health baseline : process, websocket Gateway, versions
  CLI/service, canaux par canal, exporter Prometheus, état des crons.

**Validation** : même version de Node pour CLI/service, seul paquet canonique
actualisé, Gateway actif et disponible sur loopback, archive restaurable.
**Rollback** : restaurer unité systemd et environnement précédents, conserver
les packages historiques, redémarrer seulement après revue des effets.

## P1 — workstation : convergence application et sécurité

- [ ] Avec Node et préfixe alignés, refaire `update --dry-run`, puis seulement
  lancer l'update réel en contrôlant les logs et le résultat. La version cible
  `2026.9.9` est une observation du 2026-10-09, **à revérifier**.
- [ ] Auditer `openclaw doctor --session-sqlite dry-run --session-sqlite-all-agents`.
  Sauvegarder l'état avant `update repair` et `doctor --fix`, puis comparer
  les identités des sessions et les transcripts ; conserver l'original.
- [ ] Résoudre la migration Slack avec la procédure officielle ; aligner les
  plugins officiels (dont WhatsApp), après vérification des compatibilités,
  et contrôler le rétablissement de chaque canal.
- [ ] Valider les IDs Discord, le consentement des capacités du code-agent,
  la policy IRC et les allowlists d'outils `message` de `main`/`cron` ;
  ne donner que les permissions nécessaires. Conserver Telegram en pairing
  et le Gateway en loopback par défaut.
- [ ] Examiner l'automatisation en backoff, le modèle `litellm-cron` et le
  périmètre autorisé de `daily-tech-news-digest`. Rejouer une exécution
  contrôlée sans doublon.
- [ ] Migrer les secrets de `openclaw.json` vers SecretRefs ou gestionnaire
  équivalent ; `openclaw secrets audit --check`, puis
  `openclaw security audit --deep` et contrôle des permissions.
- [ ] Actualiser l'authentification Browser Relay vers v2 avant de désactiver
  `allowLegacyAuth` ; vérifier clients Chrome/CDP.
- [ ] Corriger la metadata du skill Vaultwarden, arbitrer les collisions
  GitHub/GOG, activer/configurer ou désactiver les skills manquants et
  évaluer la migration des assets Codex sans élargir l'accès par défaut.
- [ ] Ajouter un wrapper local `just openclaw-audit` (lecture seule en propre,
  sans `doctor` mutateur), `just openclaw-backup` et smoke tests ; tester
  shellcheck/format/tests local-first avant publication.

**Acceptance P1** : pas de conflit de destination ; upgrade vérifié,
migrations documentées, sauvegarde/restauration prouvées, secrets hors JSON,
aucune erreur cron récurrente inexpliquée, plugins/canaux nécessaires OK,
Gateway sain après redémarrage et reboot workstation.

## P2 — conception du service cible TrueNAS (aucun cutover)

- [ ] Choisir une instance OpenClaw en **Custom App Compose** versionnée,
  image immuable et digest-pinnée, architecture adaptée, UID/GID non-root
  et volume persistant explicite. Ne pas déployer une seconde instance active
  qui traite les mêmes canaux ou tâches planifiées.
- [ ] Cartographier séparément (a) config Git non sensible, (b) secrets runtime
  dans stockage protégé, (c) sessions SQLite/transcripts, (d) plugins/skills,
  (e) cache temporaire, (f) sauvegardes. Définir ownership, ACL, dataset ZFS,
  snapshots et rétention. Utiliser les conventions `nabla-compose` et
  `/mnt/cpool` sans inventer de chemin avant revue de la topologie.
- [ ] Définir firewall/egress DNS, accès à LiteLLM sur workstation
  `172.17.0.57:4000` (machine intermittente), fallback en cas de panne,
  timeouts et isolation du navigateur. Privilégier accès local privé / tunnel
  authentifié au lieu d'exposer Gateway directement sur WAN/LAN.
- [ ] Produire déployeur idempotent `--check`/`--apply` et diagnostic compact,
  contrats de validation, métriques Prometheus, Gatus depuis TrueNAS,
  observabilité externe FastAPI si pertinente, aucune fuite des secrets.
- [ ] Préparer une restauration de snapshot dans un environnement **isolé**.
  Désactiver canaux, webhooks, automatismes et agents sortants sur cette copie.
- [ ] Documenter le modèle de menace : tokens, prompt injection via
  connecteurs, extensions tierces, isolation conteneur, privilèges d'agents,
  exposition réseau, contrôle des coûts LLM et limites ressources.
- [ ] Garder OpenTofu/Terragrunt import/no-op en option uniquement après
  acceptation Compose, sans transférer automatiquement le state Terraform.

**Acceptance P2** : instance TrueNAS restaurée et testée hors production,
state persistant et récupérable après redéploiement/reboot, egress et
authentification prouvés, aucun envoi de canal ni cron doublonné.

## P3 — bascule contrôlée, puis exploitation

- [ ] Définir fenêtre de maintenance et rollback, geler les mutations d'état,
  désactiver/cranter les automations et connecteurs entrants workstation,
  puis capturer un dernier backup + manifest/checksum et état des offsets.
- [ ] Copier état chiffré via canal protégé vers TrueNAS ; vérifier checksum,
  schéma SQLite, permissions et versions. Ne pas écraser les datasets existants.
- [ ] Ne basculer identités de canal, tokens/webhooks et automations que lorsque
  la source est **quiescée**. Vérifier qu'un seul Gateway détient chaque canal
  et exécute chaque job ; valider messages test et protections anti-doublons.
- [ ] Vérifier disponibilité, auth, canaux utiles, envoi/réception de test,
  crons, modèles LiteLLM, plugins/skills, Prometheus, redémarrage service,
  reboot TrueNAS, restauration et budget/alerting.
- [ ] Conserver la workstation comme reprise **inactive**, avec procédure
  de failback atomique ; ne supprimer anciens paquets/états qu'après période
  d'observation, rollback documenté et autorisation explicite.

**Acceptance P3** : TrueNAS seul propriétaire des flux, services sains après
reboot, sauvegarde/restauration démontrées et test de failback maîtrisé.

## Dépendances et blocages

- DSOMM/Sentry/TrueNAS foundation existants restent prioritaires : ne pas
  mélanger les transactions et ne pas rebaptiser du `planned` en `accepted`.
- La disponibilité de LiteLLM GPU workstation n'est pas garantie 24/7 ;
  concevoir le mode dégradé avant d'exiger un OpenClaw toujours disponible.
- L'instance TrueNAS ne doit pas avoir accès à Docker socket, datasets hôtes,
  réseau admin pfSense/TrueNAS ni secrets hors périmètre sans justification.
- Sources officielles : <https://docs.openclaw.ai/install/updating>,
  <https://docs.openclaw.ai/troubleshooting>,
  <https://docs.openclaw.ai/>.
