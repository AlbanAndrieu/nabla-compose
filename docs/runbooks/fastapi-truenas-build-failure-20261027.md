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
