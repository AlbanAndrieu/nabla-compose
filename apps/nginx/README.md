# Hello Nginx : routage privé Traefik et recette

État du dépôt vérifié le 21/11/2026 : **le service est déjà
déclaré derrière Traefik** dans `apps/nginx/compose.yml` :

- Application TrueNAS `nginx`, conteneur `nginx:1-alpine`, port
  LAN `172.17.0.24:8099` (port Docker publié 8099).
- Réseau Docker externe `traefik_network`.
- `traefik.enable=true`, Host `hello.int.albandrieu.com`,
  entrypoint `websecure` (:443), TLS via resolver `letsencrypt`,
  backend Nginx `:80` et service Traefik `hello`.
- Gatus source native : TCP 8099 (backend), plus nouvel endpoint
  `Hello Nginx via Traefik` en **HTTPS** sur le hostname et code 200.
  Traefik TCP :443 est sondé séparément. Probes tous les 60 s.
- Prometheus scrape Traefik `:8082/metrics` et alerte sur absence
  de cible, scrape échoué ou absence de backend sain (si le metric
  `traefik_service_server_up` existe).

**Attention au décalage de topologie :** la déclaration
`x-nabla.exposure.public.gatewayRef=pfsense-haproxy` et son
`riskAcceptance.reason` évoquent encore l'ancien HAProxy,
retiré le 18/11. Ils décrivent une **intention/exception publique
historique**, et **ne prouvent plus aucune exposition WAN**.
Le nom `hello.int.albandrieu.com` est une exception DNS publique
gérée séparément par `cloudflare-ddns` (sans proxy).
Ne pas ajouter à la légère un second routeur, un NAT WAN ou une
nouvelle route Cloudflare Tunnel. Auditer d'abord DNS public,
Pi-hole, TLS et l'absence de pfSense ; enregistrer les constats
dans H04 puis décider séparément de la politique publique.
Aucun basculement DNS n'a été effectué par cette PR.

## Réception après synchronisation Git sur TrueNAS

```bash
cd /mnt/cpool/compose/nabla-compose
sudo docker compose -f apps/nginx/compose.yml config --quiet
sudo docker network inspect traefik_network --format '{{json .IPAM.Config}}'
sudo docker inspect nginx --format '{{json .NetworkSettings.Networks}}'

# Preuve Nginx directe (pas le routeur Traefik)
curl -fsS --max-time 5 http://172.17.0.24:8099/ >/dev/null

# Preuve du vrai routeur avec SNI et validation du certificat :
curl --fail-with-body --max-time 10 \
  --resolve hello.int.albandrieu.com:443:172.17.0.24 \
  https://hello.int.albandrieu.com/ -o /dev/null

# Diagnostic observabilité sans appliquer la configuration
curl -fsS --max-time 5 http://172.17.0.24:8082/metrics \
  | grep -m1 '^traefik_service_server_up' || true
```

Si le Compose versionné n'est pas encore celui appliqué dans
l'application TrueNAS, **après sauvegarde/revue**, redéployer
uniquement l'app `nginx` par la procédure opérateur
(`sudo midclt call -j app.redeploy nginx`) puis revérifier
les sorties ci-dessus. Le redéploiement n'a pas été exécuté
depuis le connecteur GitHub.

Critère Done : Nginx HTTP 200, TLS Traefik validé sans `-k`,
Gatus backend 8099 et frontend HTTPS au vert, scrape Prometheus
Traefik UP, aucune dérive de DNS public. Une cible Gatus en erreur
n'implique pas automatiquement une panne globale de Traefik.

[Runbook général](../../docs/runbooks/workstation-truenas-report-sharing-and-honeypot.md).
