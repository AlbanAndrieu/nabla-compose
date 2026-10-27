# FastAPI TrueNAS — diagnostic du build échoué le 27/10/2026

## Preuves acquises

La tentative de déploiement du commit FastAPI 0266f20d7ff1278bf7dd36ac15a22618d04b3742 a échoué à l'étape 3/6 (construction Docker). Le script confirme que l'ancien conteneur a été préservé. Le log privé est /tmp/tmp.ngofCbFlgw, avec des données potentiellement sensibles.

Les Dockerfiles de fa13c08d (build réussi précédemment) et 0266f20d (échec) sont identiques, empreinte Git 9c1e1da90c66612ec65001e01d9115956b18104a. Le contexte et les ressources peuvent toutefois avoir changé. **La cause précise du build est inconnue** tant que le journal privé n'a pas été classé.

Le test Playwright normal/safe a été exécuté avant le déploiement de 0266f20d : les deux résultats main_thread_unresponsive ne valident donc pas encore le mode de secours ui_safe. Le blocage du navigateur est indépendant de l'échec du build.

## Classer sans imprimer le journal

Depuis un checkout TrueNAS actualisé sur la branche de PR #289 :

~~~bash
python3 scripts/truenas/classify-fastapi-build-failure.py \
  --check --log /tmp/tmp.ngofCbFlgw
~~~

Si le journal appartient à root, exécuter uniquement le classifieur avec sudo :

~~~bash
sudo python3 scripts/truenas/classify-fastapi-build-failure.py \
  --check --log /tmp/tmp.ngofCbFlgw
~~~

Ce script ouvre seulement un fichier mktemp régulier, non symlinké, situé directement sous /tmp, avec permissions privées. Il ne renvoie aucune ligne du log, URL, chemin interne arbitraire, identifiant ou secret. La sortie est un JSON à vocabulaire fermé.

Ne pas utiliser cat, tail, grep, Docker --progress=plain, FASTAPI_SAMPLE_VERBOSE_LOGS=true, ni copier le log dans ChatGPT.

## Cas `unsafe_log_owner` sous `sudo`

Ce code signifie que le fichier n'a pas été lu : **aucune cause Docker n'a encore été identifiée**. Le script accepte les journaux privés appartenant à `root`, à l'UID effectif du processus, ou (seulement sous `sudo` exécuté en root) à l'UID d'origine déclaré par `SUDO_UID`. Les fichiers appartenant à un autre UID restent refusés.

Le contrôle ci-dessous ne révèle **que des métadonnées**, jamais le contenu du log :

~~~bash
stat -c 'owner_uid=%u mode=%a links=%h type=%F' /tmp/tmp.ngofCbFlgw
id -u
sudo sh -c 'printf "sudo_original_uid=%s\n" "${SUDO_UID:-unset}"'
~~~

Utiliser la **dernière version de la branche #289** avant de réessayer le classifieur ; huit tests seulement indiquent un checkout ancien, avant l'ajout des nouveaux cas. Si `owner_uid` diffère de `0` et de l'UID d'origine transmis par `sudo`, ne pas faire de `chown`, `chmod`, ni désactiver le contrôle ; investiguer d'abord quel compte a créé le journal. Un `mode` plus large que `600`, un lien symbolique ou un autre type de fichier reste bloquant.

~~~bash
git fetch origin fix/nexus-wan-haproxy-acl-evidence-20261027
git show origin/fix/nexus-wan-haproxy-acl-evidence-20261027:scripts/truenas/classify-fastapi-build-failure.py |
  sudo python3 - --check --log /tmp/tmp.ngofCbFlgw
~~~

Ne communiquer que le JSON de classification. Le journal reste strictement local à TrueNAS.

## Étape intermédiaire du diagnostic : échec initialement non classé

La recette opérateur a confirmé que `/tmp/tmp.ngofCbFlgw` est un fichier régulier privé (`owner_uid=1000`, `mode=600`, `links=1`). L'invocateur `sudo` a aussi l'UID 1000. Avec le classifieur corrigé, l'ouverture réussit mais la sortie demeure `state=unclassified_build_failure`, `matched_categories=[]`, `raw_log_printed=false`.

**Cela n'établit pas la cause du build.** Le classifieur enrichi analyse les derniers **4 Mio** d'un journal de **20 Mio maximum**, traite plus de signatures BuildKit, et indique `buildkit_failure_marker`, `failure_stage` et `failure_operation`. Ces champs sont des codes de vocabulaire fixe. `unknown` signifie que la corrélation avec l'identifiant BuildKit de l'étape n'est pas prouvée. `build_step_nonzero` ne signifie pas nécessairement une dépendance défectueuse.

### Prochaine recette sans build

~~~bash
git fetch origin fix/nexus-wan-haproxy-acl-evidence-20261027
git show origin/fix/nexus-wan-haproxy-acl-evidence-20261027:scripts/truenas/classify-fastapi-build-failure.py |
  python3 - --check --log /tmp/tmp.ngofCbFlgw
~~~

Le propriétaire du journal est le même UID que l'utilisateur courant : **pas besoin de sudo** dans ce cas. Pour vérifier les nouveaux contrats avec le checkout à jour, exécuter `python3 -m unittest discover -s tests -p 'test_fastapi_build_failure_classifier.py' -v`. Ne publier que le JSON. Si `unclassified_build_failure` persiste, contrôler localement **la présence et la taille du journal** sans communiquer son contenu ; le diagnostic reste bloqué tant qu'aucune cause observable n'est identifiée. Ne pas relancer le builder pour obtenir de nouvelles preuves, ni effectuer un redéploiement concurrent.

## Origine du faux refus de propriétaire et preuve BuildKit intermédiaire

**`unsafe_log_owner` était un faux positif du classifieur, pas une permission Docker incorrecte.** Le shell de déploiement lance `log="$(mktemp)"` dans `build_fastapi_sample()`, ce qui crée le fichier `0600` au nom de l'utilisateur opérateur (UID 1000). Ensuite, `run_build_attempt()` écrit le résultat de `run_docker` dans ce fichier. L'exécution éventuelle du client Docker avec `sudo` ne change **pas** le propriétaire du journal. L'ancien test de sécurité `st_uid in (0, os.geteuid())` refusait l'UID 1000 lorsque le diagnostic était exécuté en EUID 0. Avec `SUDO_UID=1000` validé, ou simplement avec Python exécuté par l'utilisateur propriétaire, le journal est lu sans modifier les droits.

Dernière classification opérateur à partir du journal réel : `state=buildkit_generic_failure`, `buildkit_failure_marker=true`, `failure_stage=unknown`, `failure_operation=unknown`, `raw_log_printed=false`. Elle atteste une signature d'erreur générique BuildKit, **pas la cause racine**. Une étape inconnue peut résulter d'une sortie BuildKit sans identifiant `#N ERROR` corrélable, ou du fait que le classifieur lit uniquement les 4 derniers Mio. Ne pas déduire un OOM ou un problème `uv` sans preuve.

**Suite en lecture seule :** relever `stat -c 'size_bytes=%s' /tmp/tmp.ngofCbFlgw`, puis examiner une preuve privée plus ciblée localement si le journal existe et la classification ne progresse pas. Ne transmettre ni extrait, ni URL, ni argument BuildKit, ni secret. Maintenir le conteneur précédent et ne pas relancer de build tant que le diagnostic n'est pas exploitable.

## Journal complet : 1324 octets (preuve opérateur)

Le journal privé `/tmp/tmp.ngofCbFlgw` fait **1324 octets**. Le classifieur lit jusqu'à 4 Mio, donc **aucune troncature de ce journal** n'explique `failure_stage=unknown` ou `buildkit_generic_failure`. L'échec précis n'est toujours pas démontré. Ne pas augmenter encore la fenêtre de lecture.

De nouvelles règles reconnaissent les erreurs de Dockerfile absent ou invalide, les métadonnées d'image de base, le contexte de build, la sélection du service Compose, une référence d'image invalide et les erreurs de cache. Les sorties restent des codes fixes et ne comprennent ni texte de journal, ni chemin, ni URL.

Réexécuter la classification au HEAD de la branche #289, sans `sudo` (UID 1000) et transmettre uniquement le JSON. Si l'état reste `buildkit_generic_failure`, la prochaine action est une inspection **locale et privée** de l'erreur terminale avec l'opérateur, sans coller de ligne brute ni transmettre le journal ; l'étape `3/6` reste fermée pour tout redéploiement.

## Dernière classification : échec générique sur le journal entier

La nouvelle exécution du 27 octobre retourne toujours `state=buildkit_generic_failure`, `failure_stage=unknown`, `failure_operation=unknown`, `buildkit_failure_marker=true` et `raw_log_printed=false`, malgré les signatures supplémentaires. Le journal mesure **1324 octets** : il est lu intégralement. **Ne pas ajouter d'autres catégories au hasard.**

Pour caractériser le message terminal sans publier son texte ni aucun secret, lancer uniquement la nouvelle option `--failure-shape` du classifieur **depuis le même UID 1000 propriétaire du log** :

~~~bash
git fetch origin fix/nexus-wan-haproxy-acl-evidence-20261027
git show origin/fix/nexus-wan-haproxy-acl-evidence-20261027:scripts/truenas/classify-fastapi-build-failure.py |
  python3 - --check --failure-shape --log /tmp/tmp.ngofCbFlgw
~~~

La sortie est un JSON à champs fixes : `terminal_marker_style`, `terminal_keyword_codes` (seuls termes techniques d'une liste prédéfinie), `error_marker_count`, `numbered_error_count`, `buildkit_step_headers_present`, `ansi_escapes_present`. L'option est facultative et ne change pas le résultat standard du classifieur. Ne pas communiquer le journal, d'empreinte cryptographique du journal, d'extrait de commande, d'URL, ni de chemin provenant du journal. Si le diagnostic structurel ne suffit pas, la **lecture humaine de l'erreur doit rester locale à TrueNAS** : en communiquer uniquement une catégorie reformulée, non un extrait.

Aucun appel Docker, aucune CI et aucun redéploiement ne font partie de cette opération.

## Diagnostic confirmé — HTTP 429 Docker Hub sur l'image Python

**Preuve opérateur du 27 octobre 2026** : journal complet de 1324 octets, privé (UID 1000, permissions 0600) ; `state=registry_request_failure`, `failure_stage=internal`, `failure_operation=image_metadata`, `registry_provider=docker_hub`, `registry_image=official_python`, `registry_request_method=HEAD`, `registry_http_status=429`, `registry_http_class=rate_limited`, `raw_log_printed=false`. La référence de l'image de base dans le Dockerfile est `python:3.13-slim-trixie` et elle est utilisée par trois étapes de build. **Cause immédiate de l'échec du build : limitation HTTP 429 côté Docker Hub**. Le gel du navigateur de `/api` est un autre défaut ; son correctif #380 n'a pas été déployé sur TrueNAS.

Le code 429 ne suffit pas à établir s'il s'agit du **quota de pulls** (fenêtre de 6 heures) ou de la **limitation anti-abus** (nombre de requêtes élevé, valable même pour les comptes authentifiés). Docker distingue les deux par le corps de réponse ; le classifieur ne l'affiche pas. Éviter les boucles de tentatives et les `pull --all-tags`. Sources : https://docs.docker.com/docker-hub/troubleshoot/ ; https://docs.docker.com/docker-hub/usage/pulls/ ; https://docs.docker.com/docker-hub/usage/ .

### Préflight strictement en lecture seule — aucune requête au registre

~~~bash
if sudo docker info >/dev/null 2>&1; then
  echo "docker_daemon=accessible"
  if sudo docker image inspect python:3.13-slim-trixie >/dev/null 2>&1; then
    echo "python_base_image_cache=present"
  else
    echo "python_base_image_cache=absent"
  fi
else
  echo "docker_daemon=unavailable"
fi

# Identifie quel client serait utilisé par run_docker dans le script :
if docker info >/dev/null 2>&1; then
  echo "build_docker_client=user"
else
  echo "build_docker_client=sudo_candidate"
fi

# Ne vérifie que l'existence de la configuration, PAS l'authentification effective.
if test -s "${HOME}/.docker/config.json"; then
  echo "user_docker_config=present"
else
  echo "user_docker_config=missing"
fi
if sudo sh -c 'test -s "${HOME}/.docker/config.json"'; then
  echo "sudo_docker_config=present"
else
  echo "sudo_docker_config=missing"
fi
~~~

Ne pas imprimer `config.json` ; il peut contenir des identifiants ou pointeurs de coffre. La présence du fichier ne prouve pas que Docker Hub est authentifié. `cached=no_or_access_error` vu précédemment **ne prouve pas** l'absence d'image : distinguer l'accès au daemon de la présence de l'image avec les deux premières commandes.

### Récupération ciblée, après attribution du type de 429

1. **Pull quota :** attendre le renouvellement de la fenêtre de six heures ou, après intervention explicite de l'opérateur, authentifier le **même client Docker** que `run_docker` dans un contexte de configuration protégé. Ne pas mettre un token dans une commande ou dans `compose.yml`. `sudo docker` peut utiliser un autre magasin d'identifiants que `docker`.
2. **Anti-abus :** réduire le trafic sortant et laisser expirer le blocage ; une connexion Docker Hub ne garantit pas de lever ce type de 429. Inspecter les pollers ou builds répétés du homelab avant de modifier le réseau.
3. **Une fois le 429 levé :** effectuer au plus un `docker pull python:3.13-slim-trixie` avec le client effectif. Vérifier l'image dans le cache avant un seul déploiement du SHA immuable `0266f20d7ff1278bf7dd36ac15a22618d04b3742`. Ce pull **télécharge une image** et n'appartient pas au préflight en lecture seule.
4. **Acceptation :** vérifier l'étape 6/6, l'endpoint /health et la provenance de l'image, puis comparer `node scripts/diagnose-production-api-ui-freeze.mjs truenas` et `node scripts/diagnose-production-api-ui-freeze.mjs truenas --safe` depuis un checkout FastAPI contenant #380. Ne pas attribuer une réussite UI au seul HTTP 200.

Aucune modification du daemon global TrueNAS, du Dockerfile, de pfSense, des services Nexus/DefectDojo ni de configuration DNS n'est nécessaire à ce stade. Un proxy pull-through Nexus ou un miroir Docker Hub peut être évalué ultérieurement pour limiter les téléchargements, mais **pas configuré dans cette intervention** (impacts multi-services). Documentation Docker : https://docs.docker.com/docker-hub/usage/manage/ ; https://docs.docker.com/docker-hub/image-library/mirror/ .

## Causes classées et actions de lecture seule

| État | Diagnostic suivant |
| --- | --- |
| disk_full | df -h sur les volumes et l'espace Docker |
| oom_or_killed | free -h, /proc/pressure/memory, OOM noyau |
| buildkit_frontend_crash | état BuildKit, mémoire, ressources disponibles |
| network_dns / network_timeout | DNS et connectivité des registres depuis le builder |
| registry_auth / tls_certificate | autorisation du registre ou CA, sans exposer le jeton |
| uv_dependency | résolution des dépendances et métadonnées uv.lock |
| apt_package | cache apt et disponibilité du miroir Debian |
| dockerfile_copy | sous-modules et contexte du build |
| builder_unavailable | état du daemon Docker |
| filesystem_permissions | droits du contexte ou des montages du builder |
| dependency_fetch | liaison vers les miroirs/référentiels de dépendances |
| build_step_nonzero | analyser en privé l'étape signalée, sans présumer de la cause |
| buildkit_generic_failure | erreur Docker générale, classification détaillée encore manquante |
| unclassified_build_failure | vérification privée plus ciblée sans partage du log |

La catégorie est indicative. En cas de plusieurs signatures, la priorité protège contre les erreurs génériques qui masquent un OOM ou un disque plein.

## Vérifier le runtime conservé avant un autre build

~~~bash
sudo docker inspect fastapi-sample \
  --format 'state={{.State.Status}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}'

curl -sS -o /dev/null -w 'http=%{http_code}\n' \
  --connect-timeout 2 --max-time 5 http://127.0.0.1:8091/health

free -h
cat /proc/pressure/memory
~~~

Ne pas redémarrer un service ni relancer le build simplement pour reproduire l'échec.

## Modifications proposées en PR #289

Le chemin d'échec de scripts/truenas/update-fastapi-sample.sh a été complété : au prochain échec, il peut imprimer la classification de manière sûre tout en conservant le journal privé et le conteneur actif.

La recette future doit déployer un seul SHA FastAPI immuable à la fois, vérifier l'acceptation 6/6, puis comparer le navigateur normal et le mode public-only /api?ui_safe=1. Ce mode n'a pas été activé par la tentative échouée.

Le code UI reste dans fastapi-sample ; l'orchestration et la preuve de build restent dans nabla-compose PR #289. Les travaux Nexus et DefectDojo de cette PR ne sont pas modifiés.
