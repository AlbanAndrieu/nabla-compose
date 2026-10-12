# DefectDojo — accès CI GitHub via Cloudflare Tunnel et Access

## Architecture retenue (préparation, non déployée)

GitHub Actions (runner hébergé, uniquement `master` / environment protégé)
→ HTTPS `defectdojo-ci.albandrieu.com` (nom proposé, **pas un DNS existant**)
→ Cloudflare Access **Service Auth** (Service Token dédié)
→ Tunnel `cloudflared` existant du homelab
→ HTTP interne `172.17.0.24:31085` → DefectDojo API v2.

Le hostname est **hypothétique** jusqu'à vérification du domaine, du tunnel existant et des règles DNS. Ne pas l'ajouter au routage de production sans vérification des conflits de noms. **Aucune ouverture WAN du port 31085** et aucun tunnel vers l'interface d'administration générique.

## Politique réseau et identité

1. Garder le tunnel en connexion **sortante**. Définir une application Access dédiée à `defectdojo-ci.albandrieu.com`, politique **Service Auth** pour un seul Service Token GitHub Actions ; aucune règle bypass, `Everyone` ou accès anonyme. Conserver l'interface interactive derrière sa politique humaine séparée.
2. Limiter le réseau `cloudflared` → origine DefectDojo au seul port TCP 31085. Activer **Protect with Access** côté tunnel ou validation JWT Access côté origine ; vérifier qu'un contournement direct ne permet pas de passer les règles. Appliquer du rate limiting et de l'observabilité non sensible.
3. Dans GitHub, créer un environnement `defectdojo-production` avec approbations/branches autorisées. Secrets `DEFECTDOJO_URL`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`, `DEFECTDOJO_API_TOKEN`, et variable `DEFECTDOJO_PRODUCT_NAME=nabla-site-alban` **uniquement si le produit exact a été créé et revu dans DefectDojo**.
4. DefectDojo : créer une **identité de service propre à l'import Nuclei**, autorisée à écrire uniquement dans le produit/engagement choisi ; une seconde identité **lecture seule** est préférable pour le reporting. Le jeton DefectDojo se crée côté DefectDojo, **pas via une GitHub App**. Stocker les secrets dans un coffre contrôlé, injectés seulement lors de l'exécution. Rotation, révocation, expiration et journalisation.
5. Les jobs PR depuis forks, code non approuvé ou `pull_request_target` **ne reçoivent aucun secret**. Le scan actif de production tourne sur `master` / calendrier (hors PR). Avant l'import, valider la chaîne exacte, la réponse HTTP et la liaison au produit, sans enregistrer les contenus privés.

## Protection par deux authentifications

La requête doit porter simultanément :

```bash
curl --fail-with-body --silent --show-error \
  -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}" \
  -H "Authorization: Token ${DEFECTDOJO_API_TOKEN}" \
  "${DEFECTDOJO_URL%/}/api/v2/products/"
```

Ne jamais placer le jeton DefectDojo dans un paramètre d'URL, et ne jamais désactiver la validation TLS (`-k`), ni enregistrer ces en-têtes en sortie de commandes.

**Test d'acceptation** : requête anonyme = 401/403/redirect Access, Service Token seul = 401 DefectDojo, clé DefectDojo seule = rejet Access, les deux = 200 si rôle autorisé ; toute écriture hors produit = 403. Révoquer un token doit invalider l'accès. Un HTTP 403 seul ne prouve pas la santé de l'origine.

## GitHub App et OIDC

Une GitHub App émet des **installation access tokens GitHub**, pas des `DEFECTDOJO_API_TOKEN`. Elle n'est donc pas nécessaire pour cet accès et ne doit pas recevoir un jeton administrateur DefectDojo. Si une identité sans secret statique est exigée, étudier un **broker de secrets** validant les JWT OIDC GitHub (`repository`, `ref`, `environment`, `aud`, `sub`) et échangeant cette identité contre un secret limité ; aucun broker ni rotation automatisée n'est aujourd'hui attesté.

Les deux en-têtes `CF-Access-Client-Id` / `CF-Access-Client-Secret` viennent d'un Service Token Cloudflare Access. Cloudflare recommande l'application Service Auth, et l'activation de Protect with Access ou une validation explicite à l'origine.

## Garde-fous supplémentaires

- Compte Cloudflare : API token de configuration limité (zones Access et Tunnel nécessaires), jamais le Global API Key.
- Ne pas exposer le MCP DefectDojo sur cette route. Le MCP communautaire contient des capacités d'écriture et nécessite son propre audit et cloisonnement.
- La remontée des findings vers PR se fait par **synthèse non sensible**, sous une identité GitHub lecture seule ; éviter de rendre les findings complets visibles aux PR publiques.
- Journaliser les appels Access, DefectDojo et l'origine, sans secrets et avec durée de rétention définie.
- Ne déclarer **ni DNS, ni policy Access, ni tunnel, ni secret provisionnés** avant observation de leur état réel.

## Références

- [Cloudflare Service Tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)
- [Cloudflare politiques Service Auth](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/common-policies/)
- [Cloudflare Protect with Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)
- [GitHub App installation tokens](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation)
- [DefectDojo API v2](https://docs.defectdojo.com/automation/api/api-v2-docs/)
