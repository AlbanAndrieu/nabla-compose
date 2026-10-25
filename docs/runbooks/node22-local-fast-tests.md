# Tests locaux rapides — Node 22 / npm 10

**Mode de compatibilité opt-in**, sans GitHub Actions et sans installation
de dépendances. Node 24 reste la version canonique du dépôt
(`.nvmrc`, `mise.toml`). Ce mode ne modifie ni les lockfiles,
ni `node_modules`, ni le système TrueNAS.

## Exécution

Sur une workstation disposant de **Node 22.x et npm 10.x** :

1. Vérifier les versions avec `node --version` et `npm --version`.
2. Exécuter une seule commande dans un worktree isolé :

```bash
just node22-fast
```

Si `just` est absent, utiliser directement :

```bash
npm --offline run test:fast:node22
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
