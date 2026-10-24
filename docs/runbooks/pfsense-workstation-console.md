# Console pfSense — diagnostics depuis la workstation

Objectif : un affichage clair dans le terminal, sans changer les collecteurs ni les actions sur le Netgate 1100.

## Contrat de sortie

| Contexte | Présentation |
| --- | --- |
| Workstation avec TTY | Sections 🔎, statut ✅ / ⚠️ / ❌, couleurs et résumé |
| `PFSENSE_OUTPUT=compact` | Vue condensée même hors TTY ; ANSI seulement si autorisé |
| `PFSENSE_OUTPUT=verbose` | Toutes les lignes affichables ; le syslog brut reste masqué |
| `PFSENSE_OUTPUT=raw` | Sortie exacte du collecteur, sans en-tête ni résumé |
| Pipe / fichier / CI | Par défaut, sortie exacte pour scripts, CSV et JSON |
| `NO_COLOR=1`, `TERM=dumb`, `PFSENSE_COLOR=never` | Pas de séquences ANSI |

Les niveaux de couleur ne certifient jamais la santé du service. Les erreurs explicites restent visibles, même si une section dépasse 14 lignes. Le compteur OOM représente des mentions, pas nécessairement des incidents uniques. Une valeur `unknown` reste inconclusive.

## Commandes de validation, une action par étape

1. Exécuter les tests hors réseau :

```bash
just pfsense-console-test
```

2. Exécuter les contrats pfSense existants :

```bash
just pfsense-unbound-wifi-test
```

3. Lancer le diagnostic prioritaire en lecture seule :

```bash
bash scripts/pfsense/diagnose-pfblocker-unbound-whatsapp.sh --check
```

4. Si les détails sont nécessaires, afficher la vue longue :

```bash
PFSENSE_OUTPUT=verbose bash scripts/pfsense/diagnose-pfblocker-unbound-whatsapp.sh --check
```

Ne pas partager une sortie `raw` sans vérifier les données privées. La mise en forme ne remplace pas un mécanisme de rédaction des secrets.

## Périmètre

Le module `scripts/pfsense/console.sh` fonctionne **uniquement sur la workstation**. Les commandes distantes continuent d'utiliser `/bin/sh`, sans installation ni coloration sur pfSense. Les diagnostics SSH Unbound, Snort, pflow, mémoire, split DNS, Prometheus, WhatsApp et CrowdSec Small sont raccordés.

`audit-posture.sh` possède déjà une table colorée et une sortie `--json`. `diagnose-recover.sh` possède déjà un résumé coloré et un rapport privé. Les scripts natifs `check-central-crowdsec-bouncer.sh` (POSIX sh) et `manage-api-identities.php` (PHP) ne chargent pas ce module workstation. Le wrapper `verify-crowdsec-small.sh` délègue au contrôle workstation.

Ne pas supprimer ni modifier les codes retour des sondes. Ne pas lancer de CI payante sur la PR Draft.


## Lecture du relevé du 25 octobre à 00:03 CEST

Contrats local-first transmis par l'opérateur : `pfsense-console-test`
7 tests PASS et `pfsense-unbound-wifi-test` 32 tests PASS.
La gate globale au HEAD GitHub exact reste distincte.

Le contrôle montre **15 lignes d'OOM noyau distinctes**, imprimées une seconde
fois dans les archives : l'ancienne console affichait 30 mentions et
30 erreurs. La console déduplique maintenant les horodatages précis et
présente des **événements OOM historiques**, pas des pannes actuellement
actives. Le nombre de minutes concernées n'est pas une preuve de causalité.

Le processus Unbound actif portait le PID `12710`, avec
démarrage déclaré à **23:38:57 le 24 octobre**. Le relevé ne rapporte
pas d'OOM au moment exact de ce démarrage ; ne pas inventer sa cause.
La mémoire `free + inactive` valait
`(28172 + 8568) × 4096 / 1048576 = 143,5 Mio` ; ce
n'est ni la mémoire réellement allouable ni une mesure à 02:09.

Le rendu classe désormais les journaux RFC5424 sans publier leurs messages
bruts : conflit de bind Unbound, notice de redémarrage, sortie du module
DNSBL Python, échec DNSSEC, alerte de tampon socket et lifecycle CrowdSec.
En cas de message non reconnu, le mode compact le masque avec un décompte ;
le mode verbose affiche **uniquement l'horodatage et la catégorie**.

Aucune différence de PID, de journal ou d'horodatage ne prouve que Snort ou
CrowdSec a provoqué un OOM. Ne pas modifier Snort, DNSBL, CrowdSec ni
relancer Unbound avant une corrélation mesurée.


## Relevé du 25 octobre à 00:12 CEST — P0 Unbound

Onze tests de console passent dans le checkout opérateur. Unbound a
changé de PID entre 23:38:57 (24 octobre) et 00:04:56 (25 octobre).
À 00:12, le PID observé est 2135. Cela atteste un nouveau démarrage,
mais **pas** un nouveau OOM. Ne pas attribuer le démarrage à Snort
ou à pfBlockerNG sans preuve de l'action réellement déclenchante.

Le relevé indique free+inactive = 119,4 Mio, load average
4,56 / 4,47 / 3,48, CrowdSec engine ~75 772 Kio RSS,
et un helper php_pfb ~42 832 Kio RSS. Ces observations ne sont
ni simultanées aux OOM nocturnes ni des mesures de mémoire exclusive.
Les compteurs Unbound ont été réinitialisés par le nouveau processus :
ne pas interpréter leurs valeurs cumulées comme une série continue.

La console compacte regroupe maintenant les OOM historiques par minute,
en distinguant le nombre de processus tués du nombre d'incidents.
La vue verbose conserve les horodatages distincts (sans doublons).
Les événements pfBlockerNG incluent désormais la date locale uniquement
si le préfixe du journal est reconnu ; sinon timestamp=unknown.
Les domaines privés, téléchargements et tokens ne sont pas affichés.

### Transition de l'heure locale, 25 octobre 2026

Le 25 octobre, 03:00 CEST est suivi de 02:00 CET : il existe
deux 02:09 locaux (02:09+02:00 et 02:09+01:00).
FreeBSD cron peut appliquer un traitement dédié de ce changement
selon les options du daemon, dont -s. Une double exécution Snort
n'est **pas démontrée** : vérifier les exécutions réelles, en
lecture seule, à 00:09Z et 01:09Z puis les journaux Snort.
Les démarrages Unbound à 23:38 et 00:04 précèdent la transition.

Note DST : pour le regroupement console, la clé de minute conserve maintenant
le décalage UTC (`02:10 +02:00` et `02:10 +01:00` restent deux minutes
réelles distinctes). Un journal sans décalage est affiché avec
`(offset unknown)` : aucun fuseau n'est inventé.
