# Migration contrôlée — `homeassistant` et `openwebui`

**État : souhaité dans la PR #273 ; non appliqué à TrueNAS ou Cloudflare.**

## Contrats à préserver

| Élément | Avant | Cible |
|---|---|---|
| Home Assistant Compose service / container | `homeassistant` | déjà correct |
| Home Assistant TrueNAS app ID (historique possible) | `home-assistant` | `homeassistant`, sous contrôle TrueNAS |
| Open WebUI Compose service / container | `open-webui` | `openwebui` |
| Open WebUI Backstage ID | `openwebui` | inchangé |
| Open WebUI Tunnel hostname | `open-webui.albandrieu.com` | `openwebui.albandrieu.com` |
| Open WebUI origin | `http://172.17.0.24:31028` | inchangé |
| Open WebUI données | `/mnt/cpool/openwebui/data` | inchangé |
| Home Assistant données | `/mnt/storage0/home-assistant/config` | inchangé |
| Images Docker officielles | `ghcr.io/open-webui/open-webui`, `ghcr.io/home-assistant/home-assistant` | inchangées |

N'enlevez **pas** les tirets des noms de produit, images officielles, chemins existants contenant des données ou clés d'environnement du fournisseur. La normalisation concerne les identifiants de service et le hostname du nouveau point d'entrée.

## Procédure — une action par étape

1. Exécuter `bash scripts/truenas/migrate-homeassistant-openwebui-names.sh --check` depuis le checkout TrueNAS.
2. Lire l'inventaire Docker et `midclt call app.query` en mode lecture seule.
3. Créer une sauvegarde indépendante et vérifiée des données Home Assistant et Open WebUI.
4. Créer **manuellement** dans Cloudflare Zero Trust le hostname `openwebui.albandrieu.com` vers `http://172.17.0.24:31028`.
5. Associer au nouveau hostname une politique Cloudflare Access MFA/Service Auth au moins aussi restrictive que l'ancienne.
6. Vérifier le DNS et le comportement Access du nouveau hostname. Refuser tout bypass involontaire.
7. Modifier la définition de l'application **depuis TrueNAS** si `midclt app.query` en confirme la propriété. Ne pas utiliser un `docker compose up` parallèle contre une application TrueNAS.
8. Recréer uniquement la charge Open WebUI avec le service et conteneur `openwebui` à l'aide de la procédure TrueNAS approuvée. Pour une installation Compose **indépendante**, la variante explicite est `NABLA_RUNTIME_CHANGE_APPROVED=yes bash scripts/truenas/migrate-homeassistant-openwebui-names.sh --apply` après préflight et injection des secrets légitimes.
9. Vérifier les identités Docker, l'accès à l'UI, la persistance des données, LiteLLM et OpenRAG.
10. Vérifier le nouveau chemin Cloudflare Tunnel et Access sur navigateur privé et mobile.
11. Vérifier les consommateurs FastAPI/Site, leurs `entityRef`, les sondes Gatus et les logs expurgés.
12. Supprimer l'ancienne route `open-webui.albandrieu.com` seulement après une période de surveillance et approbation explicite.

Le script `--apply` n'efface pas le conteneur de retour arrière après succès. Il ne modifie **jamais** Cloudflare DNS/Access ni les datasets. Sur un déploiement TrueNAS géré, il bloque et demande une procédure via le middleware de TrueNAS.

## Échecs et rollback

- Échec du déploiement autonome : le script tente de remettre en marche l'ancien conteneur `open-webui`. Vérifier le port `:31028` et le conteneur de sauvegarde.
- Échec de la nouvelle route : conserver l'ancien hostname et son application Access, sans contourner MFA.
- Échec d'une application TrueNAS : utiliser la sauvegarde et la configuration d'application TrueNAS avant toute suppression.
- Contrôle des statuts : `container RUNNING` ne remplace pas la sonde HTTP authentifiée. Une réponse HTTP `302` d'Access ne prouve pas la santé de l'origine.

## Qualité hors CI payante

Depuis un checkout complet : `bash -n scripts/truenas/migrate-homeassistant-openwebui-names.sh`, `docker compose --project-directory apps/openwebui -f apps/openwebui/compose.yml config --quiet --no-interpolate --no-env-resolution`, `python scripts/generate-service-topology.py`, `python scripts/generate-service-topology.py --check`, `python -m unittest tests.test_openwebui_canonical_migration` puis la quality gate locale. Ne pas mettre la PR Ready avant ces validations.
