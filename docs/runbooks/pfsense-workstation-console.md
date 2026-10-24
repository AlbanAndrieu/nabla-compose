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

