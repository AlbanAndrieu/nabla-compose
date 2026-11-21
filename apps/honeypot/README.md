# Honeypot TrueNAS : Cloudflare Tunnel → Traefik → CrowdSec (staged)

**Dernier contrôle propriétaire, 21/11/2026 :** `GET
http://172.17.0.24:31090/healthz` retourne `ok` ;
`login.albandrieu.com` ne résout plus après suppression volontaire du
record A vers l'ancienne IP WAN `82.66.4.247`. L'App est **déployée
en LAN**, mais **pas publiée sur Internet** au moment de ce constat.

## Architecture et frontières

```text
Internet HTTPS login.albandrieu.com
  └─ Cloudflare DNS (CNAME proxifié requis, NOT_VERIFIED)
     └─ Access "honeypot-login": Everyone bypass (IaC ; live NOT_VERIFIED)
        └─ Cloudflare Tunnel "homelab" / cloudflared
           ├─ DÉFAUT : http://172.17.0.24:31090
           │      └─ Apache/PHP Project Honey Pot (/, /healthz, /login)
           └─ OPT-IN : https://traefik:443
                  ├─ SNI traefik.int.albandrieu.com (TLS vérifié)
                  ├─ HTTP Host login.albandrieu.com
                  ├─ peer-only 10.200.2.0/24 (pas de WAN direct)
                  ├─ CrowdSec LAPI streaming + AppSec WAF
                  ├─ limite de débit (GET 10/s, POST /login 2/s)
                  └─ honeypot:8080 via traefik_network
```

Ce tunnel **n'utilise pas** un port WAN ouvert par NAT. Le flag
`honeypot_tunnel_via_traefik` vaut **false** par défaut
(`terraform/cloudflare/variables.tofu`) : même un `tofu apply`
non spécifique ne peut pas activer Traefik involontairement.
Une seule route publique reste déclarée dans le Tunnel.
La configuration complète du Tunnel est partagée ; **ne jamais appliquer
un plan qui supprime/modifie des routes sans revue**.

### Pages

| Méthode | Chemin | Réponse et impact |
| --- | --- | --- |
| GET / HEAD | `/healthz` | 200 statique, **aucun événement Project Honey Pot** |
| GET | `/` | script Project Honey Pot original, chaque GET signale une visite |
| GET | `/honeypot/keywaspish.php` | script d'origine, réservé au diagnostic ; éviter les probes |
| GET | `/login` | formulaire de **simulation** statique, sans `name` sur les champs |
| POST | `/login` | 403 Apache (pas de PHP, body max 1 KiB, sans authentification) |
| Autres | `/wp-login.php`, etc. | 404 ; aucun fallback vers un vrai login |

La page `/login` a une mention visible de simulation : **ne jamais
collecter d'identifiants réels**. Les champs n'ont pas de `name` ;
un navigateur soumet un corps vide. Les POST forgés par des robots
rencontrent le 403 Apache et ne sont ni journalisés dans le corps
ni transmis au script PHP. Les logs Apache enregistrent seulement
IP, date, méthode, chemin **sans query string** et statut.
Depuis la révision 21/11, Apache exclut aussi les requêtes exactes
`/healthz` de son **access log** via `SetEnvIf` ; Docker/Gatus conservent
leur résultat HTTP 200. Les 30-secondes de sondes qui remplissaient
le journal avec `127.0.0.1` ne sont donc plus comptées comme visites
après redéploiement. Les logs déjà produits restent inchangés.

## Plan de publication progressif, pas exécuté

### Étape 1 — DNS et Tunnel direct (conserver le rollback)

La suppression du record A historique est déjà effectuée par
l'opérateur. Le code possède la publication proxifiée attendue sous
`terraform/cloudflare/dns-policy.yaml:new_tunnel_hostnames` :

```text
login.albandrieu.com CNAME
  1d98bede-6fa0-42a8-971c-cd390d74d7f6.cfargotunnel.com
Proxied: true
```

**Depuis la workstation autorisée**, récupérer d'abord l'état Garage
et réconcilier les imports/CNAME existants :

```bash
cd /mnt/cpool/compose/nabla-compose
python3 scripts/cloudflare/capture-dns-records.py --help
scripts/infra/terragrunt-safe.sh infrastructure/cloudflare plan
# inspecter CNAME "login" ajouté, Access "honeypot-login",
# aucune suppression ou mutation involontaire des autres routes
# appliquer via la procédure approuvée terraform/cloudflare/README.md
```

**Ne pas appliquer** depuis la CI, ne pas forcer un create si le CNAME
est déjà présent : le plan import-first doit reconciler DNS, Tunnel,
Access et les autres objets du state. `dig @1.1.1.1 login.albandrieu.com
A +short` peut retourner des IP Cloudflare après la publication,
mais la présence du DNS ne prouve pas l'origine.

Contrôles depuis une vraie connexion externe :

```bash
dig @1.1.1.1 login.albandrieu.com CNAME +short
curl -sS -o /dev/null -w '%{http_code}\n' \
  https://login.albandrieu.com/healthz
# 200 attendu, sans toucher / qui déclenche un hit Project Honey Pot
```

### Étape 2 — redéploiement contrôlé de l'App honeypot

`apps/honeypot/compose.yml` ajoute `traefik_network` en plus du
réseau propre à l'App. Avant déploiement, vérifier :

```bash
sudo docker network inspect traefik_network \
  --format '{{json .IPAM.Config}}'
sudo docker network inspect ix-cloudflared_default \
  --format '{{json .IPAM.Config}}'
sudo docker inspect traefik --format '{{json .NetworkSettings.Networks}}'
sudo docker inspect honeypot --format '{{json .NetworkSettings.Networks}}'
sudo docker compose -f apps/honeypot/compose.yml config --quiet
sudo bash scripts/truenas/diagnose-crowdsec-appsec.sh --runtime
```

**Attention :** les réseaux versionnés connus sont
`traefik_network=172.16.56.0/24` et
`ix-cloudflared_default=10.200.2.0/24`. Si l'appliance ne confirme
plus exactement ces CIDR, **NO-GO** et revoir les plages de confiance.
Apache ne fait pas d'authentification avec l'IP reportée par PHP :
les décisions CrowdSec s'appuient sur les **journaux Traefik** validés
avec le peer réel `cloudflared`.

Après contrôle de l'état et sauvegarde, redéployer la seule App
`honeypot` avec le mécanisme TrueNAS existant et vérifier les trois
chemins LAN : `/healthz` 200, `/login` 200, POST `/login` 403.
Les deux routeurs Traefik publics sont déclarés, mais **aucun trafic
Internet ne les emprunte tant que le switch Tunnel reste false**.

### Étape 3 — recette canary Traefik/CrowdSec

Le middleware `honeypot-tunnel-peer` limite le router à la vraie IP
du conteneur cloudflared sur `10.200.2.0/24`. Une sonde directe depuis
une workstation LAN doit être **403**, même avec des en-têtes falsifiés.
Pour la recette positive, utiliser **uniquement un conteneur de test
approuvé** relié à `ix-cloudflared_default`, ou le chemin Tunnel
après publication. Tester TLS vérifié avec :

```bash
# À exécuter DANS un client de test sur ix-cloudflared_default
curl --fail-with-body \
  --connect-to traefik.int.albandrieu.com:443:traefik:443 \
  -H 'Host: login.albandrieu.com' \
  https://traefik.int.albandrieu.com/healthz
```

Prévoir l'accès DNS/certificat dans le client ; un échec de
validation TLS/SNI est un **NO-GO**, ne jamais le contourner
par `-k` pour déclarer la recette validée. Surveiller les logs
`traefik`, `cscli metrics show appsec`, erreurs 403/429 et
`traefik_dashboard`. Le dernier préflight fourni rapporte
collections installées et métriques disponibles, mais **aucun 403
canary ni portail admin prouvé**. Le test spécifique FastAPI reste
requis avant d'affirmer la protection générale AppSec.

### Étape 4 — bascule optionnelle puis rollback

Après preuves, définir `-var='honeypot_tunnel_via_traefik=true'`
dans le **plan contrôlé** de l'unité Cloudflare et vérifier les
modifications du seul champ `service/origin_request` de
`login.albandrieu.com`. Utiliser le plan approuvé.
Le rollback est `honeypot_tunnel_via_traefik=false` et un nouveau
plan/apply revu. Maintenir le port :31090 et l'App durant la transition.

## CrowdSec : visiteurs, scénarios et fausses détections

**Aujourd'hui**, `crowdsec-appsec@file` sur les routeurs
`honeypot-public` et `honeypot-login-attempt` peut appliquer les
règles WAF installées et les décisions LAPI existantes **après
activation du Tunnel**. Une visite GET ou un POST isolé ne prouve
pas qu'un individu est malveillant et **ne justifie pas une IP ban**.

Un scenario de leaky bucket **préparé mais NON monté** dans
`apps/crowdsec/scenarios/nabla/honeypot-login-burst.yaml` détecterait
les POST répétées `/login` depuis le routeur exact et par IP source.
Avant de le charger, vérifier que CrowdSec est en **simulation** via
`cscli simulation status`, puis analyser les faux positifs,
`cscli explain` sur logs contrôlés, et les alertes/whitelists.
Le brancher seulement lors d'un futur apply explicitement approuvé ;
ne pas ajouter de mount de scénario avec remediation active
sans simulation. Une fois qualifié, l'action préférée est challenge
gradué ou ban court sur attaques répétées, avec procédure d'unban.

### Où consulter les visiteurs ?

```bash
# Journal riche, PRIVÉ, sur TrueNAS (ne pas le publier, contient des IP)
sudo grep -F 'honeypot-' /mnt/cpool/traefik/logs/access.log | tail -n 30
sudo docker exec crowdsec cscli metrics show acquisition
sudo docker exec crowdsec cscli alerts list -a
sudo docker exec crowdsec cscli decisions list

# Rapport CTEM agrégé sans IP, query string, corps, JWT ou URL arbitraire
python3 scripts/security/summarize-honeypot-traefik.py --check
sudo python3 scripts/security/summarize-honeypot-traefik.py --summarize
```

Un système de sécurité permet d'identifier des **adresses réseau et des
tentatives**, pas l'identité civile des personnes. L'IP peut être celle
d'un VPN, d'un réseau partagé, d'un relais ou d'un robot.
Ne pas exporter les logs bruts vers le site public, Homarr ou GitHub.
Les journaux Apache sont tournants (10 MiB × 3) dans le Docker
json log de l'App ; vérifier séparément la rotation des access logs
fichier Traefik. Documenter la durée de conservation, la finalité
sécurité et les accès limités (RGPD).

## www.albanandrieu.com — intégration prévue

Le dépôt `nabla-site-alban` possède **déjà** une page React
`app/[locale]/login/LoginClient.tsx` (demo Turnstile, mot de passe
dummy readonly, formulaire POST `/handler`). Ne pas créer une seconde
page de connexion ni mettre le vrai login du site derrière le piège.

Pour transmettre un **signal de test**, il est possible d'ajouter
sur cette page de démonstration une navigation explicite vers
`https://login.albandrieu.com/login` : **lien GET sans query**, pas
de POST de données, pas de cookies/JWT ni de transfert de Turnstile.
Aucune redirection HTTP 307/308, aucun proxy de credentials
Vercel → TrueNAS et aucun formulaire prenant des identifiants réels.
Un navigateur qui visite le leurre est observé uniquement si
`login.albandrieu.com` est publié, et un bannissement ne doit pas être
déclenché par cette simple navigation.
Ce chantier Vercel/Next.js reste **PLANNED** tant qu'il n'a pas son
propre contrat de test/no-credential et déploiement validé.

Références :
- https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/dns/
- https://docs.crowdsec.net/docs/appsec/quickstart/traefik/
- https://docs.crowdsec.net/docs/log_processor/scenarios/format/
- https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
