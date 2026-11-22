# Workstation ↔ TrueNAS : rapports web et honeypot (21/11/2026)

Ce runbook distingue **données déjà observées**, **code déclaré** et **réception
runtime à effectuer**. Il complète [CTEM externe](ctem-external-exposure.md)
et [ansible-workstation #39](https://github.com/AlbanAndrieu/ansible-workstation/pull/39).
Il ne donne aucune autorisation de publier des résultats de scans bruts.

## 1. Partage NFS et Apache : deux voies indépendantes

```text
TrueNAS  /mnt/cpool/www                         (dataset ZFS exporté en NFSv4.2)
             ├── nabla-site-apache/              (site historique)
             ├── nabla-site-bababou/             (site historique)
             └── reports/ctem/amass-summary.json (agrégats CTEM, opt-in)
                        │
                  NFS /media/www    (Workstation; automount systemd)
                        │
             ┌──────────┴────────────────────────────────┐
             │ liens symboliques /var/www/nabla-site-*    │
             │ publication des sites historiques Apache  │
             └──► /opt/script/publish-ctem-web-mirror.py  │
                  contrôle JSON, copie expurgée (opt-in)
                                │
                /var/www/reports/ctem (disque local)
                                │
            Apache Alias /reports, LAN seulement (code)
```

**Observations du propriétaire, 21/11/2026** :

- `findmnt -T /media/www/nabla-site-apache` et `...bababou` :
  `nabla:/mnt/cpool/www` monté `nfs4`, vers=4.2, `nosuid,nodev,noexec`,
  au-dessus de `systemd-1 autofs` ; **ni copie locale ni miroir** pour
  les sites historiques.
- `apache2ctl -S` : uniquement des VirtualHosts `*:80` et `*:8082`
  (`www.albandrieu.com`), `Main DocumentRoot: /var/www/html`,
  exécutés comme `www-data`. Aucune preuve d'un listener `8087` ni
  d'un vhost `:443` actif dans cet extrait.
- `namei -l /var/www/nabla-site-apache/public` : symlink vers
  `/media/www/nabla-site-apache` ; chemins NFS lisibles et traversables.
- `getfacl /media/www/nabla-site-apache/public` :
  `albandrieu:www-data`, `user::rwx group::rwx other::r-x`.
  Le groupe serveur `www-data` dispose de l'écriture sur ce répertoire :
  **risque d'altération du contenu servi** en cas de compromission Apache/PHP.
- Modules actifs rapportés : `php_module`, `proxy_module`,
  `proxy_http_module`, `remoteip_module`; pas de `security2_module`
  dans le filtre fourni. `AH00558` est l'avertissement de `ServerName`
  global absent, pas la preuve d'une panne Apache.

**Distinction critique :** la future copie locale *CTEM* sur
`/var/www/reports/ctem` ne transforme **pas** les répertoires des sites
historiques `/var/www/nabla-site-*` en miroirs locaux. L'Alias et le port
`8087` sont **déclarés dans ansible-workstation #39** mais ne sont pas
attestés par le dernier `apache2ctl -S` fourni. Ne pas afficher
`DEPLOYED` sans test HTTP depuis un client LAN.

### Contrôles read-only (sur workstation)

```bash
sudo apache2ctl -S
sudo apache2ctl -M | grep -E 'php|proxy|remoteip|security2' || true
sudo grep -R -n -E '^\s*(Alias /reports|Listen 8087|ServerName)' \
  /etc/apache2/conf-enabled /etc/apache2/sites-enabled /etc/apache2/ports.conf
findmnt -T /media/www/nabla-site-apache -o TARGET,SOURCE,FSTYPE,OPTIONS
findmnt -T /media/www/reports -o TARGET,SOURCE,FSTYPE,OPTIONS
namei -l /var/www/nabla-site-apache/public /var/www/reports
getfacl -p /media/www/nabla-site-apache/public
getfacl -p /var/www/reports
```

**Durcissement à planifier, pas appliqué :** monter les répertoires de sites
historiques en lecture seule pour Apache ou supprimer l'écriture du groupe
`www-data` **après** inventaire des déploiements/ACL et vérification NFS.
Conserver une identité de déploiement distincte. Séparer l'exécution PHP des
sources NFS modifiables ; désactiver `Indexes`, restreindre symlinks, limiter
les modules actifs et documenter le listener réel. Un `ServerName localhost`
global supprime AH00558 sans modifier les VirtualHosts ; ne pas confondre
ce réglage avec la publication DNS.

### CTEM : frontière de publication

| Chemin | Nature | Autorisation |
| --- | --- | --- |
| TrueNAS `/mnt/cpool/ctem/amass/reports` | rapports détaillés, FQDN et actifs | **privé**, jamais NFS/HTTP |
| TrueNAS `/mnt/cpool/www/reports/ctem` | JSON et HTML de synthèse expurgés | NFS seulement après opt-in |
| Workstation `/media/www/reports/ctem` | **même** partage NFS | entrée non fiable à revalider |
| Workstation `/var/www/reports/ctem` | miroir local régénéré depuis JSON validé | Apache LAN-only après contrôle |

Le producteur `publish-ctem-web-summary.py` (nabla-compose #436) et
le consommateur `publish-ctem-web-mirror.py` (ansible-workstation #39)
sont **séparément opt-in**. Le premier refuse les noms/IP/entités dans la
sortie ; le second reconstruit une page locale, sans recopier le HTML NFS.
Les rapports sécurité workstation existants sous `/var/www/reports/security`
sont locaux et distincts. Pas de mise à disposition publique via
Cloudflare Access sans vérification cryptographique des assertions et recette
indépendante de l'absence d'accès WAN.

## 2. Honeypot public — NFS et ingress indépendants

Le honeypot **ne lit aucun rapport** sur le partage NFS workstation.
Il est un conteneur Apache/PHP isolé sur TrueNAS, port LAN `:31090`.

**Nouveau relevé opérateur du 21/11 :** l'enregistrement A historique
`login.albandrieu.com → 82.66.4.247` a été supprimé dans Cloudflare.
`dig @1.1.1.1 login.albandrieu.com A +short` ne renvoie rien ;
`curl https://login.albandrieu.com/healthz` échoue par résolution DNS ;
`curl http://172.17.0.24:31090/healthz` renvoie `ok`.
Il manque donc une **publication CNAME/Access/Tunnel reçue**, et non
une preuve de panne de l'App.

Le nouveau [runbook canonique du honeypot](../../apps/honeypot/README.md)
prépare **sans apply** :

- `login.albandrieu.com` CNAME proxifié
  `1d98bede-6fa0-42a8-971c-cd390d74d7f6.cfargotunnel.com`
  dans le module OpenTofu déjà propriétaire du Tunnel.
- Un switch `honeypot_tunnel_via_traefik=false` initialement :
  voie directe 31090 conservée ; passage éventuel à
  `https://traefik:443` seulement après recette.
- Routeurs Traefik `honeypot-public` et
  `honeypot-login-attempt` avec source TCP `cloudflared`
  strictement autorisée, AppSec CrowdSec, quotas distincts.
- Page `/login` HTML statique **sans envoi de credentials**,
  refus Apache POST `403`, journal d'accès sans query string.
  La racine `/` reste le script Project Honey Pot, et
  `/healthz` ne déclenche pas d'alerte.
- Un scénario CrowdSec `nabla/honeypot-login-burst` **non monté**,
  à évaluer en simulation avant autorisation de bannissement.
- Une synthèse CTEM de logs Traefik
  `scripts/security/summarize-honeypot-traefik.py` sans IP,
  en complément de la consultation privée des alertes et décisions.

Il ne faut pas confondre une IP source avec l'identité d'une personne,
ni le `PASS_INSTALLED` des collections AppSec avec un blocage HTTP
réel. Le premier test 403 contrôlé et le dashboard Traefik restent
`NOT_VERIFIED` jusqu'à preuve runtime. Le site
`nabla-site-alban` possède **déjà** une démo Turnstile sous
`app/[locale]/login/LoginClient.tsx` ; sa future connexion éventuelle
au honeypot doit se limiter à un **GET explicite sans identifiants,
cookies, JWT ou redirection POST**, jamais une collecte d'identifiants
des lecteurs du site.

## 4. Garde-fous avant activation

- **Preuves CrowdSec du propriétaire (21/11)** : `--check` 11/11 ;
  port 7422 non publié ; réseau `traefik_network` joint ;
  `appsec_collections=PASS_INSTALLED` ;
  `appsec_metrics=AVAILABLE_BLOCK_BEHAVIOR_NOT_VERIFIED`.
  Le WAF n'est **pas** déclaré opérationnel : requête canary
  HTTP 403, métriques de blocage et test témoin encore requis.
- `traefik_dashboard=NOT_VERIFIED_REQUIRE_AUTH_AND_METRICS_RECEIPT` :
  vérifier route admin authentifiée, fermeture du port API `:8080`,
  cible Prometheus `:8082` et absence de fuite de secret LAPI.
- Tester `Cloudflare → Traefik → honeypot` uniquement après validation
  de l'IP publique véritable, du certificat origine (SNI) et des ACL.
  Les refus d'Access ne sont pas des succès du WAF.
- Ne bannir une IP qu'après un scénario CrowdSec indépendant et
  une fenêtre de test contrôlée (règles de whitelist/rollback) ;
  une réponse `429` Traefik ne prouve pas une décision LAPI.
- Un formulaire leurre ne doit jamais accepter d'authentification,
  provoquer de collecte de mots de passe ni permettre de redirection
  vers un vrai service sensible.

Références : [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/concepts/routing/),
[Turnstile](https://developers.cloudflare.com/cloudflare-challenges/challenge-types/turnstile/),
[AppSec CrowdSec](https://docs.crowdsec.net/docs/appsec/quickstart/traefik/).
