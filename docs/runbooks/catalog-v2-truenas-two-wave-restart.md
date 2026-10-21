# Catalog v2 — préparation TrueNAS en deux vagues

**Lecture seule : aucune application n'est redémarrée par ce plan.**

L'identité est tirée de Backstage, le binding Compose/Gatus du fichier **généré**
`catalog/generated/identity-map.json`. L'état RUNNING vient uniquement d'un
snapshot récent `midclt call app.query`, jamais de labels ou de Git.
Les identités non mappées sont visibles, pas inventées.

## Capturer l'état du TrueNAS (opérateur)

Sur TrueNAS :

```bash
umask 077
sudo midclt call app.query > /tmp/nabla-truenas-app-query.json
python3 scripts/truenas/plan-catalog-v2-restart.py \
  --apps-json /tmp/nabla-truenas-app-query.json \
  --runtime-root / \
  --output /tmp/nabla-catalog-v2-restart-plan.json
```

Le résultat contient **waveRunning** (services actuellement RUNNING),
**waveOther** (STOPPED/CRASHED/UNKNOWN, à traiter ensuite) et **blocked**.
Aucune modification d'état n'est effectuée. Les valeurs de secrets et le
`BW_SESSION` ne sont jamais lus. Le champ `vaultwardenItemVerified=false`
signifie qu'un item du manifeste n'a **pas** été vérifié réellement dans
Vaultwarden ; un fichier présent sur disque ne prouve pas que ses clés sont
à jour ni utilisables.

## Ordonnancement avant toute relance réelle

1. Relever les applications `RUNNING` juste avant l'intervention et figer la
   liste : elles forment **la première vague**, prioritaire pour l'exploitation.
2. Dans cette vague, respecter `spec.dependsOn` Backstage, puis
   `depends_on` Compose pour l'ordre au sein d'un projet. Une ressource
   PostgreSQL/Kafka/ClickHouse ne doit pas être réinitialisée parce qu'un
   consommateur la mentionne. Identifier les dépendances manquantes.
3. Pour les applications dotées d'un item dans `config/secrets/manifest.json`,
   exécuter sous **compte non-root** `scripts/secrets/materialize_runtime.py
   --app <id> --verify`, puis confirmer les permissions (0600) et que les
   variables requises sont disponibles sans afficher leurs valeurs.
4. Vérifier après chaque application les états `app.query`, le healthcheck
   Docker, Gatus/Prometheus si disponibles et les journaux applicatifs
   expurgés. Une sonde négative seule ne prouve pas que le service est DOWN.
5. **Deuxième vague** : traiter les applications qui n'étaient pas RUNNING
   séparément, y compris `planned`, `disabled` et `CRASHED`. Ne pas
   démarrer aveuglément les profils manuels ni les services intentionnellement
   désactivés ; leur activation nécessite un changement explicite d'intention.

Aucune dépendance Catalog v1 n'est introduite dans ce plan. Ce n'est pas un
script de redémarrage : l'activation doit passer par les contrôleurs et
scripts TrueNAS existants après résolution des dépendances et des secrets.
