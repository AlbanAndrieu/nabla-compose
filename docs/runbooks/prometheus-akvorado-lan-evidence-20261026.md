# Observabilité LAN — preuve consolidée Prometheus + Akvorado

**26 octobre 2026 · PR #285 · H-05 / H-06 · lecture seule**

Ce runbook produit un instantané de diagnostic **sur TrueNAS**. Les
résultats historiques `Prometheus 21/28 UP` et `Akvorado metadata missing`
ne décrivent pas nécessairement l'état courant. Aucun traitement ne
modifie Prometheus, Akvorado, Kafka, ClickHouse, pfSense ni ses exports.

## 1. Préparer une collecte LAN

Dans le checkout canonique de TrueNAS, **après intégration du code
de la PR #285** :

```bash
cd /mnt/cpool/compose/nabla-compose

python3 -m unittest discover -s tests \
  -p 'test_collect_observability_evidence.py' -v

python3 -m pytest -q \
  tests/test_prometheus_failed_scrapes_diagnostic.py \
  tests/test_akvorado_flow_deltas.py
```

Le collecteur n'utilise que Python standard et les classificateurs
déjà versionnés. Il ne requiert ni `bw`, ni `python-dotenv`, ni
un certificat Cloudflare.

## 2. Lancer un seul rapport expurgé

```bash
cd /mnt/cpool/compose/nabla-compose

sudo python3 scripts/truenas/collect-observability-evidence.py \
  --check --scope remaining --observe-seconds 20 \
  --report-dir /mnt/cpool/var/nabla/observability
```

Équivalent si `just` est installé dans l'espace utilisateur :

```bash
just observability-evidence-lan
```

Le rapport est sauvegardé sous
`/mnt/cpool/var/nabla/observability/observability-*.json`
(mode `0600`, dossier propriétaire `0700`). Si les permissions
ne sont pas conformes ou si le chemin comporte un lien symbolique,
la sauvegarde échoue sans modifier le dossier existant.

Le JSON inclut les états et **uniquement les catégories** suivantes :

- **Prometheus** : sept jobs ciblés (`docling`, `fastapi_sample`,
  `haproxy`, `litellm_hermes`, `opensearch`,
  `opensearch-security`, `postgres_exporter`). Pour chacun :
  `scrape_up`, `scrape_down`, `scrape_partial`,
  `scrape_unverified` ou `no_active_target`, nombres de cibles
  et domaines `auth/http/tcp/dns/tls/timeout/network/unverified`.
- **Akvorado Inlet** : présence d'au moins un compteur reconnu.
- **Akvorado Outlet** : différence de compteurs sur 20 secondes :
  flux reçus, erreurs `metadata missing`, Kafka, lots ClickHouse.
  Un ancien compteur non nul ne signifie pas qu'une erreur persiste.
- **SQL** : toujours `NOT_VERIFIED` ; une hausse de lots métriques
  ne confirme pas les lignes ClickHouse effectivement persistées.

Interprétation de la sortie de la commande :

| Code | Verdict | Conduite |
| --- | --- | --- |
| `0` | `PASS` | Tous les contrôles instrumentés pris en compte sont concluants ; SQL métier non démontré si indiqué séparément |
| `1` | `FAIL` | Au moins un scrape explicitement DOWN/partial ou un rejet actif de métadonnées |
| `2` | `UNVERIFIED` | Observations absentes, inconnues, incomplètes ou non concluantes ; ne pas déclarer un service DOWN |

Les limites sont intentionnelles : maximum 1 Mio JSON Prometheus,
2 Mio par endpoint Akvorado, timeout 5 s et observation 1–60 s.
Pas de redirection HTTP, pas de proxy, pas de raw `lastError`,
labels de métriques, URL de scrape, credential ou adresse de flux
dans le JSON. Le code de sortie peut être non nul **tout en ayant
créé le rapport** : ne pas le masquer avant lecture.

## 3. Diagnostic ciblé Prometheus (H-05)

Si `prometheus.status=FAIL`, commencer par :

```bash
python3 scripts/prometheus/diagnose-failed-scrapes.py \
  --check --scope remaining

sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
```

Le `401` de `fastapi_sample` est une question d'authentification
de `/metrics` et non une preuve d'arrêt FastAPI. Un refus TCP de
`postgres_exporter:9187` ne signifie pas que PostgreSQL sur
`:5432` est arrêté. Ne pas imprimer le jeton ni le DSN.

## 4. Diagnostic ciblé Akvorado (H-06)

Si `akvorado.observation=BLOCKED_METADATA_MISSING`,
`PARTIAL_METADATA_REJECTIONS` ou
`METADATA_REJECTIONS_INSERTS_UNVERIFIED` :

```bash
sudo bash scripts/truenas/diagnose-akvorado-config.sh --check

python3 scripts/truenas/check-akvorado-metadata-config.py --check

python3 scripts/truenas/diagnose-akvorado-flow.py \
  --strict --fail-on-blocked --observe-seconds 30
```

Le mapping actuel est **déclaratif** pour l'exporter pfSense
`172.17.0.1/32` et `ifIndex=11`. Il faut vérifier que la
configuration est bien chargée par le conteneur Outlet. Ne pas
élargir la collecte pflow sur le Netgate 1100 ni augmenter sa
pression mémoire pour déclencher artificiellement un flux.

Pour chercher une progression de lots uniquement :

```bash
python3 scripts/truenas/diagnose-akvorado-flow.py \
  --strict --require-inserts --observe-seconds 30
```

**Attention :** ce dernier contrôle confirme au mieux une **activité
de lots**, pas des insertions SQL datées. Une validation E2E supplémentaire
exige un compte ClickHouse **read-only** limité à `akvorado`,
la découverte du schéma effectif, la comparaison de nouvelles lignes
et la visualisation dans la Console. Aucune requête SQL brute ou donnée
de flux n'est envoyée dans ce rapport.

## 5. Vérification depuis la workstation (LAN autorisé)

Si le checkout existe sur la workstation et peut joindre
`172.17.0.24`, la commande de collecte peut être exécutée sans
`sudo` et sans sauvegarde :

```bash
cd ~/w/nabla-compose
python3 scripts/truenas/collect-observability-evidence.py \
  --check --scope remaining --observe-seconds 20
```

La comparaison TrueNAS/workstation différencie un défaut de chemin
LAN d'un problème serveur. Pour un rapport reproductible, conserver
les deux JSON expurgés **hors Git** avec leurs timestamps.
Il n'est pas nécessaire d'appeler directement pfSense ni de forcer
des mises à jour DNSBL/Snort.

## 6. Conditions de clôture

- Prometheus : classifier les sept cibles d'après les dernières
  preuves, corriger seulement l'exporter ou l'autorisation concernée,
  puis observer le scrape à nouveau.
- Akvorado : compter une hausse des flux récents sans nouveaux rejets
  de métadonnées, confirmer les lots puis les **lignes SQL récentes**
  avec une identité de consultation. Si aucune donnée ne circule durant
  la fenêtre de 20 secondes, l'état reste `UNVERIFIED`.
- Ne jamais interpréter un `docker running`, un HTTP 200 métriques,
  un PASS de code ou un lot ClickHouse comme une disponibilité métier
  complète.
