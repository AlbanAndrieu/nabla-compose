# LiteLLM — audit différé des coûts, budgets et observabilité (2026-10-11)

**Statut : planifié ; aucune modification des plafonds ni des secrets.**
**Ordre de priorité :** P0 stabilisation OpenClaw/heartbeat et vérification de `openclaw-cron`; P2 audit des coûts transversal; n8n est hors de l'intégration OpenClaw à ce stade.

## Périmètre et état observé

- Workstation `http://127.0.0.1:4000` : endpoints liveliness/readiness HTTP 200, admin `/key/info` accessible dans le shell de l'opérateur avec `LITELLM_MASTER_KEY`.
- TrueNAS `http://172.17.0.24:4000` : liveliness/readiness HTTP 200; application TrueNAS `litellm` RUNNING, conteneur healthy; aucune preuve actuelle de fonctionnement du chemin authentifié complet TrueNAS → workstation.
- Audits workstation fournis le 11/10/2026, instantané non temps réel :

| Identité | Dépense / budget | TPM | RPM | Fenêtre | Prochaine remise à zéro (UTC) |
| --- | --- | --- | --- | --- | --- |
| `openclaw-main` | 4.459116 / 10 | 200000 | 30 | 7d | 2026-10-12T00:00:00Z |
| `openclaw` | 0.2091128 / 2 | 100000 | 10 | non reportée | non reportée |
| `ide` | 0 / 100 | 1500000 | 300 | 7d | 2026-10-12T00:00:00Z |
| `n8n` | 0 / non reporté | non reporté | non reporté | non reportée | non reportée |
| `openclaw-cron` | **non audité** | **non audité** | **non audité** | **non audité** | **non audité** |

Les unités `spend/max_budget` sont celles de LiteLLM, normalement USD si le proxy est correctement configuré. Une valeur absente ne prouve **ni zéro ni illimité**. `TPM=200000` signifie tokens/minute et ne correspond pas à une fenêtre contextuelle de 200k. Ne pas additionner aveuglément les dépenses des proxys en cascade : une même requête peut être comptabilisée deux fois.

## P0 — Stabiliser OpenClaw et auditer la route cron

- [ ] Vérifier via `openclaw models status` et les métadonnées de route (sans afficher les clés) que le cron isolé utilise réellement `litellm-cron/gpt-4.1-mini`, avec sa **propre clé virtuelle** et le budget déclaré par l'opérateur à 2 ; ne jamais le basculer vers `litellm-main` automatiquement.
- [ ] Recueillir l'**ID haché** de la clé virtuelle `openclaw-cron` de manière sécurisée/localement pour `/key/info` ; ne pas inventer un ID ni enregistrer une valeur secrète ou un préfixe de token dans le dépôt.
- [ ] Auditer `spend/max_budget/tpm_limit/rpm_limit/budget_duration/budget_reset_at`, le rattachement équipe/modèle et la réinitialisation. Contrôler que la liste de modèles de la clé autorise le modèle cron attendu.
- [ ] Confirmer un smoke de conversation principale **déjà réussi** avec `litellm-main/gpt-4.1` (`OK`), tout en conservant la limite manuelle d'un test facturable toutes les 24 heures.
- [ ] Diagnostiquer les heartbeats `main` en échec consécutif autour de 68 secondes avec le journal applicatif, contexte/session et routage effectif, sans compacter ni effacer l'historique, augmenter les budgets ou redémarrer des services.
- [ ] Vérifier la séparation de la clé virtuelle `openclaw` préexistante et de `openclaw-main` pour éviter toute confusion de coûts.

## P2 — Audit consolidé des coûts LLM (plus tard)

- [ ] Relever les limites réellement effectives : clé, utilisateur, équipe, modèle, fournisseur, budget global, reset/expiration et limitations héritées.
- [ ] Comparer coûts par modèle, requêtes, tokens et erreurs 401/429 entre workstation et TrueNAS, **sans double comptage** ; choisir un étage de facturation faisant autorité, l'autre restant garde-fou technique.
- [ ] Auditer les fallbacks (`gpt-4.1` → `gpt-4o` → `gpt-4.1-mini`) : compatibilité fonctionnelle, coûts, retry/timeout, sécurité et idempotence.
- [ ] Vérifier les tarifs Azure, OpenAI et modèles personnalisés, la tarification effective, les prix nuls et les journaux de dépenses.
- [ ] Examiner `apps/litellm/config.yaml` : `store_prompts_in_spend_logs: true`, `turn_off_message_logging: false`, headers utilisateur transférés et callbacks `langfuse_otel` ; décider explicitement des minimisations, durées de rétention et protections de l'historique des prompts/mémoire OpenClaw.
- [ ] Évaluer `ide` à 100/7d à partir de consommation réelle avant de diminuer ou augmenter les plafonds.
- [ ] Auditer les limites de `n8n` séparément **après son adoption**, aucune action n8n ne bloque P0 OpenClaw.
- [ ] Définir des alertes de consommation 50/80/95 %, dérive de dépense, budget expiré et erreurs 429 ; éviter un modèle payant pour envoyer ces alertes.
- [ ] Vérifier la configuration TrueNAS déployée (fichier et DB `store_model_in_db: true`) et sa divergence possible avec le YAML Git, puis seulement valider le transfert de trafic.

## Prometheus / Grafana — état et tâches

Le dépôt TrueNAS contient **déjà** `callbacks: [langfuse_otel, prometheus]` et `prometheus_initialize_budget_metrics: true` dans `apps/litellm/config.yaml`. Le Compose déclare le lien de télémétrie vers Prometheus. **Ces déclarations ne prouvent ni un scrape Prometheus actif, ni la présence de métriques de coût utilisables.** Aucun accès direct au Prometheus LAN n'est disponible depuis la connexion GitHub.

- [ ] Depuis workstation/TrueNAS, vérifier `/metrics` avec une authentification adéquate sans exposer des séries porteuses de clés/tokens et confirmer la découverte et l'état `up` dans Prometheus (adapter les noms de séries à la version effective).
- [ ] Contrôler les séries LiteLLM de dépenses, tokens, budget restant, erreurs, latence, modèle et proxy; ne pas inventer de métriques absentes.
- [ ] Vérifier labels, cardinalité et confidentialité; ne pas faire de `key_id` exposé une étiquette publique.
- [ ] Concevoir un dashboard Grafana « LLM Cost & Reliability » avec séparation des deux proxys et déduplication explicite.
- [ ] Définir les alertes seulement après validation du scrape, du reset des budgets et de la provenance des coûts.

## Procédure actuelle en lecture seule

```bash
bash scripts/workstation/openclaw-ops.sh --litellm-audit
bash scripts/workstation/openclaw-ops.sh --heartbeat
bash scripts/workstation/openclaw-ops.sh --recent-errors
```

La clé maître workstation ne doit jamais être expédiée à TrueNAS en HTTP, même à seule fin d'audit. Les clés virtuelles et les identifiants fournisseur originaux restent côté workstation. L'audit doit échouer en « non vérifié » plutôt qu'en « OK » pour les données indisponibles.

## CI liée à la PR #253

- Gate locale pre-commit : échec ShellCheck `SC2174` sur `mkdir -p -m 700` dans `openclaw-ops.sh`; corriger la commande, conserver chmod explicite, puis valider localement.
- `Production Security` : `/health` et `/v2/version` ont répondu HTTP 404 sur le déploiement `fastapi-sample.fastapicloud.dev` (11/10/2026), hors du runtime LiteLLM. Le contrôle doit rester **bloquant**; investiguer le contrat applicatif, le routage, la version en production ou un déploiement temporaire, **sans soft-fail ni désactivation de la vérification**.
- Réexécuter les tests locaux avant d'envisager une CI hébergée, afin de limiter les crédits GitHub Actions.
