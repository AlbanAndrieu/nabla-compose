# daily-tech-news-digest — message déclaratif (sans secrets)

Exécute le skill installé `tech-news-digest` avec sa référence
`references/digest-prompt.md` et les paramètres explicites suivants :

- MODE = daily
- TIME_WINDOW = past 1-2 days
- FRESHNESS = pd
- RSS_HOURS = 48
- ITEMS_PER_SECTION = 5
- ENRICH = true
- BLOG_PICKS_COUNT = 3
- LANGUAGE = French
- TEMPLATE = discord

IMPORTANT : `ITEMS_PER_SECTION` est un nombre entier, pas une plage.
Quand le template invoque `summarize-merged.py`, utiliser exactement
`--top 5` (et jamais `--top 3-5`).

Ne modifie ni les destinataires, ni les clés, ni la destination Discord :
ces réglages restent exclusivement dans les champs de livraison privés
de l'automation existante. N'invente pas une réussite d'envoi sans preuve
de sortie validée. Respecte le budget, les cooldowns et la politique
de retry du job ; ne relance pas automatiquement en cas de 429.
