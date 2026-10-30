# CrowdSec pfSense Small — preuve d'application et de retrait PF

> Procédure de réception P0 — 27 octobre 2026. **Aucune commande de ce
> document n'est exécutée par l'agent.** Les deux étapes de mutation
> ci-dessous requièrent une décision explicite de l'opérateur.

## État établi

- LAPI centrale TrueNAS : `172.17.0.24:8084`; bouncer pfSense actif,
  authentifié (HTTP 200), moteur CrowdSec local pfSense arrêté.
- Dernier diagnostic central : **0 décision active**.
- Bouncer pfSense observé dans `cscli bouncers list` :
  `PFSENSE_FIREWALL@172.17.0.1`, IP `172.17.0.1`, type
  `crowdsec-firewall-bouncer`, `last_pull=2026-10-27T22:35:27Z`.
  C'est distinct de `PFSENSE_FIREWALL` (appel `curl` TrueNAS
  `172.17.0.24`, `last_pull=21:46:28Z`) et de l'ancien
  `pfsense-firewall` (dernier appel le 25 septembre).
  L'identité observée prouve un accès LAPI attribuable à pfSense
  selon l'IP et le User-Agent, **sans prouver une application PF**.
- La nouvelle réception `--accept` contrôle strictement ces métadonnées
  sur l'enregistrement suffixé, sans mutation, plutôt que d'attribuer le
  `last_pull` du client `curl` à pfSense.
- Les tables `crowdsec_blacklists` et `crowdsec6_blacklists` contiennent
  des milliers d'entrées historiques. Leur présence, leur variation
  (4 085 puis 4 074) et un `last_pull` ne prouvent pas qu'une décision
  **nouvelle** de TrueNAS est appliquée dans PF. Un probe d'authentification
  peut lui-même actualiser la date de `last_pull`.

## Première réception LIVE — 28 octobre 2026

- **Gate local workstation PASS :** `just crowdsec-pf-natural-test`
  15/15 ; `just crowdsec-bouncer-config-test` 46/46.
- **Baseline effectuée en lecture seule :**
  `crowdsec_pf_baseline=READY source_mode=LIVE pf_networks=4016 natural_bans=0`.
  La référence historique est maintenant enregistrée sur la workstation.
- **Première observation :**
  `pf_decision_cycle=NOT_VERIFIED reason=NO_ELIGIBLE_NEW_NATURAL_BAN`.
  Le collecteur est prêt, mais il n'a pas encore observé de nouvelle
  décision centrale éligible. **Ne pas conclure à une panne du bouncer.**

**Action suivante uniquement :** depuis le même checkout workstation,
exécuter `just crowdsec-pf-natural-observe` lors d'une nouvelle
décision naturelle. **Ne plus exécuter `baseline`**, sauf procédure
d'initialisation d'une nouvelle campagne avec archivage privé préalable.
Ne jamais transmettre le fichier d'état à la PR, à GitHub Actions ou
dans un échange de diagnostic : il contient des adresses IP historiques.

## Option A automatisée — suivi naturel sans mutation (28 octobre 2026)

La workstation est l'**orchestrateur de lecture** : elle interroge TrueNAS
via SSH (`172.17.0.24:9922`) et pfSense séparément via SSH.
**TrueNAS ne contacte pas pfSense en SSH.** Aucune commande ne crée
ni supprime de décision, et aucun `pfctl -T add/delete/flush` n'est lancé.

Avant toute observation, établir une baseline **sur la workstation**,
avec la clé SSH vers TrueNAS et les droits `sudo -n docker exec`
pour la seule lecture centrale :

```bash
cd ~/w/nabla-compose
git pull --ff-only

just crowdsec-pf-natural-test
just crowdsec-pf-natural-baseline
```

La commande `baseline` lit `cscli decisions list --limit 0 -o json`,
`pfctl -t crowdsec_blacklists -T show` et l'état pfSense Small
(bouncer actif, ancien moteur local absent).
Elle mémorise les identifiants de décisions et le contenu initial de
la table PF pour **exclure les entrées historiques**.
Le fichier de preuve reste **local à la workstation** dans
`~/.local/state/nabla-compose/crowdsec-pf-natural-cycle.json`
(dossier `0700`, fichier `0600`, adresses IP potentiellement sensibles).
Il n'est jamais envoyé dans GitHub ni inclus dans les journaux partagés.
Une baseline existante **n'est pas écrasée**.

Lors des observations suivantes, sur **la même workstation** :

```bash
just crowdsec-pf-natural-observe
```

Relancer après l'apparition d'une nouvelle décision naturelle, pendant
sa durée, puis après sa disparition. **Aucune tâche de fond n'est
installée par la PR.** Pour être éligible, la décision doit provenir
du moteur (`origin=crowdsec`), être de type `ban`, de portée
`Ip`, cibler une IPv4 globale, être non simulée, et ne pas figurer
dans la baseline centrale/PF. L'application peut être observée
immédiatement ou lors d'un relevé ultérieur. Le verdict `PASS` exige :

1. décision nouvelle absente des décisions et tables historiques ;
2. même IP observée simultanément dans la LAPI et la table PF ;
3. décision disparue de la LAPI **et** correspondance PF disparue ;
4. bouncer pfSense toujours actif, ancien moteur toujours absent.

`NOT_VERIFIED` est **normal** si aucune décision n'est encore née.
D'autres états indiquent `PF_APPLICATION_NOT_OBSERVED`,
`PF_APPLIED_AWAITING_REMOVAL`,
`PF_STILL_PRESENT_AFTER_LAPI_REMOVAL` et
`BAN_EXPIRED_BEFORE_PF_PROOF`. Les IP des candidates ne sont
**pas affichées par défaut** : elles sont étiquetées par un
hash salé propre à cette baseline. L'option `--reveal-ip` existe
pour un diagnostic local, sans partager son résultat.

En cas de refus SSH/`sudo -n` TrueNAS, la commande échoue avec
`NOT_VERIFIED` (code 2). Ne pas assouplir les droits sudo
globalement. Une voie alternative permet d'utiliser des
snapshots transférés de manière sécurisée via
`--central-json`, `--pf-table-file` et `--pf-health-file`,
mais **ce mode OFFLINE ne constitue jamais une preuve runtime** :
il rend `SIMULATED_PASS_NOT_RUNTIME_VERIFIED` au mieux et ne
peut pas être mélangé avec une baseline LIVE.

<details>
<summary>Exécution directe et paramètres SSH (workstation)</summary>

```bash
python3 scripts/workstation/observe-crowdsec-pf-decision.py baseline \
  --truenas-ssh albandrieu@172.17.0.24 --truenas-port 9922 \
  --pfsense-ssh home.albandrieu.com

python3 scripts/workstation/observe-crowdsec-pf-decision.py observe
```

Variables `CROWDSEC_TRUENAS_SSH`,
`CROWDSEC_TRUENAS_SSH_PORT`, `PFSENSE_SSH_TARGET`,
`PFSENSE_SSH_PORT` acceptées. Les deux accès SSH utilisent
`BatchMode=yes`, des délais bornés et aucune demande de mot
de passe interactive.

</details>

**Limites :** l'existence d'une IP dans une table PF ne prouve pas
qu'une règle PF bloque réellement un paquet WAN. Une validation
ultérieure de la référence à cette table dans les règles actives
et, si nécessaire, un test depuis un WAN indépendant restent requis.
Une corrélation temporelle ne prouve pas non plus à elle seule
la causalité du bouncer.

## Option A — observation naturelle, sans mutation (préférée)

1. **TrueNAS** : attendre une décision `ban` IPv4 réellement nouvelle ;
   consulter `sudo docker exec crowdsec cscli decisions list -o json`.
   Consigner l'IP exacte, le type, l'origine et l'heure **sans données
   personnelles**. Si aucune décision n'existe : `NOT_VERIFIED`.
2. **Workstation → pfSense** : vérifier cette IP précise, sans exporter
   la liste des autres adresses PF :

   ```bash
   ssh -T home.albandrieu.com \
     'pfctl -v -t crowdsec_blacklists -T test <IP_IPV4_OBSERVEE>'
   ```

   Le marqueur verbose `M` confirme une correspondance dans la table.
   Il ne prouve pas à lui seul que toutes les règles firewall référencent
   correctement cette table.
3. Attendre l'expiration de cette décision, puis vérifier sa suppression
   du niveau LAPI et de la table PF. L'expiration/résolution d'une décision
   naturelle peut être suivie sans provoquer de trafic hostile.

## Incident 30 octobre — test synthétique non vérifié (PR #295)

**Preuve opérateur :** tests CrowdSec 61/61 PASS, précontrôle
`initial_lapi=ABSENT initial_pf=ABSENT pf_bouncer=RUNNING`,
puis `--apply` : `synthetic_cleanup=NOT_VERIFIED` et
`reason=NotVerified`, sans identifiant de décision affiché.
**Aucune conclusion d'absence ou de nettoyage n'est possible
sur la base de ce seul résultat.**

Cause de code **confirmée** dans CrowdSec 1.8.1 : la commande
`cscli decisions list -o json` renvoie `[alert{decisions:[...]},...]`.
L'ancienne lecture supposait `[decision,...]` et pouvait ignorer
l'IP en précontrôle, puis ne pas retrouver l'ID de suppression.
Le correctif du 30/10 normalise les décisions imbriquées, rejette
toute structure inconnue et exige un `scenario` correspondant
exactement à la raison aléatoire créée pendant ce test avant de
supprimer un ID. Le délai d'expiration reste **5 minutes** ; le
nettoyage sous interruption ne constitue pas une garantie.

**Procédure de reprise — depuis la workstation, sans mutation :**

```bash
cd ~/w/nabla-compose
git pull --ff-only
just crowdsec-pf-synthetic-test
just crowdsec-bouncer-config-test
just crowdsec-pf-synthetic-inspect
```

L'inspection affiche un nombre de décisions LAPI correspondant à
`203.0.113.77`, leurs **IDs** (sans exporter le JSON brut), l'état
de correspondance dans PF et celui du bouncer. Si
`lapi_matches=0 pf_present=false`, aucun vestige actif du test
n'est détecté au moment de la lecture, mais cela ne prouve pas
l'application/retrait lors du premier essai. Si une décision ou
une entrée PF subsiste, **NO-GO** pour une nouvelle création :
conserver les preuves privées, identifier l'ID et la provenance,
puis utiliser exclusivement la reprise ciblée ci-dessous.

**Après inspection propre**, le précontrôle `just
crowdsec-pf-synthetic-preflight` peut être relancé. N'exécuter
le test `--apply` à nouveau que par décision explicite de
l'opérateur ; aucune recette Just ne le lance.

**Impact sur l'option A :** le collecteur naturel utilisait
la même hypothèse JSON et a été corrigé. Son fichier de baseline
historique `crowdsec-pf-natural-cycle.json` doit être conservé
comme archive, **pas utilisé pour clôturer la preuve PF**.
Une nouvelle baseline `crowdsec-pf-natural-cycle-v2.json` est
nécessaire à l'observation naturelle à jour, sans toucher à v1.

## Option B — test synthétique réversible et borné (validation explicite)

**Test actif** : crée temporairement une seule décision CrowdSec sur
`203.0.113.77` (plage documentaire TEST-NET-3) pendant **5 minutes
maximum**, puis tente une suppression **par identifiant unique**.
Ce test n'est pas une décision naturelle ; son résultat est nommé
`SYNTHETIC_PF_DECISION_CYCLE_PASS` et ne modifie pas la baseline naturelle.

**Préconditions et NO-GO :**
- Exécuter **sur la workstation**, dans le checkout `nabla-compose`
  à jour. Les deux connexions SSH sont indépendantes :
  TrueNAS `172.17.0.24:9922` et pfSense via l'alias configuré.
- Le firewall bouncer pfSense est actif ; l'ancien moteur pfSense est
  arrêté. Les droits `sudo -n docker exec crowdsec cscli` sont nécessaires
  depuis la workstation.
- Aucune décision LAPI existante sur l'IP ou sur un intervalle la
  couvrant, **et aucune entrée PF** (même sous forme de CIDR) couvrant
  l'IP. Sinon **NO-GO** avant toute mutation.
- Le moteur ou le bouncer peut ignorer les adresses réservées
  TEST-NET-3. Cela donne **NOT_VERIFIED**, pas une migration en panne.
- Les règles PF qui réfèrent à `crowdsec_blacklists` et le blocage WAN
  effectif restent un contrôle distinct.

### 1. Tests hermétiques (aucune connexion au homelab)

```bash
cd ~/w/nabla-compose
git pull --ff-only
just crowdsec-pf-synthetic-test
just crowdsec-bouncer-config-test
```

### 2. Précontrôle LIVE en lecture seule

```bash
just crowdsec-pf-synthetic-preflight
```

Résultat attendu : `synthetic_preflight=PASS initial_lapi=ABSENT
initial_pf=ABSENT pf_bouncer=RUNNING`. En cas d'échec, **arrêter**.
Le précontrôle doit être refait automatiquement juste avant le test actif.

### 3. Exécution active unique — confirmation explicite

L'appel ci-dessous est la **seule action mutatrice autorisée** dans cette
procédure. Elle ne modifie que la liste de décisions LAPI et laisse PF
être mis à jour par son bouncer normal. Ne pas lancer si l'on ne souhaite
pas créer le bannissement temporaire.

```bash
python3 scripts/workstation/smoke-crowdsec-pf-synthetic.py \
  --apply --confirm SYNTHETIC-203.0.113.77
```

Le script :
1. répète le contrôle de sécurité LAPI/PF avant création ;
2. crée un `ban` d'une durée de **5m** sur `203.0.113.77` ;
3. relève **l'ID** du ban et recherche l'IP dans
   `crowdsec_blacklists` par lectures SSH (CIDR inclus) ;
4. dans une clause `finally`, supprime **uniquement cet ID**
   avec `cscli decisions delete --id` ;
5. recherche la disparition de la décision **et** de l'IP dans PF,
   en vérifiant également l'état Small du bouncer.

Les deux périodes de polling sont bornées et les retours d'erreur
ne permettent jamais d'afficher un faux succès. `Ctrl+C` et
`SIGTERM` déclenchent une tentative de nettoyage.
**SIGKILL, coupure brutale ou SSH indisponible ne garantissent pas
l'exécution du nettoyage** : la décision a un TTL de 5 minutes.

Verdicts :
- `synthetic_cycle=SYNTHETIC_PF_DECISION_CYCLE_PASS` :
  ajout LAPI, apparition PF, suppression de cet ID et disparition PF observés ;
- `synthetic_cycle=NOT_VERIFIED` :
  absence d'application ou de retrait, preuve incomplète,
  ambiguïté d'ID ou échec réseau. Ne pas assimiler à une panne moteur.

### 4. Si le nettoyage est incertain

Ne **jamais** supprimer toutes les décisions pour une IP par
`cscli decisions delete --ip` : cela pourrait effacer une autre décision.
Ne pas utiliser `--all`, `pfctl -T flush`, rotation de clés ou
redémarrage du moteur pour régler cette preuve.

Lire d'abord, **sur TrueNAS** :

```bash
sudo docker exec crowdsec cscli decisions list --ip 203.0.113.77
```

Si la décision est **certainement celle du test** et que son identifiant
est connu (affiché sous `synthetic_lapi=CREATED decision_id=...`),
l'opérateur peut effectuer une reprise ciblée sur TrueNAS :

```bash
sudo docker exec crowdsec cscli decisions delete --id <ID_UNIQUE_DU_TEST>
```

Vérifier ensuite l'absence de cette décision et l'absence de
`203.0.113.77` dans PF. Si l'ID est incertain, **ne rien effacer** et
attendre le TTL de 5 minutes en contrôlant l'expiration.

## Verdict et limites

**`PF_DECISION_CYCLE_PASS`** exige :
1. aucune décision et aucune correspondance PF au départ ;
2. décision centrale créée/observée, puis correspondance de **cette même IP**
   dans PF après propagation ;
3. décision supprimée/expirée puis disparition de **cette même IP** de PF ;
4. bouncer toujours opérationnel ; moteur pfSense toujours arrêté.

Sinon `PF_DECISION_CYCLE_NOT_VERIFIED`, avec le stade exact manquant.
La vérification reste séparée de l'audit HAProxy/DNS/Cloudflare.
Un match de table ne démontre pas à lui seul le blocage d'un paquet WAN :
les règles PF actives et, si nécessaire, une sonde depuis une vraie source
WAN doivent être vérifiées indépendamment.

## Références

- [CrowdSec — Gestion des décisions](https://docs.crowdsec.net/u/user_guides/decisions_mgmt/)
- [CrowdSec 1.8 — `cscli decisions list`](https://docs.crowdsec.net/docs/cscli/cscli_decisions_list/)
- [pfctl — `-T test` et marqueur `M`](https://man.openbsd.org/pfctl.8)
- [pfSense CrowdSec Small](https://docs.crowdsec.net/docs/getting_started/install_crowdsec_pfsense/)
