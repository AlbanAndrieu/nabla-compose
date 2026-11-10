# PostgreSQL 16 → 18 : cible FIPS, TLS 1.3, Keycloak/OAuth et Vault

Date : 2026-11-10. Statut : **CODED (documentation) / NOT_VERIFIED (runtime)**. Aucune mutation de base, certificat, compte, `pg_hba.conf`, secret ni réseau.

## Décision de sécurité

- **Cible homelab : alignement FIPS 140-3 vérifiable**, avec inventaire des modules, modes et algorithmes, sans prétendre que PostgreSQL/TrueNAS sont certifiés. Le règlement DORA ne rend pas FIPS obligatoire de façon générale ; appliquer une politique cryptographique fondée sur les risques (articles 6 et 9).
- **P0** : documenter la version réelle de PostgreSQL TrueNAS (l'App native n'est pas définie comme service serveur dans `apps/postgres/compose.yml`, qui ne contient que l'exporter), les paramètres TLS, les chaînes de confiance et tous les clients.
- **P0** : SCRAM-SHA-256 pour les rôles techniques ; inventorier MD5 sans afficher les hashes, puis rotation contrôlée. Ne pas supprimer les accès de secours avant validation.
- **P1** : imposer TLS 1.3 pour les connexions TCP **uniquement après matrice de compatibilité et vérification SAN/CA**, retirer TLS 1.0/1.1 et suites obsolètes, limiter TLS 1.2 selon exigences et capacité des clients. PostgreSQL 16 supporte déjà TLS 1.3 ; `ssl_tls13_ciphers` est nouveau en PostgreSQL 18.
- **P1** : passage HashiCorp Vault/OpenBao database secrets engine pour les identifiants temporaires des services. Vaultwarden est aujourd'hui la source de vérité transitoire ; la présence du Helm Vault dans Git n'atteste pas l'activation du moteur ni sa disponibilité. Politique de rotation, TTL, révocation, gestion des pools et chemin break-glass obligatoires.
- **P2** : PostgreSQL 18 et preuve de restauration ; tester OAuth natif pour DBA/psql via Keycloak realm `nabla`, validator explicitement audité, `issuer`/`audience`/`exp`, mapping minimal des rôles, refus des élévations. Conserver SCRAM ou certificat pour les workloads. OAuth PostgreSQL 18 n'est pas automatiquement OIDC et nécessite un validateur.
- **P2** : migration OIDC des utilisateurs applicatifs vers Keycloak ; les jetons OIDC API sont distincts des comptes techniques SQL ; conserver autorisation au niveau des APIs.

## Constats vérifiables dans le dépôt (pas dans la production)

| Composant | Indice Git | Risque / statut |
| --- | --- | --- |
| Keycloak | `apps/keycloak/compose.yml` image `keycloak:26.8.2`, `KC_DB_TLS_MODE=verify-server` et CA PEM en lecture seule | **CODED** : authentification TLS serveur exigée ; **NOT_VERIFIED** : certificat, IP SAN/DNS SAN, TLS réel et déploiement. |
| Plumber | `apps/plumber/compose.yml` : `JOBS_DB_SSLMODE: verify-full` et `PGSSLROOTCERT` | **CODED** : connexion vérifiée exigée ; **NOT_VERIFIED** : respect de `PGSSLROOTCERT` par le driver backend réel, CA et test runtime. |
| SonarQube | `apps/sonarqube/compose.yml` : URL JDBC par défaut sans paramètre TLS explicite | Configuration réelle à qualifier ; `verify-full` selon driver JDBC et truststore. |
| Dependency-Track | `apps/dependency-track/compose.yml` : URL JDBC par défaut sans paramètre TLS explicite | Configuration réelle à qualifier et certificat Java/truststore à valider. |
| postgres-exporter | `apps/postgres/compose.yml` : DSN dans `/mnt/cpool/secrets/runtime/postgres-exporter/.env.secrets` | SSL mode inconnu ; ne jamais lire ou journaliser le mot de passe. |
| FastAPI Sample | `mise.toml` déclare `POSTGRES_HOST/USER/PASSWORD`; la topologie seule ne prouve pas un OIDC FastAPI actif | Auditer code runtime, JWT validation, audience, endpoints et session ; **OIDC actuellement non prouvé**. |
| Keycloak SSO | `docs/integration-synergies-20261107.md` indique qu'aucun service n'est encore déclaré consommateur de Keycloak | Intégration SSO cible, non réceptionnée ; ne pas présenter comme déployée. |
| Vault | `config/secrets/README.md` : Vaultwarden source transitoire, Vault/OpenBao cible future | Moteur PostgreSQL dynamic credentials **non prouvé activé**. |
| Certificat SQL | Pas de preuve identifiée dans les configurations Git inspectées d'un `ssl_cert_file`, `ssl_key_file`, CA, SAN, ou gestionnaire de renouvellement de l'App PostgreSQL TrueNAS | Gestion du certificat **inconnue** ; TLS Cloudflare/HAProxy n'est pas une preuve de TLS PostgreSQL bout à bout. |

Ces écarts sont des risques de configuration à qualifier ; pas une affirmation qu'une connexion de production est actuellement en clair.

## Modifications Compose effectuées après accord de coupure (10 novembre 2026)

**CODED, non déployées** : Keycloak et Plumber sont actuellement inutilisés
selon l'opérateur. Leur indisponibilité temporaire est acceptée ; les deux
définitions Compose peuvent échouer en mode fermé jusqu'à provisionnement
du certificat. `apps/keycloak/compose.yml` impose
`KC_DB_TLS_MODE=verify-server` et une CA PEM montée en lecture seule.
`apps/plumber/compose.yml` fixe `JOBS_DB_SSLMODE=verify-full` et monte
la même CA dans API et worker ; `PGSSLROOTCERT` doit être confirmé sur
l'image Plumber lors du premier test de connexion. Le défaut Keycloak par IP
nécessite un **IP SAN** valide, ou le remplacement par `KEYCLOAK_DB_HOST`
pointant vers un nom DNS couvert par le certificat.

**Règle homelab** : un redémarrage ou une interruption ne bloque plus la
modernisation, y compris sur des services partagés. Cela ne permet pas
la suppression de données persistantes ni des sauvegardes sans autorisation
spécifique, ni la désactivation de contrôles cryptographiques. Le changement
de configuration serveur PostgreSQL reste **NOT_VERIFIED/NOT_APPLIED**,
car son certificat, son chemin et l'accès TrueNAS runtime ne sont pas
accessibles depuis cette PR.

## Matrice d'acceptation des clients PostgreSQL

- [ ] Keycloak / JDBC : `KC_DB_TLS_MODE=verify-server` (déclaré), `KEYCLOAK_DB_HOST` ou IP avec SAN correspondant, truststore PEM, redémarrage et reconnexion après rotation
- [ ] SonarQube / JDBC : driver Java et truststore, test TLS 1.3 et SQL applicatif
- [ ] Dependency-Track / JDBC : driver Java, gestion des migrations
- [ ] Plumber : `JOBS_DB_SSLMODE=verify-full` déclaré ; vérifier respect effectif et chargement de `PGSSLROOTCERT` par le driver
- [ ] postgres-exporter : DSN runtime expurgé, `sslmode=verify-full`, récupération métriques sans secret
- [ ] FastAPI Sample et éventuels clients asyncpg/psycopg ; vérifier les chemins réseau réels, les racines de confiance et pool reconnect
- [ ] LiteLLM, Langfuse, Sentry, n8n, SonarQube, NetBox, Joplin, Home Assistant, Scanopy, DefectDojo : confirmer connexion au PostgreSQL partagé, driver, TLS, extension, protocole de migration et rollback
- [ ] Clients d'administration : `psql`, jobs backups/restores, scripts de bootstrap, éventuels pools PgBouncer, observabilité
- [ ] Toute instance PostgreSQL Workstation distincte de TrueNAS : qualifier séparément, ne pas globaliser le cutover

Un échec TLS ou OAuth d'un client ne doit pas être étiqueté « application incompatible » sans preuve de test.

## Audit préliminaire strictement en lecture seule

Depuis une session `psql` déjà autorisée (la requête sur `pg_authid` requiert des droits élevés ; elle ne retourne jamais le hash brut) :

```sql
SELECT version();
SHOW ssl;
SHOW ssl_min_protocol_version;
SHOW ssl_max_protocol_version;
SHOW ssl_ciphers;
SHOW ssl_ca_file;
SHOW ssl_cert_file;
SHOW ssl_key_file;
SHOW password_encryption;
SELECT a.usename, a.application_name, a.client_addr, s.ssl, s.version, s.cipher
FROM pg_stat_activity a JOIN pg_stat_ssl s USING (pid)
WHERE a.backend_type = 'client backend';
SELECT rolname,
  CASE WHEN rolpassword IS NULL THEN 'NO_PASSWORD'
       WHEN rolpassword LIKE 'SCRAM-SHA-256$%' THEN 'SCRAM'
       WHEN rolpassword LIKE 'md5%' THEN 'MD5' ELSE 'OTHER' END AS password_format
FROM pg_authid WHERE rolcanlogin;
SELECT line_number, type, address, auth_method, error
FROM pg_hba_file_rules ORDER BY line_number;
```

**Ne pas collecter** `rolpassword`, `DATABASE_URL`, `PGPASSWORD`, clés privées, ni fichiers secrets en sortie des diagnostics. Les champs `ssl_*_file` peuvent révéler un chemin mais ne prouvent pas que le certificat est valide. Le certificat effectivement présenté doit être comparé au DNS, SAN, CA et dates d'expiration (sans exporter la clé).

## Proposition de configuration future (non appliquée)

Avant d'activer, fournir un certificat serveur valide couvrant le **nom DNS** utilisé par tous les clients, une CA distribuée aux clients et une preuve de compatibilité :

```conf
ssl = on
ssl_min_protocol_version = 'TLSv1.3'
password_encryption = 'scram-sha-256'
# PostgreSQL 18 seulement : ssl_tls13_ciphers à définir si politique cryptographique spécifique.
```

Dans `pg_hba.conf`, autoriser explicitement `hostssl` depuis les réseaux/applications nécessaires avec `scram-sha-256`, puis tester les refus non-TLS. Un `hostssl` seul ne bloque pas d'autres règles `host` plus larges ; revoir l'intégralité de l'ordre des règles. La restriction `ssl_min_protocol_version` ne remplace pas `sslmode=verify-full` côté client.

## HashiCorp Vault : choix d'architecture

- `database/config/postgres` avec `postgresql-database-plugin` et `sslmode=verify-full`; utiliser un principal bootstrap à privilèges minimaux pour la création/rotation SQL et une CA approuvée.
- Dynamic roles pour services capables de renouveler à chaud ; TTL et gestion de la fermeture des pools avant révocation.
- Static roles et rotation quand les applications ne supportent pas les credentials éphémères ; orchestrer le redémarrage ou rechargement sans rupture.
- Rotation du credential Vault de gestion après un test de récupération, une sauvegarde restaurée et preuve de révocation.
- Ne pas injecter une identité OAuth humaine dans des workloads ; ne pas dépendre du service Keycloak pour restaurer sa propre base.

## Conditions de livraison

1. **Inventaire** : versions, clients, paramètres serveur effectifs, certificats et topologie expurgés, état `CODED / TESTED / ACCEPTED`.
2. **TLS** : `verify-full` validé pour chaque consommateur ; `pg_stat_ssl.version = TLSv1.3` pour les sessions TCP attendues ; tests de refus de clients faibles.
3. **SCRAM** : absence de rôles MD5 après rotation ; tests positifs/négatifs HBA.
4. **Vault** : secret lease renouvelable, révocation testée, continuité applicative et accès de secours.
5. **OAuth DBA** : module de validation audité, MFA Keycloak, claims et mapping de rôles contraints, révocation et traçabilité ; test de coupure Keycloak.
6. **Migration PG18** : sauvegarde + restauration indépendante, `pg_upgrade --check`, extensions compatibles, downtime/rollback mesurés.

Sources :
- DORA : https://eur-lex.europa.eu/eli/reg/2022/2554/oj
- PostgreSQL OAuth : https://www.postgresql.org/docs/18/auth-oauth.html
- PostgreSQL validator : https://www.postgresql.org/docs/18/oauth-validators.html
- PostgreSQL TLS : https://www.postgresql.org/docs/18/ssl-tcp.html
- Vault PostgreSQL : https://developer.hashicorp.com/vault/docs/secrets/databases/postgresql
