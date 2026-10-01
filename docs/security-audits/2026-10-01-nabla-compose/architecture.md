# Architecture de l'audit one-shot

Date: 2026-10-01  
Cible: `AlbanAndrieu/nabla-compose`  
Mode: revue statique défensive, sans exécution de code cible ni mutation runtime.

## Frontières de confiance examinées

- TrueNAS SCALE / Docker Engine ;
- services Compose ayant accès au socket Docker ou au réseau host ;
- reverse proxy Traefik et surfaces d'administration ;
- interfaces opérateur exposées sur le LAN ;
- secrets runtime référencés par fichiers hors Git ;
- configuration de durcissement Compose.

## Surfaces prioritaires

1. accès à `/var/run/docker.sock` ;
2. `privileged`, `host network`, `SYS_ADMIN` et surfaces d'administration ;
3. publication de ports d'administration sans restriction d'interface ;
4. vérification TLS backend ;
5. outils d'administration disposant de shell/actions/MCP.

## Limites

Le workflow Cloudflare recommande un sandbox OS isolé et des validateurs
indépendants. L'environnement de cette exécution ne permet ni sandbox du
runtime TrueNAS ni validation indépendante par sous-agents. Les leads qui
nécessitent une preuve runtime restent donc `needs_validation`.
