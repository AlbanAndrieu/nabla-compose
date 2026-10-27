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

## État réel du 27 octobre : échec non classé

La recette opérateur a confirmé que `/tmp/tmp.ngofCbFlgw` est un fichier régulier privé (`owner_uid=1000`, `mode=600`, `links=1`). L'invocateur `sudo` a aussi l'UID 1000. Avec le classifieur corrigé, l'ouverture réussit mais la sortie demeure `state=unclassified_build_failure`, `matched_categories=[]`, `raw_log_printed=false`.

**Cela n'établit pas la cause du build.** Le classifieur enrichi analyse les derniers **4 Mio** d'un journal de **20 Mio maximum**, traite plus de signatures BuildKit, et indique `buildkit_failure_marker`, `failure_stage` et `failure_operation`. Ces champs sont des codes de vocabulaire fixe. `unknown` signifie que la corrélation avec l'identifiant BuildKit de l'étape n'est pas prouvée. `build_step_nonzero` ne signifie pas nécessairement une dépendance défectueuse.

### Prochaine recette sans build

~~~bash
git fetch origin fix/nexus-wan-haproxy-acl-evidence-20261027
git show origin/fix/nexus-wan-haproxy-acl-evidence-20261027:scripts/truenas/classify-fastapi-build-failure.py |
  python3 - --check --log /tmp/tmp.ngofCbFlgw
~~~

Le propriétaire du journal est le même UID que l'utilisateur courant : **pas besoin de sudo** dans ce cas. Pour vérifier les nouveaux contrats avec le checkout à jour, exécuter `python3 -m unittest discover -s tests -p 'test_fastapi_build_failure_classifier.py' -v`. Ne publier que le JSON. Si `unclassified_build_failure` persiste, contrôler localement **la présence et la taille du journal** sans communiquer son contenu ; le diagnostic reste bloqué tant qu'aucune cause observable n'est identifiée. Ne pas relancer le builder pour obtenir de nouvelles preuves, ni effectuer un redéploiement concurrent.

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
