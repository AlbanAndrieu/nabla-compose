# Audit sécurité one-shot — nabla-compose

**Date :** 2026-10-01  
**Méthode :** Cloudflare `security-audit-skill`, profil `quick`  
**Source auditée :** `4fa9eb8d262bab437c99773475fcf84e489be863`  
**Statut :** **INCOMPLETE / couverture partielle**

> No confirmed vulnerabilities. Ce run source-first n'a pas exécuté de code cible,
> n'a sondé aucun runtime partagé et ne disposait pas d'un vérificateur indépendant.
> Il ne constitue donc ni un pentest complet ni une attestation d'absence de vulnérabilités.

## Résumé

Le dépôt présente plusieurs bons contrôles structurels : Actions GitHub épinglées par SHA,
permissions CI restreintes, `persist-credentials: false`, vérification SHA256 du binaire
Terragrunt et usage d'un Docker Socket Proxy restreint pour Doco-CD dans le Compose
workstation.

Le point prioritaire identifié concerne **Scanopy daemon**. Le Compose lui accorde
simultanément `network_mode: host`, `privileged: true` et le socket Docker brut.
L'upstream Scanopy courant indique en outre un bind par défaut `0.0.0.0:60073` et
une route `/api/initialize` publique avant la première initialisation. Le dépôt utilise
cependant `:latest`, et l'état/routage live n'a pas été inspecté : le point reste
**NEEDS VALIDATION**, sans sévérité attribuée.

## Findings confirmés

Aucun finding confirmé dans ce run partiel.

| Sévérité | Titre | Boundary | Résultat observé |
| --- | --- | --- | --- |
| — | Aucun | — | Aucune violation de frontière n'a été démontrée de bout en bout |

## NEEDS VALIDATION

| Lead | Boundary | Bloqueur principal | Prochaine validation sûre |
| --- | --- | --- | --- |
| Scanopy daemon first-initialization boundary | LAN/API daemon -> hôte TrueNAS/Docker | image `:latest`, état d'initialisation et firewall live non observés | relever passivement digest/listener/firewall/config, puis reproduire uniquement sur hôte jetable avec le digest exact |

Détail : [NEEDS-VALIDATION.md](./NEEDS-VALIDATION.md).

## Hardening notes

### Doco-CD : port webhook publié alors que le polling suffit

`docker-compose-truenas.yml` publie TCP/30080 mais ne configure pas
`WEBHOOK_SECRET`. L'upstream Doco-CD documente que le webhook est désactivé si ce
secret n'est pas défini, donc aucun bypass n'est établi. Puisque le polling est déjà
configuré, supprimer le port webhook tant qu'il n'est pas utilisé réduirait néanmoins
la surface réseau inutile. Si le webhook est activé ultérieurement, matérialiser
`WEBHOOK_SECRET` et limiter l'exposition au chemin réseau attendu.

### Scanopy : le suffixe `:ro` ne rend pas l'API Docker read-only

Le bind `/var/run/docker.sock:/var/run/docker.sock:ro` empêche surtout de modifier
l'entrée de filesystem ; il ne transforme pas le protocole Docker en API en lecture
seule. Si Scanopy supporte les appels requis via un proxy filtrant, préférer un
Docker Socket Proxy avec allowlist minimale. À défaut, documenter explicitement ce
socket comme frontière root-equivalent et limiter fortement l'exposition du daemon.

### NVM : installateur distant exécuté directement

`.envrc` épingle NVM à `v0.39.7`, ce qui est préférable à un `latest`, mais
stream toujours `install.sh` directement vers `bash`. Préférer le gestionnaire
déjà standardisé (`mise`) ou télécharger/vérifier un digest connu avant exécution.

### Tags d'images flottants

Plusieurs Compose historiques/optionnels utilisent encore `:latest`. Ce run ne
considère pas ce fait seul comme une vulnérabilité, mais les services à privilèges
élevés devraient être prioritaires pour un tag + digest immuable.

## Patterns positifs observés

- GitHub Actions importantes épinglées par SHA.
- `actions/checkout` avec `persist-credentials: false`.
- Permissions GitHub Actions limitées au besoin du job.
- Téléchargement Terragrunt avec vérification de `SHA256SUMS`.
- Doco-CD workstation configuré derrière `docker-socket-proxy` avec `POST: 0`.
- Secrets runtime matérialisés hors Git et contrat de moindre privilège documenté.
- Le chemin `eval` du sélecteur de réseau FastAPI est alimenté par un script Python
  interne qui ne produit que des CIDR/IP dérivés d'une liste codée en dur ; aucune
  entrée attaquante n'a été trouvée sur ce chemin.

## Couverture

Le ledger contient 5 unités quick : Scanopy, Doco-CD, GitHub Actions, bootstrap NVM
et génération/eval du réseau observer. La revue n'a pas exécuté de sandbox locale,
n'a pas couvert chaque service/app, et n'a pas réalisé le critic/final verifier
indépendant exigé par le skill pour une conclusion complète.

Artefacts :

- [architecture.md](./architecture.md)
- [coverage-ledger.json](./coverage-ledger.json)
- [findings.json](./findings.json)
- [FINDINGS-DETAIL.md](./FINDINGS-DETAIL.md)
- [NEEDS-VALIDATION.md](./NEEDS-VALIDATION.md)
- [run-metadata.json](./run-metadata.json)

## Limites explicites

- aucune requête offensive ou de validation envoyée au homelab ;
- aucun accès au socket Docker, TrueNAS, Talos, pfSense ou production ;
- pas d'exécution de code cible faute de sandbox OS répondant au contrat du skill ;
- pas de vérificateur indépendant/sub-agent dans cette session API-only ;
- validateurs Node du skill vendored mais non exécutés dans ce runtime.

Le prochain run complet doit partir de ce ledger, revalider le fingerprint Scanopy,
puis élargir la couverture plutôt que supposer que le reste du dépôt est « clean ».
