# Tests locaux rapides — Node 22 / npm 10

**Mode de compatibilité opt-in**, sans GitHub Actions et sans installation
de dépendances. Node 24 reste la version canonique du dépôt
(`.nvmrc`, `mise.toml`). Ce mode ne modifie ni les lockfiles,
ni `node_modules`, ni le système TrueNAS.

## Exécution

Sur une workstation disposant de **Node 22.x et npm 10.x** :

1. Verifier l'installation existante via `mise where node@22`.
   Si la version manque, la recette s'arrete sans installer
   automatiquement Node.
2. Lancer la commande : `just` selectionne **Node 22**
   avec `mise exec node@22` meme si la version canonique est Node 24 :

```bash
just node22-fast
```

Si `just` est absent, utiliser directement :

```bash
node_root="$(mise where node@22)"
PATH="$node_root/bin:$PATH" "$node_root/bin/node" \
  "$node_root/lib/node_modules/npm/bin/npm-cli.js" \
  --offline run test:fast:node22
```

Les tests sont implémentés avec `node:test` et `node:assert/strict`,
sans paquet tiers. **Ne pas lancer `npm ci`, `npm install` ou `npx`**
pour ce mode : un simple contrôle statique ne justifie aucun accès réseau.
Le test vérifie également le major de npm. Les versions différentes de
Node 22 et npm 10 provoquent un échec explicite.

## Couverture

- Contrat déclaratif APISIX : nom `apisix`, profil, identité `x-nabla`,
  pas de port publié, réseau isolé, absence de routage Traefik.
- Route APISIX interne, clé lue depuis l'environnement, quota,
  Admin API désactivée et fin de configuration `#END`.
- Syntaxe `bash -n` des opérateurs APISIX et de migration ;
  **ces scripts ne sont pas exécutés en mode mutateur**.
- Présence des sections `postmigration` et `apisix`,
  refus des modes CLI combinés et état `UNVERIFIED`.
- Recettes `just` explicitement opt-in.

## Preuves collectées le 25 octobre 2026

Environnement agent vérifié : Node `v22.16.0`, npm `10.9.2`.
Le fichier `scripts/quality/node22-fast.test.mjs` exécuté localement
était identique au blob Git publié au moment de ce test.
Depuis, la suite Node inclut la syntaxe du script de triage critique :
**le HEAD actuel n'a pas été retesté sur un checkout intégral**.

- **6/6 PASS (ancienne révision du test)** : suite Node sur un espace de travail isolé contenant
  les fichiers APISIX récupérés par blob Git et des substituts pour les
  autres fichiers de migration (l'environnement agent n'a pas pu cloner
  le dépôt complet).
- **Cas négatif PASS** : remplacer `name: apisix` par
  `name: apisix-poc` produit un échec avec `exit=1`, puis le fichier
  est restauré à son empreinte d'origine.
- **10/10 PASS** : tests Python `tests/test_apisix_contract.py`
  exécutés sur des copies **identiques par blob SHA** du script, des
  configurations APISIX et du test de la PR.

**Limites :** le mode Node ne remplace pas `pytest` complet,
ShellCheck, `just quality`, l'analyse des secrets, le smoke Docker
ni l'acceptation runtime sur TrueNAS. Ces gates restent **NOT_RUN** sur
le dépôt complet tant que les outils et le HEAD exact ne sont pas
disponibles dans un checkout accessible. Les tests Node sur les fichiers
de migration ont utilisé des substituts, pas le runtime réel.

## Extension du 25 octobre — sept gates critiques

La suite rapide vérifie aussi la syntaxe de
`scripts/truenas/triage-critical-failures.sh`. Le test complet de la
PR actuelle, incluant la révision des diagnostics OpenRAG, reste
**NOT_RUN**. Exécuter `just node22-fast` sur le HEAD exact avant fusion.

## Releve utilisateur du 25 octobre 2026

`just migration-recovery-contracts` : **12 tests PASS**.
`just node22-fast` : **5 PASS / 1 FAIL**, le test de version a
identifie `24 !== 22`. Les cinq autres contrats sont passes.
La recette a ete corrigee pour selectionner la version Node 22
explicitement. **Retester sur le HEAD actuel** ; cette modification
n'est pas encore validee par une nouvelle execution.
`just quality` reste NON EXECUTE.

## Correctif de résolution npm 12 (25 octobre 2026)

Le nouvel essai de l'operateur sous Node 22 a echoue car la commande
`npm` resolvait **npm 12**. `mise exec node@22 -- npm` ne
garantissait pas la provenance du CLI npm. La recette `just node22-fast`
resout maintenant le repertoire via `mise where node@22`, puis lance
`bin/node` et `lib/node_modules/npm/bin/npm-cli.js` depuis cette
**meme installation**. Elle refuse toute version autre que Node 22 /
npm 10 et tout npm manquant, sans installer de dependance.

Un test local isole a reussi avec un faux npm 12 prioritaire dans
`PATH`, mais **la suite 6/6 du HEAD GitHub actuel reste a lancer**.

## Dernier test opérateur : Node22/npm10 PASS, assertion à corriger

Le relevé du 25 octobre montre que Node22/npm10 sont maintenant
sélectionnés correctement : le premier test de compatibilité est
**PASS**, ainsi que les tests APISIX et diagnostics shell. Le
`just node22-fast` s'est arrêté à **5 PASS / 1 FAIL** uniquement sur
l'assertion qui attendait l'ancien texte
`npm --offline run test:fast:node22` dans `justfile`.
La nouvelle recette exécute explicitement le chemin
`npm-cli.js --offline run test:fast:node22`. Le test de contrat
vérifie désormais **le CLI lié au Node22 installé, le mode offline
et l'absence de commande d'installation**, sans exiger le texte
obsolète. **6/6 au dernier HEAD reste NON EXÉCUTÉ**.
