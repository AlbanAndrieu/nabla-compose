# CrowdSec

This deployment is the **central CrowdSec Security Engine + Local API (LAPI)** for the homelab.
pfSense should run in CrowdSec **Small / remediation-only** mode and consume decisions from this LAPI instead of hosting the Security Engine itself.

## Audit suivant — règles PF chargées, lecture seule (30/10/2026)

La preuve précédente `SYNTHETIC_PF_DECISION_CYCLE_PASS`
démontre la **propagation dans la table PF et le retrait** ;
elle ne démontre pas la présence d'une règle effective bloquant
les paquets entrants. Le nouveau contrôle :
```bash
cd ~/w/nabla-compose
git pull --ff-only
just crowdsec-pf-rules-test
just crowdsec-pf-rules-audit
```

Le diagnostic exécute exclusivement des lectures SSH
(`pfctl -s info`, `pfctl -sr`, ancres si accessibles)
et recherche `block in quick` avec la table IPv4
`<crowdsec_blacklists>` en **source**.
`BLOCK_RULE_LOADED` indique une règle chargée dans la
portée racine ; règle trouvée **uniquement en ancre**,
absence de `quick in`, règle `pass`, erreur de transport
ou statut PF inconnu restent non concluants.
Aucune sortie brute de règles ou d'IP n'est publiée.

**21 tests de contrat** ajoutés (`test_crowdsec_pf_rules_audit.py`),
intégrés au gate CrowdSec (100 tests attendus).
**Nouveau gate et audit runtime : NON EXÉCUTÉS sur workstation**
dans cette session. Les règles peuvent être chargées mais
n'avoir aucun effet sur un paquet WAN à cause des interfaces,
règles précédentes ou états existants : cette preuve nécessite
une validation distincte avec logs/compteurs/point WAN sûr.

## Réception P0 CrowdSec : test synthétique LIVE réussi (30/10/2026)

**DONE — boucle de remédiation centralisée (sur runtime réel) :**
`synthetic_preflight=PASS` → création d'un ban central
`203.0.113.77` (décision ID **1531819**) →
`synthetic_pf_application=OBSERVED` dans la table
`crowdsec_blacklists` pfSense →
`synthetic_cleanup=PASS lapi_absent=true pf_absent=true`.
Verdict : **`SYNTHETIC_PF_DECISION_CYCLE_PASS`**.

L'adresse appartient à **TEST-NET-3**, bloc documentaire RFC 5737,
pas à une victime, un attaquant ou un véritable service.
Le mot *synthetic* décrit **la décision manuelle `origin=cscli`**,
pas le comportement de l'infrastructure : propagation et retrait
PF ont été réellement observés. Aucun secret n'a été renouvelé,
aucun flush PF ni conteneur redéployé. La suppression ciblait
l'ID exact, avec preuve de retrait des deux systèmes.

**Limites indépendantes :** non vérifiés par ce test, la création
naturelle de décision par un scénario CrowdSec et le filtrage
effectif de paquets WAN par les règles PF. La baseline v1 reste
archivée, une v2 doit être créée pour reprendre la preuve naturelle.
Gate ciblé workstation **79/79 tests PASS** ; gate global inconnu.

## Réception workstation CrowdSec — 30 octobre 2026

- **DONE — gate ciblé après correction du JSON imbriqué :**
  `just crowdsec-pf-synthetic-test` **24/24 PASS**,
  `just crowdsec-bouncer-config-test` **74/74 PASS**.
  Les tests unitaires utilisent des simulations et ne prouvent
  pas l'application d'une décision dans le PF réel.
- **DONE — inspection runtime en lecture seule :**
  `just crowdsec-pf-synthetic-inspect` renvoie
  `lapi_matches=0 decision_ids=none pf_present=false
  pf_bouncer=RUNNING` ; aucun vestige actif détecté sur
  `203.0.113.77`. Ce résultat **n'établit pas** l'issue
  du test synthétique antérieur.
- **Correctif de diagnostic supplémentaire [skip ci] :**
  les échecs d'exécution distante sont classés dans des
  catégories expurgées, notamment `ADD_DENIED_ALLOWLIST`.
  Dans CrowdSec v1.8.1, `cscli decisions add` peut
  refuser l'IP cible si elle est allowlistée ; la cause
  du premier échec n'est **pas encore vérifiée**.
  5 nouveaux tests versionnés ; **79 tests attendus**
  au prochain gate local. Pas de `--bypass-allowlist`
  automatique.
- **P0 toujours ouvert :** `SYNTHETIC_PF_DECISION_CYCLE_PASS`
  non observé sur le runtime. Précontrôle puis éventuelle
  mutation explicite uniquement sur décision de l'opérateur.
  Baseline naturelle v1 conservée, nouvelle v2 séparée.

## Diagnostic du test synthétique — 30 octobre 2026 (PR #295)

**Évidence workstation :** `just crowdsec-pf-synthetic-test`
**15/15 PASS**, `just crowdsec-bouncer-config-test` **61/61 PASS**,
précontrôle LIVE **PASS** sur `203.0.113.77`. L'exécution
`--apply --confirm SYNTHETIC-203.0.113.77` a ensuite retourné
`synthetic_cleanup=NOT_VERIFIED manual_review_required=true`,
sans identifiant créé confirmé. **La réception de remédiation PF
reste NOT_VERIFIED :** ne pas affirmer que le ban a été appliqué,
supprimé ou jamais créé.

**Cause de code confirmée par CrowdSec v1.8.1** : le JSON de
`cscli decisions list -o json` est une collection d'alertes
avec leurs `decisions[]` imbriquées. L'ancien parseur pouvait
produire un faux `initial_lapi=ABSENT` et échouer à identifier
la décision pour `delete --id` après la création. Dans #295,
le parseur accepte et vérifie les décisions imbriquées, et le
nettoyage exige également le `scenario` aléatoire du test
(`origin=cscli`, ID unique, scope/IP/type exacts).
`just crowdsec-pf-synthetic-inspect` permet de rechercher en
lecture seule des vestiges LAPI/PF de l'essai. **Ne pas relancer
`--apply` avant inspection et nouveau précontrôle PASS.**
Nouveaux tests de régression à exécuter sur la workstation.

**Baseline naturelle :** l'ancien collecteur souffrait de la
même hypothèse JSON. Une baseline **v2 séparée**, avec parsing
correct, utilise `crowdsec-pf-natural-cycle-v2.json`.
Conserver le fichier v1 privé en archive ; ne jamais le considérer
comme preuve d'absence de décisions historiques, ni le modifier
automatiquement. La v2 est **NOT_YET_CAPTURED**.

## Réception CrowdSec Small — 27–28 octobre 2026

**Le bouncer pfSense a réussi sa bascule sur la LAPI TrueNAS.**
Les sections qui suivent détaillent les incidents et procédures
**historiques**, et ne doivent pas provoquer de nouvelle rotation.

| Contrôle | Dernière preuve opérateur |
| --- | --- |
| LAPI TrueNAS | CrowdSec 1.8.1 RUNNING/healthy sur `172.17.0.24:8084` |
| Fichier clé `BOUNCER_KEY_PFSENSE_FIREWALL` | Présent en `0600` |
| Authentification candidate | `central_candidate_auth=ACCEPTED` |
| TrueNAS `diagnose-crowdsec-cutover.sh --accept` (27/10, 23:12 UTC) | **0 erreur / 2 warnings** ; provenance pfSense **LAN_IP_AND_FIREWALL_USER_AGENT_OBSERVED** |
| Enregistrement de base | `PFSENSE_FIREWALL`, `172.17.0.24`, client `curl`, `last_pull=21:46:28Z` : **sonde locale TrueNAS seulement** |
| Enregistrement bouncer réel | `PFSENSE_FIREWALL@172.17.0.1`, IP `172.17.0.1`, type `crowdsec-firewall-bouncer`, `last_pull=2026-10-27T23:12:07Z` : **lecture LAPI pfSense attestée** |
| Moteur CrowdSec local pfSense | Absent |
| Firewall bouncer | En cours, `api_url=http://172.17.0.24:8084` |
| `just crowdsec-pfsense-accept` | **0 échec / 0 warning** |
| Tables PF | **4 074** entrées au dernier contrôle workstation (4 022 IPv4 + 52 IPv6), provenance des règles **non établie** |
| Authentification bouncer pfSense → LAPI | `central_lapi_http=200`, `central_lapi_auth=ACCEPTED` |

**Gate local CrowdSec — correction du 28/10 :** 5/5 tests URL et
11/11 tests d'authentification passent désormais directement sur TrueNAS.
La suite du provisionneur avait encore 2 échecs sur 4 à cause du faux
exécutable `docker` lancé via `timeout` dans un dossier temporaire ;
cela n'indique aucune panne du conteneur en production.
Les tests simulent maintenant **`docker` et `timeout` par des fonctions
Bash** chargées dans le même interpréteur, sans mutation, sans Docker
réel et sans exécutable dans `/tmp`. Une reproduction isolée confirme
les trois parcours de vérification `--check` : inscription inutilisée,
inscription utilisée (refus de rotation) et secret déjà présent.
La suite du provisionneur complète, y compris le contrôle statique
contre les mutations et la vérification du script, passe **5/5 tests**
sur une copie locale isolée. Le contrôle statique a été corrigé pour
ne plus s'auto-détecter dans son propre code.
**Gate `just crowdsec-bouncer-config-test` exécuté sur TrueNAS le
28/10 : 31/31 PASS** (URL 5/5, authentification 11/11,
provisionneur 5/5, provenance 10/10), avec contrôles Bash/Python OK.
Preuve opérateur sur le HEAD `5f1cd05b` après `git pull --ff-only`.
Cela valide la recette locale, pas le cycle de remédiation PF.
L'opération `--apply` n'est ni nécessaire ni autorisée par ce diagnostic ;
le secret existant doit être conservé.

**Statut : SMALL_BOUNCER_CUTOVER_PASS.** Cela valide la connectivité,
l'authentification et l'état du bouncer, sans attribuer les
entrées PF existantes aux décisions centrales (0 décision centrale
dans le dernier diagnostic). Cette preuve reste à corréler à
une nouvelle décision et son application/expiration dans PF.
Les anciennes décisions PF peuvent subsister temporairement ;
leur nombre seul ne prouve pas une reconstruction par TrueNAS.

**Contrôle renforcé au prochain pull Git :** le mode `--accept` exige désormais
l'enregistrement `PFSENSE_FIREWALL@172.17.0.1`, un `last_pull`,
`ip_address=172.17.0.1`, `type=crowdsec-firewall-bouncer`, `revoked=false`.
Le `last_pull` du client `curl` TrueNAS ne suffit plus. Ce contrôle prouve
l'interrogation de la LAPI depuis pfSense selon les métadonnées fournies
par CrowdSec, **pas** l'application ou l'expiration des bans dans PF.

**Correctif du 27/10 après réception TrueNAS :** la première version du
filtre JSON contrôlait `valid=true`, champ **absent** de `cscli bouncers
list -o json` en CrowdSec **v1.8.1**. La colonne CLI « Valid » est dérivée
de `revoked`. Le filtre exige désormais `revoked=false` (champ présent)
avec le nom, l'IP, le type et `last_pull`; une valeur absente fait échouer
l'acceptation. [Modèle upstream v1.8.1](https://github.com/crowdsecurity/crowdsec/blob/v1.8.1/cmd/crowdsec-cli/clibouncer/bouncers.go).

La suite `test_crowdsec_candidate_bouncer_auth.py` échouait sur TrueNAS :
six cas tentaient une connexion réelle à `127.0.0.1:8084`. Une tentative
intermédiaire utilisait un exécutable fictif dans `/tmp`, mais son
invocation échouait avec `NOT_VERIFIED_NO_CURL` (cause exacte des
restrictions d'exécution sur TrueNAS non attestée). Les tests utilisent
désormais une **fonction Bash `curl` locale**, définie dans le même
interpréteur puis chargent le script avec
`script="$1"; shift; source "$script" "$@"`.
Aucun exécutable temporaire ni réseau n'est nécessaire. La variable
d'injection `CROWDSEC_CURL_BIN` a été retirée du script de production.
La reproduction locale vérifie 9 scénarios sans trafic réseau ;
le gate complet sur TrueNAS reste à exécuter.
L'ancien nom `pfsense-firewall` a un dernier appel daté du 25 septembre ;
ne pas le supprimer sans étude de sa provenance et de son usage.

**Réception workstation du 28/10 — gate et baseline LIVE réalisés :**
`just crowdsec-pf-natural-test` **15/15 PASS** et
`just crowdsec-bouncer-config-test` **46/46 PASS**
(URL 5, auth 11, provisionneur 5, provenance 10, cycle PF 15)
sur le HEAD `ba5aa198`.
`just crowdsec-pf-natural-baseline` :
`crowdsec_pf_baseline=READY source_mode=LIVE pf_networks=4016 natural_bans=0`.
Première commande `just crowdsec-pf-natural-observe` :
`pf_decision_cycle=NOT_VERIFIED reason=NO_ELIGIBLE_NEW_NATURAL_BAN`.
C'est une attente **sans nouvelle décision naturelle**, pas une panne LAPI.
Ne pas relancer `baseline` : cela tenterait d'écraser l'état initial
(et le script la refuserait). Exécuter seulement `observe` depuis
la même workstation. Le fichier `0600` contient les réseaux PF
historiques : **ne pas publier, copier ni supprimer automatiquement**.
Le cycle de remédiation PF reste **P0 NON VÉRIFIÉ**.

**Test synthétique réversible prêt (28/10, non exécuté sur le homelab) :**
`scripts/workstation/smoke-crowdsec-pf-synthetic.py` utilise
`203.0.113.77` (TEST-NET-3), TTL **5m** et suppression
**par l'ID unique** de la décision créée. Il vérifie d'abord
l'absence de décision LAPI et de correspondance PF (CIDR inclus),
ainsi que le bouncer pfSense actif et le moteur local arrêté.
En cas d'échec ou de Ctrl+C, il tente le nettoyage ; si l'ID
est ambigu ou si la liaison SSH tombe, un nettoyage automatique
ne peut pas être garanti et le statut reste `NOT_VERIFIED`.
Ne pas utiliser `cscli decisions delete --ip`, `--all` ou
`pfctl -T flush` pour la reprise.

Les modes sont **distincts** :
`just crowdsec-pf-synthetic-preflight` est en lecture seule,
alors que l'action mutatrice exige une commande directe
`--apply --confirm SYNTHETIC-203.0.113.77` sur la workstation.
**15/15 tests simulés PASS** localement. Ce nouveau bloc est inclus
dans `just crowdsec-bouncer-config-test` (61 tests ciblés) ;
ce gate étendu doit être relancé sur la workstation.
Une décision manuelle `origin=cscli` ne valide pas le détecteur
naturel `origin=crowdsec`. Voir le runbook PF pour exécution,
limites et reprise ciblée.

**P0 PF : corrélation automatisée en lecture seule (28/10).**
Le script `scripts/workstation/observe-crowdsec-pf-decision.py`
mémorise sur la workstation une baseline privée des décisions LAPI
et des entrées PF historiques, puis suit les **nouvelles décisions
naturelles IPv4** du moteur central jusqu'à leur application et
disparition dans `crowdsec_blacklists`. Il vérifie également le
fonctionnement du bouncer et l'absence du moteur pfSense local.
`just crowdsec-pf-natural-test` : **15/15 tests offline PASS**
sur l'environnement d'agent. Ces tests sont également inclus dans
`just crowdsec-bouncer-config-test`, dont la validation totale
sur le nouveau HEAD reste à faire (31 anciens + 15 nouveaux).
Les étapes opérateur sont exclusivement à lancer **sur la workstation** :

```bash
just crowdsec-pf-natural-baseline
just crowdsec-pf-natural-observe
```

**Une baseline runtime a été collectée par l'opérateur sur
la workstation (4 016 réseaux IPv4 PF, 0 ban naturel initial).**
La première observation est `NOT_VERIFIED` :
aucune nouvelle décision naturelle éligible. Le script n'ajoute
et ne retire aucune décision. Les snapshots offline ne peuvent
jamais produire un `PF_DECISION_CYCLE_PASS` live. Les fichiers
de preuve contiennent des IP sensibles et restent uniquement
dans le stockage privé local.

**Réception P0 encore ouverte :** [procédure de preuve d'une décision
nouvelle et de son retrait dans PF](../../docs/runbooks/crowdsec-pfsense-decision-provenance.md).
La procédure commence en lecture seule ; toute décision synthétique est
optionnelle et nécessite un accord explicite de l'opérateur.

### Erreur de formulaire « Agent user/password required »

Le paquet officiel pfSense vérifie les champs
`remote_agent_user`, `remote_agent_password` et
`remote_fw_bouncer_api_key` **dès que `enable_lapi` est désactivé**,
sans tester `enable_agent`. La validation est donc imposée
même en Small (Log Processor OFF) :

- [Source pfSense `crowdsec.inc` — `crowdsec_validate_form`](https://github.com/crowdsecurity/pfSense-pkg-crowdsec/blob/main/security/pfSense-pkg-crowdsec/files/usr/local/pkg/crowdsec.inc)
- [Définition des champs dans `crowdsec.xml`](https://github.com/crowdsecurity/pfSense-pkg-crowdsec/blob/main/security/pfSense-pkg-crowdsec/files/usr/local/pkg/crowdsec.xml)

Les champs GUI ne correspondent pas automatiquement aux
variables de shell `CROWDSEC_REMOTE_API_USER` et
`CROWDSEC_REMOTE_API_PASSWORD`. Le login/password machine
est distinct de la clé bouncer : **ne pas mettre la clé
`BOUNCER_KEY_PFSENSE_FIREWALL` dans Agent password**.
Ne pas employer le login machine `truenas` si son identité
est déjà utilisée par le moteur TrueNAS. Si la GUI persiste
à exiger ces champs et qu'aucun login dédié n'existe, créer
un compte **distinct** `pfsense-small` sur la LAPI centrale.
Il sera validé mais **non sollicité** tant que Log Processor
pfSense reste OFF. Cette création est facultative si les
paramètres déjà enregistrés continuent de fonctionner.

Dans le conteneur TrueNAS, inspection read-only :

```bash
sudo docker exec crowdsec cscli machines list
```

Pour enregistrer un nouveau compte dédié uniquement si
l'interface ne peut pas sauvegarder autrement :

```bash
# Création ponctuelle : mot de passe automatique dans un fichier
# éphémère *dans le conteneur*, jamais dans Git ou la conversation.
sudo docker exec crowdsec sh -c \
  'umask 077; cscli machines add pfsense-small --auto -f /tmp/pfsense-small-credentials.yaml'

# Consulter localement le fichier privé et saisir login/password
# dans les champs GUI Agent user / Agent password.
sudo docker exec crowdsec sh -c \
  'cat /tmp/pfsense-small-credentials.yaml'

# Une fois les champs pfSense sauvegardés, supprimer le fichier
# éphémère dans le conteneur ; conserver le secret dans
# un coffre approuvé si nécessaire.
sudo docker exec crowdsec rm -f /tmp/pfsense-small-credentials.yaml
```

Les valeurs du fichier sont **secrètes** : ne pas partager
le résultat des commandes `cat` ni les sauvegarder dans Git.
Conserver Remediation Component ON, Log Processor OFF et
Local API OFF. L'API Machine peut publier des décisions :
ne jamais partager cette identité avec le compte TrueNAS.

**Prochaine étape de validation (lecture seule) :**

```bash
# Workstation :
just crowdsec-pfsense-accept
ssh -o BatchMode=yes -o ConnectTimeout=8 home.albandrieu.com sh -s \
  < scripts/pfsense/check-central-crowdsec-bouncer.sh

# TrueNAS :
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --accept
sudo docker exec crowdsec cscli bouncers list
```

Après avoir obtenu la preuve d'un `last_pull` actualisé
**par le bouncer pfSense** et le statut des nouvelles décisions,
le chantier peut être clos sans migrer les anciennes tables PF.

## Incident de provisionnement et récupération des variables — 27 octobre

**Relevé réel de l'opérateur :**

```text
central_registration=PFSENSE_FIREWALL last_pull=<none>
credential_state=MISSING; unused registration eligible for --apply
level=info msg="bouncer 'PFSENSE_FIREWALL' deleted successfully"
ERROR: unexpected key format; no runtime file written
central_candidate_auth=NO_GO_MISSING_SECRET_FILE
```

Le premier `--apply` a **supprimé** l'inscription inutilisée,
puis `cscli bouncers add -o raw` a créé une nouvelle inscription,
mais le parseur de sortie a rejeté la chaîne retournée.
**Aucune clé n'a été enregistrée** dans
`/mnt/cpool/secrets/runtime/crowdsec/.env.secrets`.
La nouvelle clé aléatoire n'est pas récupérable par
`cscli bouncers list` : cette sortie ne donne pas les secrets.
Le bouncer pfSense reste connecté à sa **LAPI locale :8089**.

### Variables existantes : ne pas confondre machines et bouncers

| Nom | Utilisation |
| --- | --- |
| `CROWDSEC_LOCAL_API_PASSWORD` | Password du compte *machine* CrowdSec, pas une clé bouncer |
| `CROWDSEC_BOUNCER_API_KEY` | Candidate bouncer centrale ; identifier sa source et tester son authentification |
| `BOUNCER_KEY_TRAEFIK` | Identité de bouncer **Traefik** ; ne pas l'attribuer implicitement à pfSense |
| `BOUNCER_KEY_PFSENSE_FIREWALL` | Nom canonique attendu par le Compose et l'audit pfSense |
| `CROWDSEC_PFSENSE_BOUNCER_KEY` | Alias d'import Vaultwarden dans `config/secrets/manifest.json` |

`CROWDSEC_BOUNCER_API_KEY` n'est **pas** automatiquement le
nom reconnu par l'entrypoint CrowdSec pour enregistrer
`PFSENSE_FIREWALL`. L'entrypoint attend
`BOUNCER_KEY_<identité>`, ou une inscription créée
par `cscli`. Cf. documentation de l'image officielle :
https://github.com/crowdsecurity/crowdsec/blob/master/build/docker/README.md.

Depuis la **session TrueNAS** qui possède ces variables :

```bash
# Vérifier la présence, sans afficher la valeur.
for name in CROWDSEC_LOCAL_API_PASSWORD CROWDSEC_BOUNCER_API_KEY \
            BOUNCER_KEY_TRAEFIK BOUNCER_KEY_PFSENSE_FIREWALL; do
  if [ -n "${!name:-}" ]; then echo "$name=PRESENT";
  else echo "$name=ABSENT"; fi
done

# Si la variable candidate existe déjà dans ta session, l'exporter
# et la tester SANS sudo (sudo ne propage pas toujours l'environnement).
export CROWDSEC_BOUNCER_API_KEY
bash scripts/truenas/check-crowdsec-candidate-bouncer.sh \
  --env CROWDSEC_BOUNCER_API_KEY

# Inventaire des noms injectés dans le conteneur : aucun secret affiché.
sudo docker inspect crowdsec --format '{{range .Config.Env}}{{println .}}{{end}}' |
  awk -F= '$1 ~ /^(CROWDSEC_LOCAL_API_PASSWORD|CROWDSEC_BOUNCER_API_KEY|BOUNCER_KEY_TRAEFIK|BOUNCER_KEY_PFSENSE_FIREWALL)$/ {print $1 "=PRESENT"}'

# Enregistrement des identités centrales (aucune clé divulguée).
sudo docker exec crowdsec cscli bouncers list
```

`central_candidate_auth=ACCEPTED` signifie seulement **clé valide
sur la LAPI centrale**, pas identité automatiquement reconnue
comme `PFSENSE_FIREWALL` ; vérifier la registration avant
d'envisager sa réutilisation. En particulier, ne pas recopier
la clé Traefik dans pfSense sans décision explicite de partager
cette identité.

### Correction du provisionneur après incident

Le script `scripts/truenas/provision-crowdsec-pfsense-bouncer.sh`
ne parse plus la réponse `-o raw` : il **génère d'abord** une clé
avec `openssl rand -hex 32`, écrit le fichier privé root:root
`0600` et **ensuite seulement** renouvelle l'inscription
`PFSENSE_FIREWALL` avec l'option officielle `--key`.
La clé transite par l'entrée standard vers Docker et n'est
jamais imprimée ; le retour de `cscli` est masqué. En cas
d'échec de registration, le fichier de clé est conservé.
Il ne faut pas relancer l'ancienne version du script.

Après vérification du gate local et seulement si aucune clé
existante n'est réutilisable :

```bash
just crowdsec-bouncer-config-test
sudo bash scripts/truenas/provision-crowdsec-pfsense-bouncer.sh --check
sudo bash scripts/truenas/provision-crowdsec-pfsense-bouncer.sh --apply
sudo bash scripts/truenas/check-crowdsec-candidate-bouncer.sh
```

En cas d'échec après `credential_state=STAGED`,
ne pas refaire `--apply` : examiner l'inscription centrale
et la clé protégée enregistrée, puis reprendre de manière
ciblée. Aucun moteur pfSense ne doit être arrêté avant
l'authentification du nouveau bouncer.

## Chemin court accepté — réémission de la clé centrale et pfSense Small

Décision opérateur du 27 octobre : **les tables de remédiation pfSense
n'ont pas à être copiées dans CrowdSec TrueNAS**. Le moteur central
reconstruira ses décisions à partir des nouvelles détections et
du flux de renseignement qu'il reçoit. Le bouncer PF se
synchronisera progressivement. Il peut y avoir une **fenêtre
de protection réduite** contre les IP anciennement bloquées.
Cette conséquence est acceptée ; elle n'exige pas un import des
8 637 anciennes entrées PF.

Le dernier contrôle : CrowdSec TrueNAS RUNNING/healthy, LAPI LAN
accessible, Loki confirmé, mais fichier secret bouncer absent
et clé pfSense historique refusée par la LAPI centrale (`403`).
L'enregistrement central `PFSENSE_FIREWALL` a
`last_pull=<none>`. La réémission de **cet enregistrement inutilisé**
est donc la voie la plus courte ; nul besoin de créer un deuxième
bouncer ou de redéployer l'App TrueNAS.

### Étape 1 — enregistrer la nouvelle clé sur TrueNAS

Depuis le checkout courant de la PR #289 sur **TrueNAS** :

```bash
sudo bash scripts/truenas/provision-crowdsec-pfsense-bouncer.sh --check
sudo bash scripts/truenas/provision-crowdsec-pfsense-bouncer.sh --apply
sudo bash scripts/truenas/check-crowdsec-candidate-bouncer.sh
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --check
```

Le mode `--apply` doit être lancé **explicitement**, seulement
après lecture du diagnostic des variables existantes. Il ne
fonctionne que si le fichier privé est absent et si
`PFSENSE_FIREWALL` n'a jamais été interrogé (`last_pull` vide).
Il génère d'abord une clé avec `openssl rand -hex 32`,
l'enregistre **avant** toute suppression d'identité, puis
remplace **l'enregistrement inutilisé** au moyen de
`cscli bouncers delete` et de `cscli bouncers add --key`
(sans lire ni imprimer la sortie du CLI), en conservant la clé dans le fichier
`/mnt/cpool/secrets/runtime/crowdsec/.env.secrets`
(root:root 0600), et ne modifie **pas** pfSense.
Le fichier reste sur TrueNAS. Ne le commiter ou envoyer
sur aucun canal de conversation. Si la génération échoue,
le script s'arrête et ne modifie pas le moteur ni le bouncer
pfSense : diagnostiquer uniquement l'enregistrement central.

**Go** lorsque `central_candidate_auth=ACCEPTED` et le
nouveau `--check` ne signale plus d'erreur.

### Étape 2 — passer pfSense en mode Small

Depuis **Services → CrowdSec** dans pfSense :

1. Sauvegarder la configuration actuelle.
2. Configurer Remote LAPI : `http://172.17.0.24:8084`
   avec la nouvelle clé provenant du fichier privé TrueNAS.
3. Conserver **Remediation Component** activé.
4. Désactiver **Log Processor** et **Local API**.
5. Enregistrer/appliquer la configuration CrowdSec.

Ne pas installer de paquet sur TrueNAS ou copier
le fichier de secrets dans Git. La commande
`ssh ... < scripts/pfsense/check-central-crowdsec-bouncer.sh`
doit alors renvoyer `central_lapi_http=200` ; auparavant,
elle renvoyait 403 avec l'ancienne clé. Le trafic syslog
reste acquis via Loki sur TrueNAS.

### Étape 3 — réception simplifiée

Depuis la workstation :

```bash
just crowdsec-pfsense-accept
ssh -o BatchMode=yes -o ConnectTimeout=8 home.albandrieu.com sh -s \
  < scripts/pfsense/check-central-crowdsec-bouncer.sh
```

Depuis TrueNAS :

```bash
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --accept
```

Vérifier que le bouncer pfSense est actif, que son URL
est la LAPI centrale et que **le moteur local a cessé**.
`last_pull` doit être renouvelé après la bascule ; une probe
sur TrueNAS peut elle-même le renseigner et ne doit pas
être confondue avec une requête de pfSense.
**Des tables PF temporairement vides sont désormais
acceptables** puisque la LAPI centrale avait zéro décision ;
elles devront ensuite être alimentées par de nouvelles décisions
centrales réelles. Ne pas fabriquer de bannissement sur les IP
de gestion. Si l'authentification échoue, restaurer la
configuration CrowdSec pfSense sauvegardée.

## Réception opérationnelle — 27 octobre, 21:53 Europe/Paris

**Preuves exécutées par l'opérateur sur TrueNAS et pfSense :**

| Contrôle | Observation |
| --- | --- |
| TrueNAS `diagnose-crowdsec-cutover.sh --runtime` | **0 erreur / 1 warning** (aucune décision centrale active) |
| App `crowdsec` | RUNNING, conteneur `healthy`, image `crowdsecurity/crowdsec:v1.8.1` |
| Scenario `firewallservices/pf-scan-multi_ports` | désactivé et fichier absent |
| LAPI et métriques LAN | `172.17.0.24:8084` et `:6060` disponibles |
| Logs pfSense via Loki | `CANONICAL_CONFIRMED`, métrique `cs_lokisource_hits_total=940` |
| Décisions LAPI centrale | **0** |
| TrueNAS `--check` | **1 erreur / 2 warnings** : secret manquant/illisible, aucune décision, `last_pull=<none>` |
| `PFSENSE_FIREWALL` dans la LAPI centrale | enregistré, mais **aucun pull** |
| Workstation `just crowdsec-pfsense-preflight` | **0 erreur / 2 warnings** : moteur legacy encore actif, bouncer sur LAPI locale |
| pfSense → TrueNAS | TCP `172.17.0.24:8084` accessible |
| Tables PF de la chaîne locale | **8 620 IPv4 + 17 IPv6 = 8 637 entrées** |
| Clé pfSense actuelle vers LAPI TrueNAS | `central_lapi_http=403` (**rejetée**) |

**Décision : NO-GO.** Le rejet `403` sur `/v1/decisions`
indique que la clé pfSense actuellement utilisée avec
`http://172.17.0.1:8089` **n'est pas acceptée** par
la LAPI centrale. La documentation CrowdSec confirme
qu'une clé de bouncer absente/invalide renvoie `403` sur
cet endpoint : https://docs.crowdsec.net/docs/local_api/bouncers/.
Le problème n'est ni la connectivité TCP, ni l'ingestion
Loki, ni le scénario désactivé.

Ne pas confondre `cscli bouncers list` avec un coffre :
**une clé enregistrée n'est pas récupérable via cette commande**.
Consulter https://docs.crowdsec.net/u/user_guides/bouncers_configuration/.

### Nouveau Gate B1 — authentifier une clé candidate SANS changer pfSense

Récupérer la **clé exacte de la LAPI TrueNAS** dans un
emplacement approuvé (sauvegarde privée, coffre déjà autorisé),
puis restaurer *hors Git* le fichier runtime
`/mnt/cpool/secrets/runtime/crowdsec/.env.secrets`,
contenant `BOUNCER_KEY_PFSENSE_FIREWALL`,
avec des droits `root:root 0600`. Cette restauration
requiert une procédure opérateur approuvée : **ne pas
inventer ni recopier la clé de la LAPI pfSense locale**.

Après restauration, sur TrueNAS uniquement :

```bash
sudo bash scripts/truenas/check-crowdsec-candidate-bouncer.sh
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --check
```

Réception nécessaire : `central_candidate_auth=ACCEPTED`,
et bouncer enregistré sous le nom contrôlé
`PFSENSE_FIREWALL` (`last_pull` peut être renseigné
par la probe, qui demande les décisions en lecture seule).
Le script lit la clé **en mémoire**, exige `0600` et
utilise `curl --config -` sur stdin. Il ne l'affiche
ni ne l'inclut en argument de processus. Ne pas
activer `set -x` dans ce contexte.

Si la clé n'est plus disponible, faire approuver une
**réémission séparée**, de préférence sous un nouveau
nom de bouncer afin de préserver la référence
`PFSENSE_FIREWALL` pour audit. CrowdSec accepte
`cscli bouncers add NOM` et indique que la clé produite
**doit être conservée immédiatement** ; elle ne pourra
pas être relue. Il est possible d'utiliser
`CROWDSEC_BOUNCER_NAME=NOM` pour la réception TrueNAS
de cette nouvelle inscription. Ne pas créer/supprimer
une inscription, générer une clé, exporter un secret ou
modifier pfSense automatiquement : l'action est une
**rotation de credentials nécessitant approbation**.

### Nouveau Gate B2 — pas de perte silencieuse de remédiation

Le bouncer pfSense possède encore **8 637 entrées PF**
alimentées par la LAPI locale, alors que la LAPI centrale
ne propose **aucune décision active**. Un changement
immédiat de LAPI peut donc retirer les anciennes
protections au prochain rafraîchissement. **Ne pas
interpréter une table PF soudainement vide comme une
migration réussie.**

Avant cutover, relever les nombres de décisions locales
et centrales, leur origine et leur durée de vie, et
définir comment maintenir la protection pendant
la transition sans importer aveuglément des bannissements
périmés. Prévoir une validation contrôlée d'une décision
centrale (IP de test non critique) et de son expiration,
puis `last_pull` et application à PF. Aucun ban de test
n'est créé par cette PR.

**État git TrueNAS :** `tree=dirty`. Ne pas déployer
le checkout TrueNAS avant revue de ses différences ;
les scripts présentés sont en lecture seule.
## Reprise du 27 octobre — GO/NO-GO avant pfSense Small

La migration n'est **pas réceptionnée** au dernier relevé :
la LAPI CrowdSec TrueNAS est saine, et Loki reçoit les événements
pfSense, mais la connexion du bouncer pfSense à cette LAPI
n'est pas démontrée. Le précédent bouncer utilisait
`http://172.17.0.1:8089` (LAPI locale) ; l'enregistrement
`PFSENSE_FIREWALL` côté central avait `last_pull=<none>`.
Le fichier privé
`/mnt/cpool/secrets/runtime/crowdsec/.env.secrets`
était alors absent/illisible. Aucun nouveau diagnostic CrowdSec
n'a été communiqué dans le relevé du 27/10 consacré à HAProxy.
**NE PAS arrêter le moteur local sur ces seules preuves.**

### Gate A — préflight TrueNAS en lecture seule

Sur **TrueNAS** (pas sur pfSense, sans afficher aucune clé) :

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --runtime
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --check
```

Critères : app RUNNING/healthy, LAPI LAN `:8084`, Loki pfSense
canonique confirmé, scénario de boucle désactivé ;
`--check` doit confirmer le fichier secret `0600`, la variable
`BOUNCER_KEY_PFSENSE_FIREWALL` et **exactement un** bouncer
`PFSENSE_FIREWALL`. Un `last_pull` vide est attendu avant
activation et doit être contrôlé après bascule ; il ne prouve
pas à lui seul une authentification préalable réussie.
Un échec de clé/secret est **NO-GO**. Ne jamais régénérer,
copier dans Git ou afficher la clé pendant un diagnostic.

### Gate B — préflight pfSense et authentification centrale

Depuis la **workstation**, avec l'accès SSH existant :

```bash
# En preflight, moteur local RUNNING = warning, pas échec.
just crowdsec-pfsense-preflight

# Probe authentifié de la LAPI centrale avec la clé du bouncer
# pfSense actuel. Lit la clé depuis sa configuration, sans l'afficher.
# Un HTTP 403 signifie que la clé actuelle appartient probablement
# à l'ancienne LAPI et ne peut pas servir au cutover telle quelle.
ssh -o BatchMode=yes -o ConnectTimeout=8 home.albandrieu.com sh -s \
  < scripts/pfsense/check-central-crowdsec-bouncer.sh
```

La probe doit retourner `central_lapi_http=200`. Si elle
retourne 401/403, **arrêter ici** : retrouver dans un coffre
approuvé la clé enregistrée sur TrueNAS, ou prévoir une rotation
explicite, séparée et réversible. Le préflight pfSense confirme
seulement l'état actuel des tables PF et l'accès réseau.

### Gate C — bascule contrôlée (opérateur, mutation hors du diagnostic)

Après A/B sans blocage et sauvegarde de la configuration pfSense :

1. Conserver les tables et la fonction firewall bouncer actives.
2. Faire pointer uniquement le bouncer pfSense vers
   `http://172.17.0.24:8084` avec **la clé centrale validée**.
3. Contrôler l'authentification, puis observer un **nouveau**
   `last_pull` sur TrueNAS **après la bascule**, corrélé à une
   requête du bouncer pfSense. Une probe préalable de la clé
   candidate peut **elle-même renseigner `last_pull`** :
   la seule présence de cette valeur ne prouve pas le cutover.
4. Passer pfSense en mode Small : arrêter le **Security Engine**
   et ses traitements locaux, sans désactiver la remédiation PF.
5. Exécuter les réceptions **en lecture seule** :

   ```bash
   # TrueNAS
   sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --accept

   # workstation
   just crowdsec-pfsense-accept
   ```

6. Valider une décision non dangereuse réellement délivrée
   par la LAPI centrale et observée dans la table PF,
   puis son expiration/retrait. Ne jamais utiliser l'IP LAN
   de pfSense, TrueNAS ou de la workstation pour ce test.

**Rollback :** restaurer les paramètres bouncer/pfSense
préservés et vérifier les tables PF. Ne pas réactiver
automatiquement l'ancien moteur sans retirer le scénario
`firewallservices/pf-scan-multi_ports`, responsable
des boucles CPU historiques. Les scripts de diagnostic
et les recettes `just` sont **read-only** ; aucune bascule
pfSense ne s'exécute depuis cette PR.
## Target architecture

```text
pfSense RFC5424 ──> Alloy UDP/1514 ──> Loki ─┐
                                              ├──> CrowdSec Security Engine + LAPI on TrueNAS
Suricata eve.json ─────────────────────────────┘                  │
                                                  │ tcp/8084, LAN only
                                                  ▼
                                     pfSense firewall bouncer
                                                  │
                                                  ▼
                                            PF block tables
```

This removes CrowdSec parsing, scenarios, SQLite/LAPI work and CAPI synchronization from the resource-constrained pfSense appliance while keeping packet remediation at the firewall.

## Relevé opérateur — 26 octobre 2026 : bascule non autorisée

Les diagnostics ont été exécutés sans modification de service.
Le checkout TrueNAS affiche `head=de24ee7ae0cf`, `tree=dirty` :
éviter tout déploiement depuis cette copie avant revue de ses différences.

| Contrôle | Résultat observé |
| --- | --- |
| TrueNAS CrowdSec 1.8.1 | App RUNNING, conteneur running/healthy |
| LAPI TrueNAS `172.17.0.24:8084` | Listener OK ; `cscli lapi status` OK |
| Scénario `pf-scan-multi_ports` | Désactivé et fichier absent |
| Metrics `172.17.0.24:6060` | OK ; `cs_lokisource_hits_total=940` |
| Loki | `/ready=200`, query canonique `device=pfsense` **intermittente** (échec puis succès) |
| Décisions TrueNAS | `crowdsec_active_decisions=0` |
| Fichier secret bouncer TrueNAS | `/mnt/cpool/secrets/runtime/crowdsec/.env.secrets` absent ou illisible |
| Bouncer TrueNAS `PFSENSE_FIREWALL` | Inscrit, `last_pull=<none>` |
| pfSense Security Engine | Processus local **running** (pas Small) |
| pfSense firewall bouncer | **running**, URL `http://172.17.0.1:8089` (LAPI locale) |
| pfSense → TrueNAS LAPI | TCP `172.17.0.24:8084` joignable |
| Tables PF pfSense | `crowdsec_blacklists=9399`, `crowdsec6_blacklists=22` |

**Réception : BLOQUÉE.** La table PF à 9 421 entrées reflète
le bouncer encore relié à la **LAPI locale** ; elle ne démontre
aucune remédiation provenant de TrueNAS. Ne pas arrêter le moteur
local maintenant : ce serait un changement de la chaîne de protection
sans bouncer central fonctionnel ni rollback validé.

La requête Loki canonique a échoué lors de `--runtime` puis a
réussi lors de `--check`, alors que le compteur source valait 940.
Cela ne prouve pas une anomalie permanente de la règle Alloy.
Le diagnostic du dépôt fait désormais **une relance bornée** de
la requête exacte avant d'attribuer l'échec à la classification.
Une relance réussie conserve un warning ; deux échecs puis des
événements non-smoke provoquent un ERROR.

### Réception complémentaire : contrats et classification Loki

Le checkout de l'opérateur a exécuté sans erreur :

- `just crowdsec-loki-evidence-test` : **5/5 PASS** ;
- `just nexus-private-ingress-test` : **4/4 PASS**.

Depuis TrueNAS, la requête agrégée, sans lecture des messages :

```bash
curl --noproxy '*' -fsSG \
  'http://172.17.0.24:3100/loki/api/v1/query' \
  --data-urlencode \
  'query=sum by (device) (count_over_time({job="pfsense",app!="nabla-smoke"}[30m]))' |
  jq '.data.result | map({labels: .metric, count: .value[1]})'
```

retourne une unique série `{device="pfsense"}` avec **1 247
événements** sur la fenêtre de 30 minutes interrogée. Cela valide
la présence du label canonique dans ce relevé. Cela ne mesure ni
les événements totalement perdus avant Loki, ni l'absence de
microcoupures, ni une nouvelle décision CrowdSec.

**Conséquence opérationnelle :** aucune modification d'Alloy n'est
justifiée par l'échec ponctuel antérieur de la requête canonique.
La relance bornée du diagnostic signale une récupération, sans
transformer un échec persistant en succès. Les tests hors ligne
ne valident pas la configuration du bouncer pfSense, qui reste
connecté à la LAPI locale. Ne pas exécuter le cutover tant que
la clé centrale et `last_pull` ne sont pas confirmés.
### Séquence de décision avant la bascule

1. **Stabiliser les preuves** sur TrueNAS (lecture seule) :
   `sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --runtime`.
   En cas de warning Loki, interroger les compteurs/labels, sans
   modifier Alloy ni vider les journaux.
2. **Retrouver la clé centralisée existante** `PFSENSE_FIREWALL`
   dans une source approuvée. Contrôler les chemins/permissions
   sans afficher la valeur. Le `api_key` du bouncer qui parle à
   `172.17.0.1:8089` peut appartenir à **une autre LAPI** ;
   ne pas présumer qu'il correspond à la clé enregistrée sur TrueNAS.
   La présence d'une inscription `PFSENSE_FIREWALL` sans `last_pull`
   ne suffit pas à prouver la possession de sa clé.
3. **Ne provisionner le fichier** `root:root 0600`
   `/mnt/cpool/secrets/runtime/crowdsec/.env.secrets`
   que par un transfert approuvé, après vérification de l'identité
   et de l'absence de doublon. Aucune génération ou rotation de
   clé automatique.
4. **Exécuter `--check`** ; exiger zéro échec sur le secret,
   la classification Loki et l'enregistrement du bouncer.
5. **En fenêtre de migration approuvée**, faire pointer le seul
   bouncer pfSense vers `http://172.17.0.24:8084`, conserver
   sa remédiation active, retirer le moteur local, puis valider
   les deux `--accept` et le `last_pull` central.
   Préparer au préalable le retour à la configuration LAPI locale
   et documenter l'état des tables PF.

Le moteur TrueNAS fonctionne, mais **nous ne déclarons pas
la migration terminée** sans la preuve d'une décision centrale
réellement appliquée au niveau du pare-feu. Ne jamais tester
avec une IP de gestion critique ou introduire un ban factice
sans un plan de retour arrière.
## Current incident mitigation — 2026-10-10

The pfSense read-only diagnostic now proves the problematic path rather than
merely correlating it:

- Security Engine: stopped;
- firewall bouncer: still running;
- `crowdsec_pf_scan_stuck_lines=19213`;
- `max_failed_sent=19899999`;
- `max_attempts=19900000`;
- `max_sigclosed=0`.

That shape is consistent with a live leaky bucket whose input cannot accept the
event, causing the producer to busy-spin. CrowdSec upstream issue
[crowdsecurity/crowdsec#1519](https://github.com/crowdsecurity/crowdsec/issues/1519)
describes the same tight-loop failure mode. The current CrowdSec 1.8.1 source
still contains the non-blocking retry path, so upgrading alone is not treated as
a fix.

The central TrueNAS engine is therefore pinned to CrowdSec 1.8.1 **and**
temporarily removes only the offending Hub scenario through the official
container variable:

```text
DISABLE_SCENARIOS=firewallservices/pf-scan-multi_ports
```

The rest of `crowdsecurity/pfsense` remains installed. Do not re-enable the
pfSense Security Engine while this incident is open merely to regain this one
port-scan scenario.

## Runtime variables

The central engine can bootstrap without a bouncer secret. The optional
`/mnt/cpool/secrets/runtime/crowdsec/.env.secrets` file is loaded only when present, so a
missing secret file no longer makes the entire TrueNAS Compose model invalid.

The **TrueNAS runtime pool** is the service's operative secret source:
`/mnt/cpool/secrets/runtime/crowdsec/.env.secrets`. CrowdSec never needs
Vaultwarden to start, restart, redeploy or recover after an outage. The file is
optional during engine bootstrap but **required before accepting the pfSense
bouncer cutover**. A missing file is not proof that the engine itself is down.

Vaultwarden is an **optional operator-managed vault and recovery copy**, not
a mandatory live dependency or a prerequisite for an already-populated runtime
secret. Neither Compose nor the CrowdSec deployment/diagnostic scripts connect
to Vaultwarden to obtain the key. Preserve the runtime materialization on ZFS
with a separately controlled backup and recovery plan, especially while
Vaultwarden is offline.

### Complete the runtime-pool migration first

1. Confirm the local runtime path, restrictive permissions and presence of
   `BOUNCER_KEY_PFSENSE_FIREWALL` using the **read-only** diagnostic; never
   print the value or source the dotenv into the operator's shell.
2. If absent, restore or transfer the **previously issued bouncer key** into
   a private file through an approved, audited operator process. Optionally
   retrieve it from Vaultwarden if it exists there, but do not make this
   mandatory and do not invent or rotate it automatically.
3. Install the reviewed material into
   `/mnt/cpool/secrets/runtime/crowdsec/.env.secrets` with `root:root 0600`
   and directory `0700`. Avoid storing staging copies in shared `/tmp` or
   the Git checkout. The runtime file is an operating asset, not a Git artifact.
4. Run the read-only `--check` acceptance. Only then perform an explicitly
   authorized CrowdSec redeploy and pfSense bouncer reconfiguration from the
   workstation's existing administrative boundary.

The runtime file is the contract: it must define the container-facing
`BOUNCER_KEY_PFSENSE_FIREWALL`. The inventory manifest's legacy
`CROWDSEC_PFSENSE_BOUNCER_KEY` alias applies **only when importing** a secret
from the optional vault workflow. A registered CrowdSec bouncer does not
reveal its existing API key; if the key cannot be recovered, an explicitly
reviewed rotation is required, not an automated silent replacement.

```bash
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --runtime
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --check
# After a reviewed cutover, run --accept
```

Keep the pfSense-side verification separate: the workstation must acquire
the same credential via an approved provisioning channel, which may be the
vault or a controlled transfer. Never automatically copy a TrueNAS runtime
secret to the workstation, print it, pass it as a CLI argument, or grant TrueNAS
administrative SSH/API access to pfSense.

#### Optional vault backup or materialization (not a runtime prerequisite)

When Vaultwarden **is available**, the unprivileged operator may maintain a
recoverable copy with `scripts/secrets/materialize_runtime.py`, following
`docs/secrets-runtime-initialization.md`. If the CrowdSec item is missing in
the vault, **do not overwrite or remove the existing valid runtime file**.
Do not use the vault import as proof of the running bouncer identity; validate
the identity and cutover separately. Bitwarden CLI compatibility is relevant
only for this optional vault interaction, not normal CrowdSec operation.

Optional:

```text
CROWDSEC_LAPI_BIND_ADDRESS=172.17.0.24
CROWDSEC_LAPI_PORT=8084
CROWDSEC_METRICS_BIND_ADDRESS=172.17.0.24
CROWDSEC_METRICS_PORT=6060
SURICATA_LOG_DIR=/mnt/cpool/suricata/log
TZ=Europe/Paris
```

The LAPI port must remain reachable from trusted LAN hosts only. Do not publish TCP/8084 through pfSense, Cloudflare Tunnel, HAProxy or any Internet-facing ingress.

## TrueNAS Custom App deployment

The app may be installed before the bouncer secret exists. For the final
pfSense cutover, confirm the approved key is already materialized in
`/mnt/cpool/secrets/runtime/crowdsec/.env.secrets` before the controlled redeploy.
Register the missing Custom App with the canonical repository include:

```bash
CROWDSEC_WRAPPER="$(
  cat <<'EOF'
include:
  - /mnt/cpool/compose/nabla-compose/apps/crowdsec/compose.yml
EOF
)"

sudo midclt call -j app.create "$(
  jq -cn \
    --arg compose "${CROWDSEC_WRAPPER}" \
    '{
      app_name: "crowdsec",
      custom_app: true,
      custom_compose_config_string: $compose
    }'
)"
```

Use `app.redeploy crowdsec` only after `app.query` confirms the app exists.

Before changing pfSense, use the scoped repository deployer. Its default mode is
read-only. A missing bouncer credential is reported as a **cutover warning**,
not as a blocker for repairing the central TrueNAS runtime. Uncommitted changes
inside the CrowdSec deployment scope remain a blocking precondition.

```bash
sudo bash scripts/truenas/deploy-crowdsec.sh --check
sudo bash scripts/truenas/deploy-crowdsec.sh --apply
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --runtime

# Only after the canonical bouncer credential is materialized:
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --check
```

`--apply` reconciles **only** the TrueNAS CrowdSec Custom App; it does not
change pfSense, create/delete a bouncer, rotate a key or start the local pfSense
Security Engine. The post-reconcile `--runtime` gate proves the image, scenario
exclusion, LAPI/listeners and Loki acquisition independently from cutover
credentials.

The stronger `--check` gate additionally verifies the canonical bouncer-secret
contract and central `PFSENSE_FIREWALL` registration. It never creates a
bouncer, prints a key, redeploys an App or restarts a service.

After pfSense is switched to the remote LAPI, require the stronger acceptance
gate:

```bash
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --accept
```

`--accept` additionally requires that the pfSense firewall bouncer has polled
the central LAPI at least once.

The acceptance is intentionally split by trust boundary:

**On TrueNAS only** — validate the central engine/LAPI/Loki path and observe
`crowdsec_active_decisions`:

```bash
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --check
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --accept
```

TrueNAS never SSHes to pfSense.

**On the workstation only** — run the pre-cutover gate over the workstation's
existing SSH path. This checks that pfSense can reach the TrueNAS LAPI without
requiring the bouncer to have switched yet:

```bash
bash scripts/workstation/verify-crowdsec-pfsense.sh --preflight
```

The current legacy URL `http://172.17.0.1:8089` is a warning in preflight
mode. After changing the CrowdSec package settings, use the strict gate:

```bash
bash scripts/workstation/verify-crowdsec-pfsense.sh --accept
```

It verifies that the local Security Engine is absent, the firewall bouncer is
running, its `api_url` targets `http://172.17.0.24:8084`, and the
`crowdsec_blacklists` / `crowdsec6_blacklists` PF tables exist. Empty tables
are a warning by default because they are legitimate when no active ban exists.
When the TrueNAS diagnostic reports `crowdsec_active_decisions>0`, rerun the
workstation helper with `--require-nonempty-table`; an empty PF table then
becomes a failure. Do not run `docker exec` from the workstation.

## Migration from pfSense Large to Small

1. Keep the existing pfSense **firewall bouncer** running, but keep the local
   Security Engine stopped while the backpressure incident remains open.
2. Deploy the central TrueNAS CrowdSec container and verify that
   `firewallservices/pf-scan-multi_ports` is absent while the remaining
   `crowdsecurity/pfsense` collection is installed.
3. Recover the **existing approved** `PFSENSE_FIREWALL` bouncer key from an
   operator-controlled source, store it as the manifest field
   `CROWDSEC_PFSENSE_BOUNCER_KEY`, then materialize it for TrueNAS. If the key
   cannot be recovered, stop: creating/rotating a bouncer key is a separate
   explicitly approved transaction, not part of this cutover.
4. Run `diagnose-crowdsec-cutover.sh --check`; require zero failures before
   touching pfSense.
5. From pfSense, verify that `172.17.0.24:8084` is reachable over the trusted LAN.
6. In **Services > CrowdSec** on pfSense:
   - keep **Remediation Component** enabled;
   - keep **Log Processor** disabled;
   - keep **Local API** disabled;
   - configure the remote LAPI URL as `http://172.17.0.24:8084`;
   - configure the firewall bouncer with the shared key.
7. Save/apply, then run `diagnose-crowdsec-cutover.sh --accept` on TrueNAS and
   require a non-empty `last_pull` for `PFSENSE_FIREWALL`.
8. Confirm that pfSense still receives CrowdSec decisions in its PF table before
   considering the migration complete.

Rollback the **cutover**, not the incident mitigation: restore the previous
bouncer/LAPI settings from the backed-up pfSense configuration, but do not
automatically re-enable the local Security Engine. An emergency local-engine
rollback must first exclude `firewallservices/pf-scan-multi_ports` and must be
observed with bounded CPU/RSS and free-memory headroom.

## Detection sources

The central engine currently acquires:

- pfSense RFC5424 events from the **existing Loki stream**
  `{job="pfsense", device="pfsense"}`, produced by Alloy on TrueNAS;
- Suricata `eve.json` from `${SURICATA_LOG_DIR}`.

This intentionally avoids a second syslog receiver and avoids inventing a
`/mnt/cpool/logs/pfsense/*.log` persistence path that the observability stack
does not create. CrowdSec's Loki datasource starts at the current time, so
post-redeploy acceptance must generate/observe fresh pfSense activity.

The pfSense logs are parsed centrally on TrueNAS after migration, so pfSense
Small mode does not need to run the CrowdSec Log Processor.

## Motivation and current pfSense evidence

Before migration, pfSense CrowdSec was the dominant CPU consumer. `filter.log` generated a very high parse workload compared with useful events, and `firewallservices/pf-scan-multi_ports` repeatedly reported event-delivery backpressure with millions of failed send attempts. The firewall bouncer itself remained healthy and inexpensive, so the remediation component should stay on pfSense while the Security Engine/LAPI moves here.

## Validation after cutover

On TrueNAS:

```sh
docker exec crowdsec cscli metrics
docker exec crowdsec cscli decisions list
docker exec crowdsec cscli bouncers list
```

On pfSense:

```sh
pfctl -T show -t crowdsec_blacklists | head
ps auxww | grep -Ei '[c]rowdsec|[c]rowdsec-firewall-bouncer'
uptime
```

Expected result: the firewall bouncer continues polling and populating PF tables, while the `crowdsec` Security Engine process no longer runs locally on pfSense.

## pfSense tcsh-safe central LAPI authentication probe

pfSense admin's interactive shell is `tcsh`, not POSIX `sh`.
Never paste shell assignments such as `KEY=$(...)` directly into that
prompt. Use the repository script through an explicitly selected
POSIX interpreter **from the workstation checkout**:

```bash
ssh -T home.albandrieu.com 'sudo /bin/sh -s' < scripts/pfsense/check-central-crowdsec-bouncer.sh
```

The script reads the existing pfSense bouncer key locally, does **not**
print it or include it in curl argv, and reports only
`central_lapi_http=200` (authenticated) or a safe error/status.
It sends one GET for test address `192.0.2.1`, does not change
firewall configuration or PF tables, and may update LAPI polling
metadata. Run only on trusted pfSense via the workstation's authenticated
SSH channel. A 401/403 means the key is not accepted; do not infer
matching credentials from the names `pfsense-firewall` and
`PFSENSE_FIREWALL`.
