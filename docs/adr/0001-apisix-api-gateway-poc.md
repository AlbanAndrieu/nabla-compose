# ADR-0001 — Évaluer Apache APISIX sans remplacer Traefik

- **Statut :** proposed (POC seulement ; pas de déploiement)
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

1. Traefik OSS + middleware/ForwardAuth (coût opérationnel minimal).
2. Apache APISIX OSS avec plugins OIDC/JWT/quotas/OTel.
3. Envoy Gateway sur Talos (naturel sur Kubernetes).
4. Kong OSS (OIDC officiel commercial pour certains usages).

Détails et liens de vérification : [comparatif](../api-gateway-selection.md).

## Décision proposée

**Conserver Traefik en production**, et autoriser uniquement une
**étude POC APISIX standalone file-driven** dans un réseau privé de staging.
Pas d'etcd pour le POC. Ne pas publier la console Admin API, les secrets,
les routes de gestion ni les métriques. Ne pas créer de route hors du réseau
privé avant le test de refus. Épingler l'image par digest après revue.
OIDC Keycloak est une cible future ; ne pas attendre son installation pour
fermer les endpoints FastAPI existants. Pour le mode file-driven, garder
`session.secret` persistant hors Git, configurer un `redirect_uri` absolu
en HTTPS et rejeter un `Host`/`Forwarded` falsifié.

Ne pas confondre **choix d'évaluation** et **ADR accepté de migration**.

## Conséquences

Positives : politiques d'authentification/quotas réutilisables,
observation normalisée, contrat de routage documenté.
Négatives : nouveau dataplane, doublons Traefik/APISIX, coût de mise à jour,
risques de mauvaise confiance des en-têtes et de disponibilité. Chaque route
doit garder la validation d'identité **dans FastAPI**.

## Critères de sortie et rollback

Test 200/401/403/429/502/timeout, refus d'une origine directe non
autorisée, preuves prometheus/trace expurgées, sécurité OIDC, gestion
de secret sans Git, exact-SHA et récupération après arrêt APISIX.
Rollback : retirer seulement le hostname de test, ne pas modifier
le flux de production. Une migration réelle nécessitera **un nouvel ADR**
et une PR d'implémentation séparée, avec décision explicite.
