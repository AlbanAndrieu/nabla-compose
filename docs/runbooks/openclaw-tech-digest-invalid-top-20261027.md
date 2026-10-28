# OpenClaw — échec daily-tech-news-digest (--top 3-5), 27 octobre 2026

## Symptôme confirmé

La tâche `daily-tech-news-digest` de 09:00 Europe/Paris annonce une
livraison mais transmet un résumé d'erreur après 1 min 34 s :
`summarize-merged.py` refuse `--top 3-5`. L'argument `--top`
attend **un entier**, pas un intervalle. La valeur à utiliser
pour « 3 à 5 articles » est **`--top 5`**. Le statut
`delivered` mesure le transport, **pas** la génération du résumé.

La panne du digest n'est pas une preuve du `API rate limit reached`
affiché dans le chat `main` : incidents à instruire séparément.

## Cause racine : intégration incompatible dans le skill v3.16.0

Le code public officiel du tag `v3.16.0` confirme la contradiction :

- `SKILL.md` propose `ITEMS_PER_SECTION = 3-5` pour le digest quotidien.
- `references/digest-prompt.md` contient
  `summarize-merged.py --top <ITEMS_PER_SECTION>`.
- `scripts/summarize-merged.py` définit `--top` en `type=int`.

Le placeholder éditorial `3-5` devient donc un argument CLI invalide.
**Notre recommandation précédente d'ajouter `--top 5` au cron
était insuffisante** : elle dupliquait une règle déjà gérée par le
template du skill et ne supprimait pas l'instruction source.

L'installation locale n'a pas encore été identifiée par son hash de
template. Le tag `v3.16.0` est une cause **confirmée dans le code
public**, pas une preuve que ce tag précis est celui du poste.
La branche principale actuelle de draco-agent/tech-news-digest utilise
`--top 30` pour le résumé intermédiaire et traite
`ITEMS_PER_SECTION` comme paramètre indicatif historique.
Ne pas assimiler une branche principale non épinglée à une version
ClawHub installée ou approuvée.

Sources :
- https://github.com/draco-agent/tech-news-digest/blob/v3.16.0/SKILL.md
- https://github.com/draco-agent/tech-news-digest/blob/v3.16.0/references/digest-prompt.md
- https://github.com/draco-agent/tech-news-digest/blob/v3.16.0/scripts/summarize-merged.py

## Preuves Workstation et nouveau contrôle (PR #289)

```bash
just openclaw-digest-top-test
just openclaw-digest-top-check
```

La Workstation a validé **8/8**, puis **10/10 tests** sur les
versions successives. Dernier contrôle avant ce durcissement :
`cron_job_read=structured`,
`digest_top_argument=multiple_top_arguments`, `exit=2`.
Le cron récent contenait deux mentions explicatives de `--top 5`,
ce qui a créé un **faux positif** du premier diagnostic. Ni une
double invocation du script ni un 429 ne sont démontrés.

Le nouveau contrôle lit en lecture seule le job connu par
`openclaw cron get` et le fichier local fixe
`~/.openclaw/workspace/skills/tech-news-digest/references/digest-prompt.md`
avec vérifications propriétaire/type/mode/taille. Aucun prompt, clé,
destinataire ou template brut n'est imprimé. Aucune requête de modèle,
exécution cron, modification runtime ou redémarrage n'est faite.

Les nouveaux codes de diagnostic :
- `skill_template_range_int_mismatch` : template local transmet
  `<ITEMS_PER_SECTION>` à `--top` alors que la valeur cron est
  une plage ; **sortie 2 attendue**.
- `skill_template_integer_valid` : template local utilise le
  placeholder avec une valeur entière ; validation statique OK.
- `skill_template_fixed_integer` : template local emploie un entier
  explicite indépendant de la plage ; validation statique OK.
- `skill_template_unavailable` : template absent ou lecture refusée ;
  ne pas supposer une version du skill.
- `skill_template_top_unverified` : politique inconnue ; fail closed.

La suite Python a été portée à **16 tests** ; cette nouvelle suite
n'est **pas encore attestée exécutée sur la Workstation**.

## Correction du digest sans toucher au Gateway

**Solution immédiate sans modifier le skill installé (v3.16.0) :**
dans l'interface OpenClaw, conserver le prompt officiel et modifier
uniquement `ITEMS_PER_SECTION = 3-5` en
`ITEMS_PER_SECTION = 5`. Supprimer les paragraphes supplémentaires
introduits pour imposer `--top 5` : la source de vérité redevient
`digest-prompt.md`. Inconvénient : cette version aura une valeur
fixe de 5 éléments par rubrique plutôt qu'une plage flexible.
Conserver toutes les autres variables et la destination.

**Solution durable pour conserver la plage éditoriale 3–5 :**
corriger le template versionné du skill pour utiliser un entier
distinct (p. ex. `--top 5` ou un nombre de candidats de récupération
plus large) tout en laissant `ITEMS_PER_SECTION = 3-5` dans le cron.
Préparer ce correctif dans la gestion déclarative de la Workstation ;
une édition locale non versionnée peut être écrasée lors d'une
mise à jour. Examiner préalablement l'édition et les changements
de version du skill ; pas de mise à jour automatique.

La commande de validation statique doit passer avant toute nouvelle
exécution programmée, mais **ne garantit pas** le succès éditorial,
l'accès aux sources, ni la livraison. Ne pas forcer `cron run`,
modifier SQLite, augmenter les budgets, changer les clés ou redémarrer
le Gateway pour cette erreur.

**Chat `main` séparé :** une réponse à « Hello » reprenant un
ancien transcript peut provenir du contexte de session conservé.
Depuis le chat, utiliser `/new` (message isolé) pour ouvrir une
session fraîche en archivant l'ancienne ; ne pas appeler
`openclaw reset` ni effacer la base SQLite. Ce test peut entraîner
une inférence au message suivant, pas à l'envoi de `/new` lui-même.

## Constat réseau LiteLLM (hors cause directe du digest)

Deux hôtes écoutent sur le port 4000. Le premier relevé montre le
bridge `172.16.7.1` nommé `br-7dc38b42b21c` avec un
`dockerd` sur `0.0.0.0:4000`. Le second montre un
`docker-proxy` sur IPv4 et IPv6. **Si** les relevés ont été
faits dans l'ordre Workstation puis TrueNAS, `172.16.7.1`
est l'adresse de bridge Workstation et explique que certaines
requêtes `openclaw-main` apparaissent sous cette adresse, pas
sous `172.17.0.57`. Le bridge et le NAT masquent parfois
l'adresse d'origine.

Les deux traces distinctes `openclaw-main` du 27 octobre
consomment 577 et 569 tokens, ont un alias `openclaw-main`
et aucune `error_information`, mais un `status=null`.
Le refus `No api key passed in.` avec `user_api_key=null`,
`total_tokens=0` et origine `172.17.0.24` n'est **pas**
une preuve du 429 et ne permet pas d'identifier l'appelant.

## Critère DONE

- La paire **paramètre cron + template installé** ne substitue
  jamais une plage à un argument CLI entier.
- Les contrats `openclaw-digest-top-test` passent localement.
- Une exécution **planifiée ultérieure** génère un vrai résumé,
  avec sources et statut de traitement, et le livre.
- L'absence de 429 pour le chat `main` reste un **autre** critère.

Références : https://docs.openclaw.ai/cli/cron et
https://docs.openclaw.ai/tools/slash-commands
