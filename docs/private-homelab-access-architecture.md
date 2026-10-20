# Cloudflare Access / Tunnel — observabilité homelab privée

Statut : **design et ordre d'exécution, non déployé** (18 octobre 2026).
Épopée Compose : [#262](https://github.com/AlbanAndrieu/nabla-compose/issues/262).
Contrats transverses : [FastAPI #352](https://github.com/AlbanAndrieu/fastapi-sample/issues/352),
[Site Alban #233](https://github.com/AlbanAndrieu/nabla-site-alban/issues/233).

## Choix

Le site Vercel `albanandrieu.com` reste une vitrine **anonyme et assainie**.
**Hostname cible confirmé : `ops.albandrieu.com` (non provisionné)** :
navigateur propriétaire → Cloudflare Access (policy default deny, identité unique)
→ Cloudflare Tunnel → origine FastAPI TrueNAS sur réseau privé → autorisation JWT
vérifiée côté FastAPI → observabilité read-only.

Éviter de placer une route `/fr/truenas/private` derrière le même domaine public :
protection de path sensible au mauvais routage, chevauchements des règles et
doubles origines Vercel/Tunnel; la documentation Cloudflare prévoit les paths mais
l'approche par hostname unique isole mieux le risque et laisse Vercel indépendant.
Le tunnel assure un **transport**, non une autorisation à lui seul.

## Keycloak : décision différée

`apps/keycloak/compose.yml` et son README existent déjà avec statut `planned`,
PostgreSQL partagé, une interface de management non destinée à l'extérieur. Le
Compose est une **préparation**, pas une preuve d'installation/health en production.
Lorsque la base, les secrets et les sauvegardes sont prêts, Keycloak peut jouer
le rôle d'IdP OIDC pour Cloudflare Access (Generic OIDC), ou délivrer une
authentification directe dans une autre architecture à étudier. Ne pas maintenir
deux sessions d'authentification propriétaires concurrentes sans raison.

Les endpoints d'administration, `/metrics` et `/health` management de Keycloak
ne sont **jamais** routés par Tunnel/HAProxy/Traefik publics. L'issuer OIDC et
les redirect URIs doivent rester cohérents avec le domaine externe.

## Roadmap d'exécution

- [ ] **P0 ownership et inventaire** : consulter configuration DNS Cloudflare,
      règles Tunnel, Access policy, pfSense NAT/WAN/HAProxy et Traefik; rechercher
      anciens alias et endpoints directs exposés; plan de rollback documenté.
      Aucun audit sur papier ne certifie l'état live.
- [ ] **P0 modèle d'accès** : propriétaire humain unique et compte break-glass,
      politique deny-by-default, audience Access unique au hostname `ops`,
      identité exacte (pas *email domain allow*), sessions courtes, révocation.
      **MFA vérifié** : GitHub IdP peut être utilisé d'abord avec MFA GitHub;
      tester Cloudflare independent MFA/WebAuthn et les contraintes du plan
      effectivement actif; ne pas présumer que l'IdP GitHub fournit un claim
      attestant l'usage de la YubiKey.
- [ ] **P0 origine inaccessible directement** : suppression des routes publiques
      alternatives et exposition WAN de l'API privée, origin bound private-LAN,
      filtrage réseaux proxy/Traefik, demande directe origine refusée. Conserver
      l'accès LAN de secours documenté et autorisé seulement.
- [ ] **P1 IaC** : importer les ressources existantes avant `apply`, projet
      Terraform/OpenTofu pour application Access + policy + Tunnel hostname/ingress
      et DNS; `plan` dry-run redacté, séparer jeton Cloudflare API de Service Token,
      permissions minimales, secret stocké hors Git dans Vaultwarden/Vault.
- [ ] **P1 publication** : activer la policy Access et vérifier l'interdiction
      anonyme **avant** de rendre opérationnel le tunnel privé; route explicite
      vers FastAPI, catch-all 404; ne pas publier de route directe Prometheus,
      pfSense, TrueNAS, Docker socket, Keycloak management ou /metrics.
      Vérification TLS vers origine (`noTLSVerify=false`).
- [ ] **P1 validation JWT origine** : ne pas se contenter du 302/403 Cloudflare.
      Simuler absence JWT, header forgé, mauvais aud/issuer/sub, expiration,
      serveur indisponible; le seul acteur autorisé peut voir une réponse riche.
      Tester l'accès direct LAN/WAN de l'origine et le DNS/hostname fallback.
- [ ] **P1 telemetry** : collecteurs Prometheus/Loki, service discovery, journaux
      Access et probes internes restent sur chemins privés. Deux moniteurs :
      transport/Access public **et** origin API authentifiée; distinguer refus
      anonyme normal de panne effective et éviter boucles d'appels.
- [ ] **P1 sûreté opérationnelle** : sauvegarde des configs, contrôle des droits
      du secret, configuration statique et contract tests, seuil rate-limit,
      limites d'egress, politique `no-store` et `noindex`, rollback automatique
      uniquement sur signal fiable; pas d'exposition d'identité dans les logs.
- [ ] **P2 durcissement** : Cloudflare WARP/device posture sur devices approuvés
      si disponible, audit drift de policies, session reuse et logout/revocation,
      réconciliation des URLs publiques assainies avec le catalogue canonique.
- [ ] **P3 Keycloak** : suivre `apps/keycloak/README.md`; bootstrap one-shot,
      DB/key management/snapshots testés, TLS strict/issuer OIDC, authentification
      multi-facteur avec clés matérielles, admin privé, journaux d'audit, disaster
      recovery. Prouver la bascule et le retour arrière avant de changer l'IdP.

## Matrice de recette minimale

| Acteur / état | Public site | `ops` | Accès direct API riche |
| --- | --- | --- | --- |
| Anonyme | Site public assaini | Login Access / 403 | 401/403 |
| Autre compte authentifié | Site public assaini | 403 | 401/403 |
| Propriétaire avec MFA | Site public assaini | 200 read-only | Refus sans JWT/autorisation |
| Service token limité | Pas de secret dans browser | Pas de session humaine | Endpoint machine dédié seulement |
| Access/Tunnel down | Site public reste disponible | Indisponible, fail-closed | 401/403 |
| Origine FastAPI down | Site public neutre | Service indisponible | Aucun fallback riche |

## Critères de clôture

IaC plan et diff examinés, politique en vigueur vérifiée dans le compte réel,
preuve négative anonyme/autre identité, preuve positive propriétaire, schéma
public sans détails, absence de route alternative, logs/retention, secret
rotation et sauvegarde/rollback **réellement** testés. Ne pas merger automatiquement.

Sources : https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/ ;
https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/github/ ;
https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/generic-oidc/ ;
https://www.keycloak.org/server/reverseproxy ;
https://vercel.com/kb/guide/cloudflare-with-vercel .

## Contrat du hostname `ops.albandrieu.com` — décision du 18 octobre 2026

**FQDN figé** : `ops.albandrieu.com` est la destination des diagnostics privés.
Le nom est **réservé par convention GitOps**, pas créé dans DNS et pas attesté
comme opérationnel. Le site `www.albanandrieu.com` et `albanandrieu.com`
ne redirigent aucune route API privée vers cette origine.

- **Owner DNS/Access/Tunnel** : `nabla-compose`. Route `ops.albandrieu.com/*`
  couverte par **une application self-hosted Cloudflare Access pour le hostname
  entier**, et non un simple path `/private/*`.
- **Owner runtime** : `fastapi-sample` sur TrueNAS, idéalement via vhost/ingress
  `ops` dédié en **lecture seule**, isolé des routes de staging/public.
  Aucune ouverture de port WAN; listener de gestion inaccessible depuis Internet
  et une route Tunnel explicitement limitée à l'origine opérateur.
- **Owner vitrine** : `nabla-site-alban`; aucun appel public vers les routes riches
  de FastAPI, pas de proxy Next.js faisant transiter les tokens Cloudflare.
- **Sécurité des sessions** : Access est la frontière de pré-authentification;
  FastAPI revalide le JWT signé avec audience spécifique, `iss`, `exp`, `nbf`
  et **identité allowlist**. Même via Tunnel, aucun header utilisateur seul
  (`Cf-Access-Authenticated-User-Email`) ne constitue une authentification.
- **Séparation des identités** : l'utilisateur humain n'obtient jamais de
  `Service Token`; les sondes et robots n'utilisent pas les cookies de session
  humaine. Aucun jeton machine dans les pages, bundles JS ou URL.
- **MFA** : l'intégration GitHub peut identifier l'utilisateur, mais sa seule
  utilisation ne prouve **pas** à Access que la YubiKey a été présentée pour
  cette session. La contrainte `Require > Authentication method` fondée sur
  les méthodes de l'IdP ne couvre pas l'IdP GitHub dans la documentation 2026.
  Pour une exigence matérielle vérifiable, évaluer **Access Independent MFA**
  et ses disponibilités réelles, ou Keycloak en **Generic OIDC** avec
  propagation attestée des méthodes d'authentification.
- **Métriques** : Prometheus et ses endpoints `/metrics` restent sur le
  réseau interne. L'UI `ops` présente des agrégats paginés et bornés, pas
  un proxy libre vers PromQL/Grafana/TrueNAS/pfSense.
- **Politique navigateur** : `noindex` et `no-store` à titre de défense
  complémentaire seulement; les protections requises sont Access + JWT origine
  + réseau interne et routes explicitement autorisées.

### Terraform / OpenTofu : préparation GitOps, sans `apply`

Privilégier le provider Cloudflare **v5** avec versions épinglées et
`terraform.lock.hcl`; les ressources documentées incluent
`cloudflare_zero_trust_access_application`,
`cloudflare_zero_trust_access_policy` et
`cloudflare_zero_trust_tunnel_cloudflared_config`. Leur schéma dépend
de la version exacte : exécuter `terraform validate` et `plan` avant de
commiter une configuration concrète.

1. **Discovery/import-first** : déterminer si un tunnel existe et est géré
   ailleurs; inventaire read-only de la zone, DNS, Access, tunnels,
   configurations Cloudflared, règles pfSense et HAProxy. Ne pas écraser la
   configuration du tunnel partagé (un seul propriétaire de l'Ingress).
2. **Isolation** : préférer un tunnel/connector **dédié** à `ops` pour
   limiter le blast radius si l'inventaire le permet; sinon import et revue
   explicite du tunnel partagé avec ordre de routes, catch-all 404 et
   permissions de l'origine. Ne jamais créer un second contrôleur IaC
   concurrent pour la même configuration.
3. **Credentials** : Cloudflare API token minimal pour gestion IaC,
   stocké hors du Git/PR et distinct des Service Tokens d'appels machine.
   Identité allowlist injectée via configuration protégée, pas codée dans
   le dépôt; state Terraform chiffré et avec contrôles d'accès restreints.
4. **Déclaration** : app Access self-hosted `ops.albandrieu.com`,
   policy sans `bypass`, session courte, règles inclure identité exacte et
   contrôles MFA supportés ; DNS proxied CNAME tunnel, Ingress `ops` vers
   l'origine privée TLS vérifiée, `http_status:404` par défaut.
5. **Revue du plan** : diff IaC sans secret, absence de route `/metrics`
   ou admin directe, absence d'effet sur les autres hostnames, règles de
   journalisation/redaction. Ne pas appliquer tant que FastAPI n'est pas
   fermé à l'origine et que le site public n'est pas assaini.
6. **Activation dans l'ordre** : durcir l'API/FastAPI → politique Access
   et tests anonymes → config Tunnel/ingress → DNS seulement après contrôle
   de la policy → E2E depuis Internet et LAN → supervision/rollback.
7. **Rollback** : fermer la route `ops`/DNS **sans** désactiver l'authentification
   d'origine, restaurer le précédent manifeste Tunnel et sa configuration
   Access; ne pas casser les autres services du tunnel existant.

### Gates de publication

| Gate | Propriétaire | Preuve attendue | État initial |
| --- | --- | --- | --- |
| G0 | Site Alban | Scan FR/EN et JSON public sans IP/ports/topologie riche | NOT_RUN |
| G1 | FastAPI | Tests JWT, origine inaccessible autrement, DTO public allowlist | NOT_RUN |
| G2 | Compose | Inventory réel Tunnel/DNS/Access/NAT et IaC import-first | NOT_RUN |
| G3 | Compose | Policy Access deny-by-default et MFA prouvée pour le propriétaire | NOT_RUN |
| G4 | Compose + FastAPI | Tunnel privé, aucun bypass direct, 200 owner/403 autre | NOT_RUN |
| G5 | Tous | Échec fermé, purge caches, journaux expurgés et rollback testés | NOT_RUN |

**Règle** : aucun gate ne devient `PASS` par un simple succès CI documentaire.

### Documentation officielle 2026

- https://developers.cloudflare.com/tunnel/guides/terraform/
- https://developers.cloudflare.com/cloudflare-one/access-controls/policies/mfa-requirements/
- https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/application-token/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/zero_trust_access_application
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/zero_trust_access_policy
