# LiteLLM dashboard 401, DefectDojo login et Prometheus — 26 octobre 2026

## LiteLLM — session de l'interface expirée, pas une clé de modèle

Incident opérateur : `401_AUTHENTICATION_FAILED` / `Expired Key`,
`user_api_key_team_id=litellm-dashboard`, `total_tokens=0` et
User-Agent Chrome Linux. Expiration horodatée au **25 octobre 2026
20:35:59 UTC**, rejet au **26 octobre 2026 19:21:45 UTC**.

Le tableau de bord LiteLLM délivre une clé de **session UI temporaire**,
indépendante des clés virtuelles de services. Une session expirée
dans un ancien onglet peut continuer à appeler les routes
`/key/list`, `/user/info` et `/models`. LiteLLM peut alors
enregistrer ces 401 dans les `SpendLogs` comme des échecs LLM
avec zéro token, bien qu'aucun fournisseur de modèles ne soit sollicité.
Ce phénomène est décrit dans
[l'issue upstream #35789](https://github.com/BerriAI/litellm/issues/35789)
et la [PR upstream #35791](https://github.com/BerriAI/litellm/pull/35791),
qui n'était pas fusionnée lors de la vérification du 26 octobre.

### Réparation utilisateur (sans redeploy)

1. Fermer **tous** les anciens onglets LiteLLM `/ui`.
2. Ouvrir le tableau de bord et utiliser **Logout**, puis
   se reconnecter avec le compte administrateur nominatif.
3. Si l'ancienne session persiste, effacer **uniquement les données
   de site LiteLLM** dans le navigateur, puis refaire le login.
   Cela supprime la session locale ; ne pas effacer les données
   d'autres applications du homelab.
4. Vérifier l'absence de nouveaux `401 Expired Key` pour
   `litellm-dashboard` après le nouveau login. Les anciens
   `SpendLogs` ne disparaissent pas automatiquement.

Ne pas renouveler `LITELLM_MASTER_KEY`, `LITELLM_IDE_API_KEY`,
les clés FastAPI, OpenClaw ou OpenRAG pour cet incident.
Ne pas prolonger toutes les expirations des clés métier et ne pas
désactiver l'expiration de session simplement pour masquer les 401.

### Classification sûre d'un événement LiteLLM

Un export JSON de **cet événement unique**, conservé dans un
fichier privé, peut être analysé sans afficher hash de clé,
adresse IP, User-Agent, identifiants de requête ni message brut :

```bash
python3 scripts/truenas/diagnose-litellm-dashboard-auth.py \
  --check --input /chemin/prive/litellm-event.json
```

La catégorie `EXPIRED_DASHBOARD_SESSION` signifie
`close_stale_ui_tabs_and_sign_in_again`. Un échec d'une clé de
service est classé séparément `EXPIRED_VIRTUAL_KEY`.
Cette classification est **offline** ; elle ne teste ni le proxy
actuel, ni sa base PostgreSQL, ni les modèles.

Pour contrôler la disponibilité du **proxy** séparément :

```bash
python3 scripts/truenas/diagnose-protected-service-http.py --check
```

## DefectDojo — disponibilité privée du login

L'URL demandée est
`https://defectdojo.int.albandrieu.com/login?next=/`.
Le suffixe `.int` est résolu par le DNS interne, pas par
l'accès Web public de l'agent. Un précédent test de l'opérateur
avait donné HTTP 200 après redirection, TLS vérifié, mais
**aucune nouvelle preuve runtime** n'a été obtenue aujourd'hui.

Exécuter depuis le LAN :

```bash
bash scripts/workstation/check-defectdojo-login-lan.sh --check
```

La sonde utilise `--resolve` vers `172.17.0.24` avec SNI
et vérification de certificat obligatoires. Elle **ne suit aucune
redirection externe**, ne télécharge pas la page dans un fichier,
n'affiche ni cookies ni formulaires, et ne fournit aucune
authentification. Verdicts :

- `PASS` : HTTP 200 HTML, TLS vérifié ;
- `UNVERIFIED` : redirection 30x ou 401/403 ;
- `FAIL` : erreur TLS, 5xx, page non-HTML ou route introuvable.

Un `PASS` prouve la **disponibilité anonyme de la page de login**,
pas que le compte Django accepte le mot de passe ni que les tâches
Celery et la base sont saines. Si la sonde échoue, poursuivre avec
`sudo bash scripts/truenas/diagnose-defectdojo.sh --check`.
Ne pas publier le domaine `.int` dans le DNS public.

## Prometheus — conteneur RUNNING mais port inaccessible

Le 26 octobre, TrueNAS confirme la nouvelle matérialisation
`credential_ready`, les quatre conteneurs de Prometheus
`running` et le bind du secret FastAPI présent. Mais
`curl` sur `172.17.0.24:9090/-/ready` renvoie
`connection refused`. Un état `app.query RUNNING` ne garantit
pas que le processus écoute ou que les règles Docker publient
réellement le port.

Contrôles **sans redeploy ni secret** sur TrueNAS :

```bash
sudo docker inspect prometheus --format \
  'state={{.State.Status}} restarting={{.State.Restarting}} restarts={{.RestartCount}} exit={{.State.ExitCode}}'
sudo ss -lnt '( sport = :9090 )'
curl --noproxy '*' -sS --connect-timeout 2 --max-time 5 \
  http://127.0.0.1:9090/-/ready
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
```

Si le conteneur redémarre, regarder les **catégories de logs**
`permission denied`, `rules`, `TSDB/WAL`, `parse error` du
diagnostic existant. Ne pas supprimer le TSDB ni élargir les
permissions des secrets pour tenter de rendre la sonde verte.
