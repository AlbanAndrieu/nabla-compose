# Nexus — HTTPS privé après le retrait de pfSense

**Révision : 21 novembre 2026. Préparation dans Git uniquement, aucun déploiement.**
Ce document remplace l'ancienne procédure fondée sur pfSense et son HAProxy :
ses preuves datées du 27/10 n'attestent **pas** le réseau actuel. Ne jamais
reprendre les commandes de pfSense de l'historique Git.

## Architecture et critères de sécurité

```text
Workstation Ubuntu 172.17.0.57
   ├─ DNS privé (~int.albandrieu.com) → Pi-hole 172.17.0.24:53
   ├─ Internet → R7000 172.17.0.1 → Freebox routeur
   └─ HTTPS SNI nexus.int.albandrieu.com → Traefik 172.17.0.24:443
                                                  │
                                                  └─ nexus:8081 (réseau traefik_network)
```

- **pfSense retiré depuis le 18/11** ; `172.17.0.1` est désormais le **R7000**.
  Ne pas confondre route par défaut, résolveur DNS et terminaison TLS.
- DNS interne : **Pi-hole uniquement**, ne créer aucun enregistrement public
  `nexus.int.albandrieu.com` et ne pas ajouter de route Cloudflare Tunnel.
  Le nom historique `nexus-albandrieu.int.albandrieu.com` n'est pas un
  remplacement valide du nom canonique.
- Routeur Traefik `nexus-private` **désactivé par défaut** :
  `NEXUS_PRIVATE_INGRESS_ENABLED=false` ; l'activation nécessite l'interpolation
  correcte dans le rendu de l'App TrueNAS (`env_file` conteneur seul ne la garantit pas).
- `Host(`nexus.int.albandrieu.com`)`, TLS avec Let's Encrypt DNS challenge
  Cloudflare, service Nexus HTTP interne sur port 8081, jamais de vérification
  de certificat désactivée. Contrôler **nom, SAN, confiance, date et SNI**.
- Middleware `nexus-private-lan-only` : sources socket
  `172.17.0.0/24,192.168.1.0/24`, **sans** `X-Forwarded-For` ni
  `ipStrategy.depth`. Cette restriction est une défense en profondeur,
  pas une preuve d'absence de NAT ou d'exposition WAN. Les plages Docker
  et le réseau Cloudflare `10.200.2.0/24` ne sont pas autorisés.
- Le nom public `nexus.albandrieu.com` reste sous sa politique **Cloudflare
  Access existante**, indépendamment du nouveau routeur privé. Le port
  `172.17.0.24:8081` est un backend LAN temporaire : fermer son accès
  client après migration validée, sans fermer l'accès Traefik→Nexus.

## Gate 0 — transport LAN avant DNS et Nexus (read-only)

Depuis la workstation ; toute erreur réseau reste **LAN_TRANSPORT_UNVERIFIED**,
jamais un `NXDOMAIN` inféré. **Suspendre** le déploiement si le transport est
indéterminé.

```bash
ip -br -4 address
ip -4 route get 172.17.0.1         # R7000, pas pfSense
ip -4 route get 172.17.0.24
ip neigh show to 172.17.0.24
# Ne pas imprimer les secrets, headers ni cookies.
curl --noproxy '*' --connect-timeout 2 --max-time 6 -sS \
  -o /dev/null -w 'nexus_backend_http=%{http_code}\n' \
  http://172.17.0.24:8081/
```

Une réponse `200`, `302` ou `401` ne prouve pas l'authentification
fonctionnelle. `000` signale l'absence de réponse HTTP, non une absence de DNS.

## Gate 1 — DNS privé, HTTP et certificat (read-only)

```bash
dig +tries=1 +time=2 @172.17.0.24 nexus.int.albandrieu.com A
dig +tcp +tries=1 +time=2 @172.17.0.24 nexus.int.albandrieu.com A
getent ahostsv4 nexus.int.albandrieu.com

# --resolve force uniquement l'IP sans contourner la vérification TLS.
curl --noproxy '*' --connect-timeout 2 --max-time 8 -sS \
  --resolve nexus.int.albandrieu.com:443:172.17.0.24 \
  -o /dev/null \
  -w 'nexus_ingress_http=%{http_code} tls_verify=%{ssl_verify_result}\n' \
  https://nexus.int.albandrieu.com/
```

Un timeout n'est **pas** une preuve DNS : aucune négociation exploitable n'a eu lieu. Le service `s3.int.albandrieu.com` conserve sa propre politique d'exposition et ne sert pas d'exception pour Nexus.

Un `404` au niveau Traefik tant que la route est désactivée est **attendu**.
Un `403` après activation peut provenir du middleware IP et ne constitue
pas une preuve que le backend ou le TLS est sain. `tls_verify=0` ne compte
que lorsque la connexion HTTPS a effectivement abouti.

## Gate 2 — source TrueNAS et plan opt-in (sans mutation)

```bash
# Vérifier le SHA et la source réellement chargée par TrueNAS.
sudo midclt call app.query | jq -c '.[] | select(.name == "nexus") | {name,state}'
sudo midclt call app.config nexus | jq '{include_type:(.include|type),include_paths:.include}'

# Ne jamais afficher la configuration environnement/secrets de Docker.
sudo docker inspect nexus --format '{{json .Config.Labels}}' |
  jq '{enabled:.["traefik.enable"],rule:.["traefik.http.routers.nexus-private.rule"],
       middleware:.["traefik.http.routers.nexus-private.middlewares"],
       allowlist:.["traefik.http.middlewares.nexus-private-lan-only.ipallowlist.sourcerange"]}'
```

Les labels et les chemins du dépôt dans Git ne prouvent rien sur l'App
TrueNAS effective. Les services TrueNAS construits par `app.config`
ne doivent pas être modifiés via le rendu sous `/mnt/.ix-apps`.
L'activation via `NEXUS_PRIVATE_INGRESS_ENABLED=true` nécessite un plan
séparé, avec snapshot, contrôle TLS et rollback vers `false`. Un simple
`docker restart nexus` n'applique pas les nouveaux labels.

## Gate 3 — test de refus WAN et bascule clients

- **Source externe indépendante :** tester depuis un réseau hors LAN,
  autorisé, avec SNI `nexus.int.albandrieu.com` et sans DNS privé. Résultat
  exigé : **connexion refusée**, ou HTTP `403` après terminaison TLS.
  `WAN_REJECTION_NOT_VERIFIED` tant que non observé. Le hairpin LAN et
  le seul DNS split-horizon **ne sont pas** un test de refus WAN.
- Tester depuis le LAN autorisé, puis depuis un conteneur du réseau
  `10.200.2.0/24` : le second doit être **refusé**. Inspecter le socket
  peer effectif et le NAT Docker avant d'attribuer un résultat `403`.
- Conserver les contrôles Cloudflare Access du nom public existant.
  Tester également qu'aucun tunnel ni règle Freebox/R7000 ne route le nom
  privé vers Traefik depuis l'extérieur.
- **Seulement après les gates 0–3** : modifier un unique client pilote
  npm/PyPI (puis APT) dans `ansible-workstation` PR #39 ; conserver
  les signatures Ubuntu, les tokens hors Git et un repli explicite.
  Les dépôts OpenTofu de Nexus sont gérés par `nabla-compose`.

Les opérations `--apply` et le redéploiement TrueNAS sont **NOT_RUN** dans
cette préparation. Les historiques HAProxy du 27/10 et les captures de
politique pfSense restent utiles pour la forensique mais ne constituent
plus un préflight exécutable.
