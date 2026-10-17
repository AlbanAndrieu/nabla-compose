# OpenClaw / LiteLLM HTTP 429 — attribution hors ligne

## Constats (16–17 octobre 2026)

- Les HTTP 429 sur `POST /v1/chat/completions` ont été observés le 16 octobre entre 00:09–00:13 et 01:13–01:18 Europe/Paris (22:09–22:13 et 23:13–23:18 UTC le 15).
- Les 20 dernières exécutions fournies du job `heartbeat-main` (`bb9757db-9559-4960-bb23-9b9770929ff1`) échouent en `agent-runner-failure` le 16–17 octobre, avec environ 250–302 s de durée, mais ces exécutions **ne couvrent pas** les rafales du 16 octobre vers 00:09. Ne pas attribuer les 429 au heartbeat sur cette seule base.
- `openclaw-ops.sh --cron` rapporte le digest (`daily-tech-news-digest`), **pas** le heartbeat. Utiliser `--heartbeat` pour ce dernier.
- `--recent-errors` ne cherche que dans une fenêtre glissante de 30 min du journal du jour ; zéro événement n'invalide pas les 429 historiques.
- Les 429 LiteLLM sont des réponses proxy ; leur origine exacte (limite virtuelle RPM/TPM, budget, upstream Anthropic, autres) reste à qualifier via traces structurées.
- Un chevauchement temporel prouve uniquement que le job était actif pendant les refus ; il ne démontre pas que les appels proviennent du job.

## Audit sans requêtes facturables

Depuis le poste (ne pas copier de texte de prompt ou de secrets vers un ticket) :

```bash
openclaw cron runs --id bb9757db-9559-4960-bb23-9b9770929ff1 --limit 100 > /tmp/openclaw-heartbeat-runs.json
docker logs --timestamps --since '2026-10-16T00:00:00+02:00' --until '2026-10-16T01:25:00+02:00' litellm-litellm-1 2>&1 > /tmp/openclaw-litellm-audit.log
python3 scripts/workstation/openclaw-rate-limit-correlation.py --cron-json /tmp/openclaw-heartbeat-runs.json --litellm-log /tmp/openclaw-litellm-audit.log
```

Fichiers temporaires : permissions restrictives recommandées (`umask 077`), purger après enquête. Le programme ne restitue que des compteurs, des horaires et l'étiquette `temporal_overlap_only_not_proof_of_caller`. Les exports source restent potentiellement sensibles et ne doivent pas être publiés.

Pour remonter au véritable appelant : corréler au niveau LiteLLM le `request_id`, le hash de clé virtuelle, le modèle, le motif 429 (budget/RPM/TPM/upstream) avec les `agent_id`, `session_id` et `cron_job_id` OpenClaw, en journalisation structurée **sans prompts ni valeurs de clés**. Une IP Docker NAT comme `172.16.7.1` ne constitue pas une identité d'appelant fiable.

Ne pas augmenter les budgets ni les limites, ne pas redémarrer les agents, ne pas supprimer les sessions, ne pas lancer de smoke facturable pour obtenir cette preuve.
