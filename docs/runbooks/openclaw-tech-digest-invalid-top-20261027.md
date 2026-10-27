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

## Préflight en lecture seule (PR #289)

Depuis la Workstation, sur une copie à jour de la branche #289 :

```bash
just openclaw-digest-top-test
just openclaw-digest-top-check
```

Le premier gate exécute des contrats synthétiques hors ligne.
Le second consulte le **seul** job connu
`7ed5dd9a-da30-479f-b0eb-4cc494fb4966` par
`openclaw cron get <id>` via l'installation Node/OpenClaw 24.22.1.
Il ne publie ni texte du prompt, ni secrets, ni destinataires, ni
sortie brute. Il refuse un ID ou un nom de job différent.
Un code de sortie 2 signifie que l'argument reste invalide, absent
ou que l'état runtime n'est pas vérifiable. Il **ne modifie pas** le job.

États attendus : `invalid_top_range` si le prompt contient
littéralement `--top 3-5`, `valid_top_five` s'il contient
`--top 5`, `no_explicit_top_argument` si la plage est formulée
seulement en langage naturel. Une instruction en langage naturel
(« top 3-5 ») peut produire la même erreur sans être détectée comme
argument littéral ; le préflight ne prétend pas auditer les décisions
du modèle.

## Correction minimale du job existant

Dans **OpenClaw → Automations / Cron → daily-tech-news-digest → Edit** :

1. Conserver la cadence, le fuseau, le modèle `litellm-cron/gpt-4.1-mini`
   et la destination de livraison.
2. Dans **les instructions de la tâche**, remplacer toute commande
   `summarize-merged.py --top 3-5` par
   `summarize-merged.py --top 5`.
3. Ajouter une contrainte explicite : « `--top` accepte seulement
   un entier. Utiliser `--top 5`. Ne jamais transmettre `3-5`.
   Si la génération échoue, signaler l'erreur et ne pas présenter
   un résumé vide comme une réussite. »
4. Enregistrer uniquement les instructions, puis exécuter
   `just openclaw-digest-top-check` de nouveau.

La CLI OpenClaw documente `cron get <job-id>` et
`cron edit <job-id> --message`, mais ce dernier peut exposer
le prompt complet dans les arguments du processus. Préférer la
modification depuis l'interface locale sécurisée, sans recopier le
texte privé dans les logs, un ticket ou le terminal.

**Ne pas** modifier directement SQLite, lancer `cron run`,
relancer l'inférence, redémarrer le Gateway, changer les clés
virtuelles LiteLLM ou augmenter les budgets pour ce symptôme.

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

- La définition runtime de `daily-tech-news-digest` contient
  un `--top` entier explicite (cible 5).
- Les contrats `openclaw-digest-top-test` passent localement.
- Une exécution **planifiée ultérieure** génère un vrai résumé,
  avec sources et statut de traitement, et le livre.
- L'absence de 429 pour le chat `main` reste un **autre** critère.

Référence CLI : https://docs.openclaw.ai/cli/cron
