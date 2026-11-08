# Synergies d'intégration entre services — analyse du 7 novembre 2026

Analyse à partir de `catalog/service-topology.json` (142 nœuds, 280 relations)
et des Compose du dépôt. Chaque proposition distingue **Existant** (relation
déclarée), **Proposé** (capacité vérifiée dans la documentation du produit) et
**À vérifier** (capacité non confirmée). Rien ici n'est appliqué : les
propositions retenues deviennent des lignes de [roadmap](roadmap.md) avec
leur preuve d'acceptation.

## 1. Identité : un seul SSO via Keycloak (realm `nabla`)

Constat : **aucun** service ne déclare de relation vers `keycloak` ; chaque
application garde ses comptes locaux. Le realm `nabla` est prêt
(`apps/keycloak/config/realms/nabla.yaml`), Keycloak doit d'abord être démarré.

| Service | Mécanisme | Statut |
| --- | --- | --- |
| Dependency-Track | `ALPINE_OIDC_ENABLED/ISSUER/CLIENT_ID`, provisioning et synchronisation d'équipes par claim `groups` | Proposé (doc officielle) |
| NetBox | `REMOTE_AUTH_BACKEND=social_core.backends.keycloak.KeycloakOAuth2` (social-auth, netbox-docker) | À vérifier sur la version `v4.7` déployée |
| Grafana | `GF_AUTH_GENERIC_OAUTH_*` vers `/realms/nabla` | Proposé (fonction native Grafana) |
| Scanopy | fichier `oidc.toml.example` présent dans le projet | À vérifier |
| Open WebUI, Langfuse, LiteLLM UI, Portainer | OIDC supportés par les produits | À vérifier case par case (versions) |
| Joplin Server, n8n (communautaire) | pas d'OIDC | Comptes locaux conservés |

Ordre : Keycloak `RUNNING` → import du realm → un client par service (secrets
dans `/mnt/cpool/secrets/runtime/<service>/`, jamais dans le realm YAML) →
Grafana en premier (réversible), puis Dependency-Track, NetBox.

## 2. Chaîne sécurité applicative : SBOM → Dependency-Track → DefectDojo

Constat : rien n'alimente `defectdojo` ; Dependency-Track n'est pas déployé.

- **Existant :** `fastapi-sample` produit déjà un SBOM (`trivy-sbom.json`,
  groupe `cyclonedx-bom`) ; OpenSSF Scorecard tourne en job (`apps/scorecard`).
- **Proposé :** publier les SBOM CycloneDX de `fastapi-sample`, `nabla-site-alban`
  et des images Compose dans Dependency-Track (API `/api/v1/bom`, jeton
  d'équipe dédié) ; importer les findings Dependency-Track, Trivy, Scorecard,
  Wazuh et CrowdSec dans DefectDojo (parsers natifs) pour un suivi unique.
- Gate : un projet Dependency-Track par dépôt avec SBOM daté ; un *engagement*
  DefectDojo par source, sans doublons.

## 3. Réseau : source de vérité NetBox, découverte Scanopy, flux pfSense

- **Existant :** Akvorado et ntopng reçoivent les flux pfSense ; Pi-hole et
  Unbound/Kea tiennent DNS/DHCP ; `scanopy` découvre L2/L3 (Docker, Proxmox,
  UniFi, SNMP, SSH).
- **Proposé :** NetBox comme IPAM/DCIM de référence : y enregistrer les
  préfixes `172.17.0.0/24`, les VLAN IoT, les équipements (pfSense, TrueNAS,
  workstation) ; alimenter NetBox depuis l'inventaire Scanopy (API REST en
  lecture côté Scanopy, API NetBox côté écriture) par un script `--check/--apply`
  versionné ; faire pointer les réservations Kea/Pi-hole vers NetBox comme
  source déclarée (contrôle de dérive, pas de synchronisation automatique).
- **À vérifier :** export Prometheus de ntopng (aucune source documentaire
  trouvée) ; en attendant, la preuve ntopng est le stockage ClickHouse.

## 4. Observabilité : combler les angles morts Prometheus

- **Existant :** 14 services `observedBy prometheus` ; `nabla:telemetry:service_exporter_up` agrège les jobs ; FastAPI Sample lit cette série.
- **Fait dans cette PR :** jobs `dependency_track` (`ALPINE_METRICS_ENABLED`)
  et `netbox` (`METRICS_ENABLED`), ajoutés à la règle d'agrégation et à
  `_EXPORTER_JOBS` côté FastAPI.
- **Proposé :** alerte `NablaExporterTargetDown` étendue aux nouveaux jobs une
  fois les Apps démarrées ; Alertmanager → webhook n8n → Telegram (n8n est
  déjà déployé) ; Loki pour les journaux des Apps via Alloy (déjà en place
  pour la stack) ; Pyroscope déjà branché sur FastAPI Sample.
- Scanopy, Plumber, Joplin : pas d'export Prometheus connu → sondes Gatus
  (port/HTTP) uniquement.

## 5. Données : sauvegardes et dépendances PostgreSQL

- **Existant :** 16 services déclarent PostgreSQL ; `apps/postgres-backup`
  sauvegarde `keycloak`, `joplin`, `homeassistant`, `netbox`, `dependencytrack`,
  `scanopy` et `jobs` (Plumber) ; les bases absentes sont ignorées (`SKIP`)
  jusqu'à leur création.
- **Proposé :** étendre `BACKUP_DATABASES` à `defectdojo`, `langfuse`,
  `sentry`, `sonarqube`, `n8n` après vérification de la taille des dumps ; PITR via pgBackRest vers Garage S3 quand PostgreSQL sera une
  Custom App ; test de restauration mensuel planifié par le même cron.

## 6. IA : passerelle unique LiteLLM

- **Existant :** Open WebUI, Hermes et FastAPI Sample passent par LiteLLM ;
  Langfuse trace.
- **Proposé :** clés virtuelles LiteLLM par consommateur (budgets/quotas),
  SSO Keycloak sur l'UI LiteLLM et Langfuse (§1), métriques LiteLLM déjà
  scrapées (`litellm_hermes`).

## 7. Interconnexions à ne pas créer

- Pas d'exposition Internet de NetBox, Dependency-Track, Scanopy, ntopng,
  Plumber : accès LAN/Traefik `.int` ou Cloudflare Access avec Service Auth
  (`/sickz` doit rester sans `external=false … reachable`).
- Pas de jeton Databasus, Dependency-Track ou NetBox dans le realm ou dans les
  Compose : secrets runtime uniquement.
