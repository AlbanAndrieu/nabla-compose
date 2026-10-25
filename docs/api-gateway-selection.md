# API gateway open source — décision d'architecture et POC

**ADR associé :** [ADR-0001](adr/0001-apisix-api-gateway-poc.md) (accepted pour POC staging). [Méthode de dispatch](architecture-governance.md).

**Propriétaire :** `nabla-compose`. **Date :** 25/10/2026. **Statut :**
POC staging approuvé, **non déployé**, aucune modification d'ingress/TLS.
Traefik demeure l'entrée actuelle et la source autoritaire des routes.
Ce document remplace les comparaisons dispersées : il ne remplace pas
[le plan Cloudflare Access](private-homelab-access-architecture.md), ni
[la roadmap](roadmap.md), ni [le runbook](runbooks/homelab-e2e-diagnostics.md).

## Critères de sélection (POC avant production)

| Candidat | OIDC/Keycloak OSS | Observabilité | Coût opérationnel | Décision |
| --- | --- | --- | --- | --- |
| **Apache APISIX** | plugin `openid-connect` OSS, JWT, key-auth, rate limits, OPA | Prometheus, request-id, OpenTelemetry | nouveau proxy, configuration YAML; etcd facultatif en standalone | **POC P1 retenu** |
| Traefik OSS + oauth2-proxy | via `ForwardAuth`/middleware indépendant ; dépend de l'IdP | métriques/logs existants | plus simple car Traefik déjà présent | **P0 conserver l'existant** |
| Envoy Gateway | SecurityPolicy OIDC/JWT ; Gateway API K8s | OTel/Prometheus | pertinent sur Talos, moins naturel pour TrueNAS Compose | évaluer après POC Talos |
| Kong Gateway OSS | JWT/key-auth ; plugin OIDC officiel **Enterprise only** | nombreux plugins | licence OIDC à vérifier | non prioritaire |

Références :
- https://apisix.apache.org/docs/apisix/installation-guide/
- https://apisix.apache.org/docs/apisix/deployment-modes/
- https://apisix.apache.org/docs/apisix/plugins/openid-connect/
- https://apisix.apache.org/docs/apisix/plugins/prometheus/
- https://apisix.apache.org/plugins/
- https://gateway.envoyproxy.io/docs/tasks/security/oidc/
- https://developer.konghq.com/plugins/openid-connect/

APISIX `standalone file-driven` charge `conf/apisix.yaml` et **n'a pas
besoin d'etcd** ; c'est préférable au démarrage pour ce homelab.

**Conditions de sécurité OIDC obligatoires avant POC :**
en standalone, le plugin `openid-connect` exige un `session.secret`
persistant (hors Git, matériel chiffré via secret runtime) pour le flux
avec session. Définir un `redirect_uri` absolu HTTPS sur le hostname
de staging, afin qu'un `Host`/`Forwarded` falsifié ne puisse pas modifier
la destination OIDC. Vérifier `SameSite`, cookies `Secure`/`HttpOnly`,
TLS amont, validation des audiences et du rôle par FastAPI. Ne jamais
copier les exemples documentaires `ssl_verify: false` en déploiement.
Le fichier YAML doit être validé et chargé sans logging de secrets.
Référence : https://apisix.apache.org/docs/apisix/plugins/openid-connect/
 Tester en
lecture seule et sur **un hostname interne dédié** avec configuration
déclarative versionnée et ports d'administration non publiés.

## Architecture cible, séquencement sans saut de sécurité

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

La vérification d'identité doit toujours être faite à l'application de
destination. APISIX, Traefik et Cloudflare ne peuvent pas transformer un
header `X-Forwarded-For` non fiable en permission OWNER.
Cloudflare Access JWT : signature JWKS, `iss`, `aud`, `exp`, `sub`,
role/acteur autorisé ; Keycloak ultérieur via OIDC, sans dépendance de
disponibilité critique dans la première phase. Aucun cookie ni Service Token
machine exposé dans le bundle Site.

## POC P1 — contrat de sécurité et rollback

1. Déployer APISIX sur un réseau Docker **interne**, sans port public et sans
   Admin API ouverte ; mode standalone YAML, version d'image **épinglée par digest**.
2. Créer une seule route de **staging lecture seule**, sous un hostname
   `api-gateway.int.albandrieu.com` uniquement si pfSense/Traefik DNS le permet.
3. Garder Traefik → APISIX → FastAPI. Ne pas modifier `sample.albandrieu.com`
   ni `www.albanandrieu.com`.
4. Tester 200 autorisé, 401 JWT absent/invalide, 403 rôle non autorisé,
   429 quota, 502 origine indisponible et timeout. Sans Keycloak, utiliser
   provisoirement un IdP de test et une clé machine **de staging**, jamais
   une clé en clair dans Git.
5. Vérifier DNS, TLS, non-divulgation des headers secrets, propagation du
   `traceparent` de façon bornée et métriques Prometheus sans identifiants.
6. Simuler un échec APISIX ; ne pas perdre la route Traefik de production.
7. N'accepter le cutover que sur un exact HEAD testé, après backup et plan
   de rollback : retirer la route POC, laisser Traefik et FastAPI existants.

**Dépendances à résoudre avant exposition :** catalogue des routes
PUBLIC/SERVICE/OWNER/INTERNAL dans FastAPI ; configuration Cloudflare Access
`ops.albandrieu.com` ; identité workload; politiques de cache et redaction.

## Frontière inter-dépôts

- **Compose** : ingress, secrets, DNS, gateway POC, version/réseau, rollback.
- **FastAPI** : preuves de transport/provider, auth côté origine, réponse
  RFC 9457 filtrée, journal d'erreurs et identifiant de corrélation.
- **Site** : affichage conditionnel, caches SERVICE non sensibles, diagnostic
  OWNER sans adresses privées dans le public.
- **Keycloak** : futur IdP OSS ; ne remplace ni contrôle d'accès applicatif ni
  mTLS workload/service tokens.

**Critère Done POC :** toutes les assertions de sécurité passent en négatif
et positif sur staging, aucune route privée accessible par contournement
d'APISIX ou modification de header, métriques présentes, rollback validé.

## Première stack autonome prête (pas de déploiement effectué)

[Compose opt-in](../apps/apisix/compose.yml) et
[procédure opérateur](../apps/apisix/README.md) : APISIX `3.19.0-debian`
file-driven `apisix.yaml` avec `#END`, mode `data_plane` sans etcd,
mock Python local, réseau Docker interne sans port publié, seul
`GET /health` protégé par `key-auth`, quota 30/min.
`just apisix-contract` vérifie le contrat sans Docker.
`just apisix-up/smoke/down` demandent une action explicite.
Avant production, signer/résoudre le digest, ajouter gateway↔FastAPI et OIDC.
