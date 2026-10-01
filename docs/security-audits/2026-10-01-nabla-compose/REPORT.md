# Rapport d'audit sécurité one-shot — nabla-compose

_Date: 2026-10-01_  
_Méthode: skill Cloudflare `security-audit`, revue statique défensive._

## Résumé

Aucune vulnérabilité n'est marquée **confirmed** dans ce run, car le skill
exige une validation indépendante et un sandbox OS pour exécuter les preuves
actives. Trois leads source-grounded sont conservés en **needs_validation**.

### Priorité 1 — frontière Docker

Le risque le plus important est l'accès direct au socket Docker dans des
services qui n'ont pas nécessairement besoin de la totalité de l'API. Le cas
Scanopy est prioritaire: `privileged: true`, `network_mode: host` et socket
Docker direct sont cumulés, alors que le repository possède déjà un
`docker-socket-proxy` configuré avec `POST=0`.

### Priorité 2 — dashboard Traefik insecure

`apps/traefik/compose.yml` active `--api.insecure=true` et publie le port
`8080`. Le repository possède déjà un routeur `api@internal` avec Basic Auth;
le port insecure doit donc être considéré comme une voie parallèle à supprimer
si le test LAN confirme son accessibilité.

### Priorité 3 — Dozzle administrateur

Dozzle combine socket Docker direct, actions, shell et MCP. Ce n'est pas traité
comme vulnérabilité confirmée sans preuve de contournement d'authentification,
mais la concentration de privilèges mérite une réduction immédiate de surface.

## Hardening observé, non classé comme vulnérabilité

- Traefik utilise globalement
  `--serversTransport.insecureSkipVerify=true`. Le commentaire l'explique par
  Proxmox, mais le réglage est global. Il faudrait le remplacer par un transport
  dédié au seul backend qui en a besoin et conserver la vérification TLS pour
  les autres backends HTTPS.
- Plusieurs autres services montent directement le socket Docker
  (par exemple Dockhand, OpenHands, Traefik). Pour les véritables interfaces
  d'administration Docker, le privilège peut être intentionnel; leur exposition
  et leur authentification doivent cependant être documentées comme frontière
  d'administration, pas comme simple dépendance technique.
- Les images `:latest` restent présentes dans plusieurs Apps. C'est une dette
  de reproductibilité/supply-chain, mais pas une vulnérabilité autonome.

## Recommandations de remédiation

1. Créer une politique repository: aucun nouveau socket Docker direct sans
   justification explicite et test contractuel; privilégier
   `docker-socket-proxy`.
2. Migrer Scanopy vers un proxy Docker strictement read-only et tester la
   découverte.
3. Désactiver `--api.insecure=true` dans Traefik et supprimer le port 8080
   direct après validation de `api@internal` via TLS + auth.
4. Réduire Dozzle à la fonctionnalité réellement nécessaire: logs seuls par
   défaut; actions/shell/MCP activés séparément si un besoin opérateur est
   documenté.
5. Remplacer `serversTransport.insecureSkipVerify=true` global par un
   transport nommé limité au backend auto-signé.

## Validation restante

Les tests runtime doivent être réalisés sur le LAN ou dans un sandbox dédié et
ne doivent pas utiliser GitHub Actions comme boucle de diagnostic. Le rapport
sera révisé après preuve runtime; jusqu'alors les trois entrées restent
`needs_validation`.

## Fichiers de preuve

- `architecture.md`: périmètre et frontières de confiance;
- `findings.json`: enregistrements structurés compatibles avec la sémantique
  du skill Cloudflare;
- `.agents/skills/security-audit/`: copie vendored du skill utilisé.
