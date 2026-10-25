# TrueNAS — opérateur de migration (procédure courante)

> Mis à jour le 25 octobre 2026 · `nabla-compose` · **aucune mutation
> par défaut**. Cet index remplace les liens directs vers un script daté,
> mais n'efface ni les anciens rapports ni les règles de sécurité.
>
> [Roadmap active](../roadmap.md) ·
> [Critères d'acceptation runtime](homelab-runtime-acceptance.md) ·
> [Plan des vagues historique](2026-10-24-truenas-migration-acceptance.md).

## Contrat de la CLI

| Entrée | Effet autorisé | Préconditions |
| --- | --- | --- |
| `--help` | Aucune connexion ni rapport | Aucun outil TrueNAS |
| `--next-commands` | Affiche un chemin de runbook | Aucun état runtime requis |
| `--check --section ...` | Lance des diagnostics ; écrit un rapport privé | Exécuter depuis une révision revue, `midclt` sur TrueNAS |
| `--plan-wave core\|gatus\|deferred` | Lit le catalogue, produit un plan privé et un hash | Vérifier les sources live, ne pas révéler les JSON |
| `--apply-wave ...` | Redémarre une vague via le planificateur existant | **`master` propre**, checkout canonique, root, hash frais et acknowledgement exact |
| `--apply-step ...` | Migration d'un secret ou de Gatus selon une allowlist | Même origine protégée, confirmation exacte et `--check` préalable |
| `--apply-csi-smoke` | Smoke CSI susceptible de créer/effacer des ressources de test | Approbation explicite, kubeconfig autorisé, rollback de l'environnement de test |
| `--local-gates` | Exécute la chaîne qualité locale dans le processus enfant | Worktree non-root, `just` disponible |

Les modes `--check`, `--plan-wave`, `--apply-wave`, `--apply-step`,
`--apply-csi-smoke`, `--next-commands` et `--local-gates`
sont **mutuellement exclusifs**. Une répétition ou un mélange de modes
retourne `exit=2` avant création de rapport. L'absence de mode
équivaut à `--check --section all`.

Les détails sensibles, notamment `selectedWaveBlocker`, restent dans les
rapports privés. La sortie publique contient seulement une catégorie
constante, les états PASS/FAIL, les comptages et le `planHash` opaque.
Ne jamais transmettre les JSON du plan ou les fichiers de secrets.

## Exécution recommandée en lecture seule

Sur TrueNAS, depuis un checkout déjà validé :

1. Contrôler le chemin Git et les modifications locales.
2. Lire la version et la politique du script.
3. Lancer une seule collecte ciblée :

```bash
sudo bash scripts/truenas/migration-operator.sh --check --section critical
```

4. Consulter `summary.tsv` dans le répertoire privé affiché par la CLI.
5. Diagnostiquer **une seule famille** en défaut ; ne pas redémarrer les
   familles déjà acceptées sans nouvel indice.
6. Épingler le SHA de code et la date du résultat dans le rapport d'incident.

Le dernier relevé fourni par l'opérateur donne **`PASS=9 FAIL=7`**
([reprise ciblée du 25 octobre](2026-10-25-critical-acceptance-followup.md)) :
Prometheus (targets/config), OpenRAG (startup/secret/bundle) et Akvorado
(insertions fraîches seulement) nécessitent encore des preuves. Sentry et DefectDojo ont
passé leurs contrôles ciblés. Il ne s'agit **pas** d'une validation E2E
permanente.

## Sept contrôles critiques à rejouer

Après synchronisation d'une révision contenant
`scripts/truenas/triage-critical-failures.sh`, exécuter **en lecture seule** :

```bash
sudo bash scripts/truenas/triage-critical-failures.sh --check
```

L'ancien `--check --section critical` couvre toujours 16 gates.
Le nouveau script isole les sept dernières gates en échec, avec
preuve privée et aucune action mutante. Les scripts déjà présents sur
TrueNAS peuvent être utilisés individuellement avant la fusion :
[commandes exactes](2026-10-25-critical-acceptance-followup.md).

## Contrôles distincts après migration

Le runner conserve la collecte `critical` historique, mais ajoute deux
sections **sélectionnées explicitement** :

- `--check --section postmigration` : validité du catalogue généré,
  readiness fonctionnelle des services, observations Gatus fraîches et
  cibles Prometheus. Tous les résultats sont horodatés dans un répertoire
  privé ; une panne ne masque pas les suivantes.
- `--check --section apisix` : état des seuls conteneurs `apisix`
  et `echo`. Un déploiement absent retourne `SKIP/WARN`, pas un PASS
  artificiel. Un processus `running` ne garantit pas une route HTTP
  opérationnelle.

Après un lancement APISIX explicitement autorisé, exécuter d'abord le
[contrôle du service](../../apps/apisix/README.md), puis le smoke
authentifié. La clé `APISIX_KEY` n'est pas nécessaire pour consulter
les métadonnées Docker. Aucun port hôte ou label Traefik n'est ajouté.

```bash
sudo bash scripts/truenas/migration-operator.sh --check --section postmigration
sudo bash scripts/truenas/migration-operator.sh --check --section apisix
```

Un diagnostic qui manque de preuves retourne **exit=2 (non vérifié)**,
notamment si APISIX n'est pas déployé ou si Gatus ne dispose pas de résultats
récents. **exit=1** signifie qu'au moins un contrôle a réellement échoué.
Ces codes de sortie ne doivent pas être regroupés sous un unique statut DOWN.

### Diagnostic Gatus — preuve directe ou capture locale

La configuration Git contient **85 moniteurs** (63 TCP, 21 HTTP,
1 HTTPS). Ce total ne prouve ni l'exécution ni le succès des sondes.

Sur TrueNAS autorisé, sans clé ni modification de service :

```bash
python3 scripts/truenas/diagnose-gatus-monitors.py --check
```

Pour réanalyser une capture privée **récente** de l'API
`/api/v1/endpoints/statuses` sans aucune connexion réseau :

```bash
python3 scripts/truenas/diagnose-gatus-monitors.py --check --snapshot /chemin/prive/gatus-statuses.json
```

Le script refuse les liens symboliques et les captures de plus de 1 Mio.
Il n'affiche ni URLs de destination, ni corps d'erreur, ni secrets.
Le résultat contient seulement des identifiants canoniques et des
catégories d'erreur autorisées. **Ne pas joindre la capture brute à la PR.**

Contrat de sortie : `0` si toutes les sondes déclarées sont confirmées
UP avec parité d'inventaire ; `1` dès qu'une sonde est effectivement DOWN
(même en présence d'inconnues) ; `2` en cas de données absentes, périmées,
dupliquées ou de dérive de catalogue, sans DOWN observé.
Le `postmigration` classe `2` en WARN, jamais en panne démontrée.
Une capture historique ne prouve pas l'état courant des services.

**Chaque commande est indépendante**. Ne pas les déclencher
automatiquement après `--apply-wave` sans connaître les composants
effectivement migrés : une absence volontaire reste non vérifiée.

## Diagnostic des quatre sessions migration (25 octobre)

Les sessions `catalog`, `secrets`, `postmigration` et `critical`
restent privées. Pour obtenir uniquement les catégories d'erreur et
les **comptages** de bloqueurs, sans afficher les noms d'applications ni
les valeurs de secrets, exécuter sur TrueNAS :

```bash
sudo python3 scripts/truenas/triage-migration-session.py --check \
  --session /mnt/cpool/var/nabla/migration-20261024/session-NcBIRDu9 \
  --session /mnt/cpool/var/nabla/migration-20261024/session-UVhR50Jd \
  --session /mnt/cpool/var/nabla/migration-20261024/session-o39rErEc \
  --session /mnt/cpool/var/nabla/migration-20261024/session-l5DtxbvY
```

Cet analyseur accepte uniquement les sessions dans la racine canonique,
les phases connues et les fichiers réguliers de taille bornée. Il refuse
les symlinks et n'affiche jamais le contenu des rapports. Un plan Gatus
`selectedWaveReady=true` est **planifiable**, pas accepté au runtime.
L'outil n'exécute aucun `--apply-wave` et n'ajuste aucun secret.
La qualité locale hermétique se vérifie par `just migration-session-triage-test`.

## Migration des secrets : pas encore clôturée

Le fait que les fichiers canoniques soient « staged » ne signifie pas
que leur contenu est complet, que leur `env_file` runtime est à jour ni
que les anciens chemins sont supprimables. Suivre les
[critères de clôture](truenas-secret-migration-closure.md) avant un
`--finalize openrag`. Ne jamais générer un nouveau mot de passe
OpenSearch pour résoudre une simple erreur de métadonnées.

## Séquence de migration approuvée (jamais automatique)

1. Créer une sauvegarde des ressources réellement concernées.
2. Examiner le plan `--plan-wave` sur TrueNAS ; conserver la preuve en privé.
3. Confirmer l'identité de la révision `master` et l'absence de diff local.
4. Comparer `planHash` avec le plan immédiatement avant la demande de mutation.
5. Exécuter seulement la commande `--apply-*` **explicitement approuvée**.
6. Rejouer le contrôle read-only ciblé et enregistrer le résultat.
7. Appliquer le rollback spécialisé si les critères d'acceptation échouent.

Ne pas contourner la dérive du plan, réinitialiser Kafka, purger les WAL,
régénérer les secrets OpenRAG, indexer `cpool/bababou`, ni supprimer des
datasets pour obtenir un `PASS`. L'option `--allow-reviewed-drift`
est limitée à `--apply-step` et requiert une revue humaine du diagnostic
avant utilisation ; elle n'est pas la valeur par défaut.

## Quality gate et compatibilité

Le nouveau point d'entrée
`scripts/truenas/migration-operator.sh` **délègue** au runner conservé
`finish-migrations-20261024.sh` dans un **Bash enfant**. Les anciens
appels restent compatibles pour les runbooks et tests historiques.
Le registre `migration-diagnostic-sections.sh` reste sourcé après les
garde-fous des modes mutateurs.

Exécuter `just migration-20261024-test` sur un worktree isolé, puis
`just agent-skills-check` et `just quality` avant publication.
Les nouveaux tests couvrent notamment les modes combinés, les sorties
privées et l'absence du runner. **Aucune gate ni acceptation runtime
n'est présumée PASS par cette documentation.**
