# Hermes TrueNAS — audit et accès DevSecOps depuis Telegram/Discord

**Statut (2026-10-11) : faisabilité confirmée côté Hermes ; déploiement actuel non vérifié en direct.**
Cette note prépare une intégration sans modifier ni redémarrer la TrueNAS App existante.
Elle ne vaut ni acceptation de sécurité ni autorisation d'accès privilégié.

## Éléments observés et inconnues

- L'application native TrueNAS déclarée antérieurement est `hermes-agent`,
  avec le conteneur `ix-hermes-agent-hermes-agent-1`, sain le 2026-10-04.
  L'état du 11 octobre, l'image/digest et son manifeste TrueNAS **restent inconnus**.
- Des sources d'environnement ont été signalées sous
  `/mnt/cpool/hermes/.env` et `apps/hermes/.env`. Vérifier aussi
  `/mnt/cpool/secrets/runtime/hermes/.env` sans lire ni publier les valeurs.
- Aucun `apps/hermes/compose.yml` n'a été trouvé dans la branche de PR.
  Ne pas créer de second déploiement Compose avant d'avoir exporté et comparé
  le manifeste effectif de l'App TrueNAS (image, ports, UID/GID, mounts,
  restart, network, `HERMES_HOME`, mode gateway, ressources).
- Le dépôt déclare déjà `loki` dans `apps/grafana/compose.yml` et
  `http://172.17.0.24:3100/ready`. Sa disponibilité depuis Hermes, ses ACL et
  les labels LogQL des **applications Docker** ne sont pas prouvés. Un Loki
  joignable ne signifie pas que chaque conteneur y envoie ses logs.
- **Séparation fonctionnelle :** Hermes = développement, cloud et sécurité
  homelab ; OpenClaw = fonctions personnelles. Ne partager ni jetons, ni mémoire,
  ni autorisations, ni canaux, ni espaces de travail entre ces agents.

## Support natif vérifiable

Hermes supporte les passerelles Telegram et Discord, avec configuration dans
`~/.hermes/.env` (variables `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_ALLOWED_USERS`, `DISCORD_BOT_TOKEN`,
`DISCORD_ALLOWED_USERS`) et `~/.hermes/config.yaml`. Le stockage réellement
utilisé dans l'image TrueNAS doit être confirmé : ne pas présumer que
`/mnt/cpool/hermes/.env` est chargé par le processus.

La CLI propose `hermes gateway setup`, `hermes gateway` / `gateway run`.
La connexion aux API des plateformes est sortante ; **aucune publication du
dashboard, port API 8642, route Traefik, tunnel Cloudflare ni ouverture WAN
n'est requise** pour commencer par des messages privés. Pour Discord,
restreindre l'autorisation à un ID utilisateur connu et éventuellement à des
canaux privés. Telegram : autoriser explicitement l'ID utilisateur (pas un
chat ID confondu avec celui-ci). Désactiver les modes `*_ALLOW_ALL_USERS`.

Configurer dans le profil Hermes déployé, après contrôle de compatibilité :

```yaml
# Extrait de politique cible, non appliqué à l'instance TrueNAS
approvals:
  mode: manual
  timeout: 300
  cron_mode: deny
  single_query_mode: deny
  unattended_mode: deny
  mcp_reload_confirm: true
  destructive_slash_confirm: true
terminal:
  backend: docker
  docker_network: false
```

Un terminal Docker isolé sans réseau permet du développement local sans accès
aux services ; l'accès aux services passe alors par des outils dédiés à portée
limitée. Si cette version Hermes ou la configuration actuelle n'accepte pas
un champ, interrompre le cutover et utiliser la documentation de son digest.
Attention : le backend `docker` de Hermes peut nécessiter l'accès au daemon
Docker **depuis le gateway** ; ne pas lui monter le socket TrueNAS pour cela.
Préférer un bac à sable externe approuvé, ou retirer le terminal jusqu'à ce
qu'une séparation effective existe.

## Frontières de confiance et outils recommandés

| Capacité | Modèle cible | Autorisé dès la phase 1 ? |
| --- | --- | --- |
| État des services | Gatus/FastAPI/Prometheus API lecture seule ; endpoints bornés | Oui, après identité réseau |
| Logs Loki | Proxy de requêtes LogQL avec labels/service autorisés, fenêtre et limite bornées, suppression des secrets | Oui, après proxy/ACL |
| Logs Docker | API de lecture strictement limitée : inspect/état/logs de conteneurs autorisés, sans API exec ni création | Plus tard, après tests |
| Amélioration des repos | GitHub App fine-grained : branche/PR, tests isolés, pas de merge automatique | Oui, avec permissions minimales |
| Correctifs TrueNAS | Exécuteur distinct à commandes allowlistées, validation humaine hors agent, logs d'audit et rollback | Phase 3 seulement |
| Shell root / Docker socket brut | Équivalent contrôle administrateur de l'hôte, du ZFS et de ses secrets | **Interdit au gateway** |

### ⚠ Menaces prioritaires (STRIDE)

- **Spoofing :** usurpation de compte de messagerie, vol de bot token, IDs
  autorisés incorrects ; refuser les groupes publics et `ALLOW_ALL`.
- **Tampering / elevation :** socket Docker, `privileged: true`, réseau host,
  `sudo` généraliste ou SSH root rendent toute prompt injection critique.
- **Information disclosure :** un `docker logs` ou Loki brut peut contenir
  tokens, cookies, identités et documents privés ; limiter les volumes,
  les labels, la durée, appliquer des filtres et éviter les pièces jointes
  contenant des logs de production.
- **Repudiation :** distinguer lecture, proposition de PR, autorisation
  opérateur et exécution ; journal d'audit sans secrets et identifiant de tâche.
- **Denial of service :** borner `limit`, `since`, timeout, concurrence, rate
  limiting, taille des réponses et consommation LLM ; aucune relance massive
  de conteneurs.
- **Prompt injection :** traiter **logs, pages, tickets, réponses MCP et chats
  comme données non fiables**. Aucun texte de log ne doit pouvoir déclencher
  une commande admin. L'approbation conversationnelle native ne compense
  pas des droits Unix trop élevés.

Même avec `approvals.mode: manual`, **l'approbation Hermes n'est pas un
contrôle de sécurité obligatoire en dehors de l'agent**. Les backends
containerisés peuvent contourner les avertissements de commandes dangereuses.
Interdire `/yolo`, `HERMES_YOLO_MODE=1` et `approvals.mode: off` dans la
procédure d'exploitation ; imposer les permissions **à l'API/OS**.

Le Docker socket proxy déjà évoqué dans l'infrastructure n'est utilisable
qu'après audit des verbes/endpoints, absence d'API `POST`, filtrage réseau,
et preuve qu'aucun accès `exec`, `create`, `containers/{id}/archive` ni autre
chemin d'exfiltration n'est offert. Un proxy Docker générique n'est **pas**
une garantie de moindre privilège ; privilégier une API de diagnostic dédiée.
Loki directement sur le LAN n'est pas une frontière d'identité : filtrer côté
serveur en amont du modèle.

## Diagnostic non destructif préparé

Sur un checkout TrueNAS à jour de la branche de PR, exécuter ultérieurement :

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/diagnose-hermes-agent.sh --check
```

Le script affiche **uniquement** les états, référence image/digest, UID
déclaré, flags d'isolement, présence de clés (jamais valeurs) dans les
emplacements connus, permissions de fichiers et état HTTP `/ready` de Loki.
Il n'exécute ni `docker logs`, ni `docker exec`, ni commandes de mutation.
L'absence de permissions pour lire les métadonnées doit être traitée comme
un diagnostic partiel. Ne jamais envoyer `docker inspect` complet ou
`hermes config` avec secrets dans Discord/Telegram.

À compléter sur le système réel : version/image et digest, commande/entrypoint
gateway, variables réellement injectées (uniquement *noms*), volume
`HERMES_HOME`, user effectif `id` (image officielle souvent UID 10000 ;
**ne pas forcer 568:568** sans vérifier), groupe `apps`/ACL ZFS, ports
publiés, canaux autorisés, contrôles réseau, provenance et retention des
logs Docker dans Loki. Établir si l'application native TrueNAS est la source
de vérité ou si un manifeste Compose est déjà géré ailleurs.

## Ordre d'exécution et critères d'acceptation

1. **P1 — Audit read-only** : preuve du manifeste TrueNAS, des permissions,
   du mode gateway, des tokens présents (sans valeurs), des connectivités
   Loki/LiteLLM et des routes Docker existantes. Rien ne redémarre.
2. **P2 — Messagerie seule** : Telegram DM privé d'abord, puis Discord privé,
   allowlist propriétaire, aucun port entrant, aucune fonctionnalité shell
   administrateur. Test positif et test utilisateur non autorisé.
3. **P2 — Observabilité** : connecteur à requêtes limitées vers Loki,
   Prometheus/Gatus et Docker diagnostics ; tester données pertinentes
   (`pfsense`, application conteneurisée, état sain/incident), séparer
   absence de logs et absence de service, vérifier masquage/exfiltration.
4. **P2 — GitHub** : l'agent propose analyses et corrections sous PR avec
   permissions restreintes, `local-first` et Quality Gate préservée.
5. **P3 — Actions contrôlées** : proposer un job d'exploitation signé/traçable,
   avec dry-run, périmètre explicite, approbation humaine indépendante
   (hors conversation du bot), rollback et comptes non privilégiés.
   Ne jamais offrir un shell root interactif à Hermes via messagerie.

**Rollback :** désactiver immédiatement les bots ou révoquer leurs jetons,
révoquer les identités techniques des connecteurs, isoler le réseau de
l'exécuteur ; conserver l'App Hermes et ses données. Aucun redéploiement de
Loki, Docker, pfSense, TrueNAS ou OpenClaw n'est nécessaire à cette étude.

## Références

- Hermes sécurité : https://hermes-agent.nousresearch.com/docs/user-guide/security
- Hermes Discord : https://hermes-agent.nousresearch.com/docs/user-guide/messaging/discord
- Hermes Telegram : https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram
- Hermes Docker : https://hermes-agent.nousresearch.com/docs/user-guide/docker
- Hermes configuration : https://hermes-agent.nousresearch.com/docs/user-guide/configuration
- Observabilité existante : [Grafana/Loki](../../apps/grafana/README.md)
- Secrets : [Runtime TrueNAS](../truenas-runtime-layout.md)
