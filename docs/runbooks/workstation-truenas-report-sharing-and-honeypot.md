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

## 2. Honeypot `login.albandrieu.com` : pourquoi LAN OK ≠ WAN OK

**Observé côté utilisateur :** `http://172.17.0.24:31090/` répond ;
la publication `http://login.albandrieu.com/` échoue. Une requête web
automatisée externe n'a pas permis de confirmer le code HTTP réel de ce
nom : le diagnostic public reste `NOT_VERIFIED`.

**Déclaré dans Git :** `apps/honeypot/compose.yml` sert un script
**Project Honey Pot** Apache/PHP, ce n'est **pas** un service de connexion.
`/` exécute le script de collecte ; `/healthz` est statique et réservé
aux sondes ; les autres chemins, notamment `/wp-login.php`, renvoient 404.
Il n'y a **ni page /login ni CAPTCHA du formulaire** aujourd'hui.

`terraform/cloudflare/tunnel.tofu` vise directement
`http://172.17.0.24:31090` : **Traefik n'est pas traversé**.
Le record DNS historique A de `login` pointait vers l'ancien WAN
`82.66.4.247` le 21/11 ; `dns-policy.yaml` prépare un CNAME
vers le tunnel après retrait/adoption de ce A. L'Access app
`honeypot-login` est préparée avec la politique `Everyone bypass`
afin que le piège soit atteignable sans identité ; ni l'état DNS **live**
ni le `tofu apply` ne sont attestés ici.

**Publication ordonnée** (après contrôle de l'état Cloudflare réel) :

1. `dig +short @1.1.1.1 login.albandrieu.com A`, puis vérifier dans
   Cloudflare la nature, la cible et l'ID de l'enregistrement ; un A et un
   CNAME sur le même nom ne peuvent coexister. Ne pas déduire du seul A
   renvoyé par Cloudflare si le record sous-jacent est CNAME (flattening).
2. Lancer le plan `scripts/infra/terragrunt-safe.sh infrastructure/cloudflare plan`
   avec **état Garage privé disponible**, imports d'abord. L'ingress de
   ce tunnel est une liste partagée : vérifier chaque route, chaque
   retrait et chaque `origin_request`. Refuser tout changement annexe.
3. Appliquer seulement le plan approuvé depuis un contexte autorisé ;
   valider Access `Everyone bypass`, CNAME proxied et
   `cloudflared → 172.17.0.24:31090`, sans NAT WAN ni exposition 31090.
4. Depuis une connexion **réellement extérieure**, `curl -sSI
   https://login.albandrieu.com/healthz` attendu 200 ; vérifier ensuite
   `/` avec parcimonie, car chaque appel déclenche un rapport
   Project Honey Pot. `/wp-login.php` doit conserver 404.
   Les réponses 1016/403/404 indiquent des frontières différentes.

## 3. Évolution proposée : tentative de login leurre vers CrowdSec

La *page* de connexion leurre devrait être **`/login` sur le même nom
`login.albandrieu.com`**, en préservant `/` comme piège à collecteurs
d'adresses et `/healthz` comme sonde silencieuse.

**Pas de formulaire/login applicatif ni de stockage des identifiants
présentés :** afficher une page statique de leurre (si approuvée), refuser
tout POST avec 401/403 et jeter le corps sans l'écrire dans les logs.
Les journaux contiennent uniquement métadonnées minimisées (date,
IP vérifiée, méthode, chemin, code HTTP), avec rétention et contrôle d'accès.
Ne pas émettre de bannissement CrowdSec sur un simple GET ni sur la santé.

Le chemin souhaitable **après un pilote spécifique** serait :

```text
HTTPS public login.albandrieu.com
   → Cloudflare Tunnel/Access Everyone bypass
       → Traefik host+chemin /login (opt-in)
           → CrowdSec LAPI bouncer + AppSec + rate limit
               → honeypot /login (leurre)
```

Cette architecture **n'est pas activée** : ni label Traefik
`login`, ni routage Tunnel vers Traefik, ni scénario CrowdSec
de tentative POST n'existent dans cette contribution. Le retrait de
l'ancien nom interne FastAPI ne déploie rien sur le honeypot.
Le port direct `:31090` et le piège Project Honey Pot doivent rester
fonctionnels pendant la recette. Revoir l'IP réelle Cloudflare depuis le
seul peer `cloudflared`, la confiance des headers sur Apache et
les faux positifs avant tout bannissement. Pour limiter la surface d'erreur,
évaluer d'abord un **router canary à chemin limité** plutôt qu'une
bascule de `/` et `/healthz`.

**Cloudflare Turnstile :** le bouncer Worker CrowdSec versionné contient
`actions: [ban, captcha]` et `turnstile.enabled: true`, mais son
profil reste opt-in et doit être déployé/recetté. Un challenge sur
**toutes** les visites du honeypot masquerait les robots recherchés ;
Turnstile est pertinent comme remédiation *sélective* après une décision,
pas comme préalable systématique au leurre. Si un formulaire légitime
devait être créé ailleurs, la validation du token Turnstile doit se faire
côté serveur via Siteverify, pas seulement dans le navigateur.

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
