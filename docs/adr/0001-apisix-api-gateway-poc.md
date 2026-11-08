# ADR-0001 — Évaluer Apache APISIX sans remplacer Traefik

- **Statut :** accepted (autorisation de réaliser le POC en staging ; aucun cutover production)
- **Approuvé le :** 2026-10-25 par le propriétaire du homelab
- **Date :** 2026-10-25
- **Propriétaire de la décision :** Compose / gouvernance plateforme
- **Implémentation :** [Compose #278](https://github.com/AlbanAndrieu/nabla-compose/pull/278)
- **Consommateurs :** [FastAPI #376](https://github.com/AlbanAndrieu/fastapi-sample/pull/376), [Site Alban #256](https://github.com/AlbanAndrieu/nabla-site-alban/pull/256)

## Contexte

Traefik distribue déjà les routes TrueNAS. Cloudflare Tunnel/Access peut
authentifier une demande d'OWNER, mais aucune gateway dédiée n'est encore
déployée. Les applications possèdent des contrôles d'accès qui ne doivent
jamais être abandonnés ou remplacés par une simple IP ou un header proxy.
Les défauts catalogue, transport, API, identité et rendu sont actuellement
insuffisamment corrélés.

## Options étudiées

| Candidat | OIDC/Keycloak OSS | Observabilité | Coût opérationnel | Décision |
| --- | --- | --- | --- | --- |
| **Apache APISIX** | plugin `openid-connect` OSS, JWT, key-auth, rate limits, OPA | Prometheus, request-id, OpenTelemetry | nouveau proxy, YAML ; etcd facultatif en standalone | **POC P1 retenu** |
| Traefik OSS + oauth2-proxy | `ForwardAuth`/middleware indépendant ; dépend de l'IdP | métriques/logs existants | plus simple, Traefik déjà présent | **P0 conserver l'existant** |
| Envoy Gateway | SecurityPolicy OIDC/JWT ; Gateway API K8s | OTel/Prometheus | pertinent sur Talos, moins naturel pour TrueNAS Compose | évaluer après POC Talos |
| Kong Gateway OSS | JWT/key-auth ; plugin OIDC officiel **Enterprise only** | nombreux plugins | licence OIDC à vérifier | non prioritaire |

APISIX `standalone file-driven` charge `conf/apisix.yaml` et **n'a pas besoin
d'etcd**. Références :
[installation](https://apisix.apache.org/docs/apisix/installation-guide/),
[modes de déploiement](https://apisix.apache.org/docs/apisix/deployment-modes/),
[openid-connect](https://apisix.apache.org/docs/apisix/plugins/openid-connect/),
[prometheus](https://apisix.apache.org/docs/apisix/plugins/prometheus/),
[Envoy OIDC](https://gateway.envoyproxy.io/docs/tasks/security/oidc/),
[Kong OIDC](https://developer.konghq.com/plugins/openid-connect/).

## Architecture cible

```text
Visiteur PUBLIC ─> Cloudflare/WAF ─> Vercel Site ─> DTO SERVICE expurgé
                                                | server-to-server, clé machine
OWNER distant ─> Cloudflare Access JWT vérifié ─┼─> FastAPI OWNER policy
OWNER LAN ─────> source réseau vérifiée + identité┘
Observateurs ──> FastAPI (preuves DNS/TCP/TLS/TrueNAS/Cloudflare)
                                   |
                     APISIX POC (optionnel) ─> FastAPI staging
                                   |
                  Traefik garde le routage/TLS existant
```

L'identité est toujours vérifiée par l'application de destination : APISIX,
Traefik et Cloudflare ne transforment pas un `X-Forwarded-For` non fiable en
permission OWNER. Cloudflare Access JWT : signature JWKS, `iss`, `aud`, `exp`,
`sub`, rôle autorisé. Aucun cookie ni Service Token machine dans le bundle
Site.

Frontière inter-dépôts :

- **Compose** : ingress, secrets, DNS, gateway POC, version/réseau, rollback.
- **FastAPI** : preuves transport/provider, auth côté origine, réponse
  RFC 9457 filtrée, journal d'erreurs et identifiant de corrélation.
- **Site** : affichage conditionnel, caches SERVICE non sensibles, diagnostic
  OWNER sans adresses privées dans le public.
- **Keycloak** : futur IdP OSS ; ne remplace ni le contrôle d'accès applicatif
  ni mTLS workload/service tokens.

## Décision acceptée

**Conserver Traefik en production**, et autoriser uniquement une
**implémentation et validation d'un POC APISIX standalone file-driven** dans un réseau privé de staging.
Pas d'etcd pour le POC. Ne pas publier la console Admin API, les secrets,
les routes de gestion ni les métriques. Ne pas créer de route hors du réseau
privé avant le test de refus. Épingler l'image par digest après revue.
OIDC Keycloak est une cible future ; ne pas attendre son installation pour
fermer les endpoints FastAPI existants. Pour le mode file-driven, garder
`session.secret` persistant hors Git, configurer un `redirect_uri` absolu
en HTTPS et rejeter un `Host`/`Forwarded` falsifié.

Cette acceptation couvre le POC, sa configuration, ses tests et son rollback.
L'agent peut agir directement sur staging sans nouvelle demande d'approbation,
à condition de documenter les preuves. Elle ne constitue **pas** une décision
de remplacer Traefik en production.

## Conséquences

Positives : politiques d'authentification/quotas réutilisables,
observation normalisée, contrat de routage documenté.
Négatives : nouveau dataplane, doublons Traefik/APISIX, coût de mise à jour,
risques de mauvaise confiance des en-têtes et de disponibilité. Chaque route
doit garder la validation d'identité **dans FastAPI**.

## Contrat de sécurité du POC P1

1. APISIX sur un réseau Docker **interne**, sans port public ni Admin API
   ouverte ; mode standalone YAML, image **épinglée par digest**.
2. Une seule route de **staging lecture seule**, sous
   `api-gateway.int.albandrieu.com` si le DNS pfSense/Traefik le permet.
3. Traefik → APISIX → FastAPI ; ne pas modifier `sample.albandrieu.com` ni
   `www.albanandrieu.com`.
4. OIDC : `session.secret` persistant hors Git (secret runtime),
   `redirect_uri` absolu HTTPS sur le hostname de staging, cookies
   `Secure`/`HttpOnly`/`SameSite`, TLS amont vérifié (jamais
   `ssl_verify: false`), audiences et rôle validés par FastAPI. Sans Keycloak,
   IdP de test et clé machine **de staging**, jamais en clair dans Git.
5. Vérifier DNS, TLS, non-divulgation des headers secrets, propagation bornée
   du `traceparent`, métriques Prometheus sans identifiants.

Dépendances avant toute exposition : catalogue des routes
PUBLIC/SERVICE/OWNER/INTERNAL dans FastAPI, Cloudflare Access
`ops.albandrieu.com`, identité workload, politiques de cache et redaction.

Stack prête, non déployée : [Compose opt-in](../../apps/apisix/compose.yml) et
[procédure opérateur](../../apps/apisix/README.md) (APISIX file-driven
`apisix.yaml` avec `#END`, `data_plane` sans etcd, mock Python local, réseau
interne sans port publié, seul `GET /health` protégé par `key-auth`, quota
30/min). `just apisix-contract` vérifie le contrat sans Docker ;
`just apisix-up/check/smoke/down` demandent une action explicite.

## Critères de sortie et rollback

Test 200/401/403/429/502/timeout, refus d'une origine directe non
autorisée, preuves prometheus/trace expurgées, sécurité OIDC, gestion
de secret sans Git, exact-SHA et récupération après arrêt APISIX.
Rollback : retirer seulement le hostname de test, ne pas modifier
le flux de production. Une migration réelle nécessitera **une nouvelle décision** tracée par
amendement ADR ou ADR successeur et une PR distincte ; l'agent peut proposer
ce cutover après preuve des critères, sans le réaliser silencieusement.
