# Passe roadmap nabla-compose — 19/11/2026

## Porte : CI master / just offline
- CI `master` : tous workflows PASS (security, CodeQL, Semantic Release)
- `just offline` : PASS syntaxique, format, recette, mais NOT VERIFIED pour hooks, scanners, gates L2/L3 (offline)

## Items traités (3)
- Redis : mot de passe dans env runtime, interdit .env legacy (CODED, `apps/redis/compose.yml`) ; healthcheck sécurisé
- Dozzle : docker API read-only, shell/actions coupés, log rotate, conformité ratchet (CODED, `apps/dozzle/compose.yml`)
- CrowdSec bouncer Traefik : plugin stream opt-in, middleware attachable, logs rotate, policy bouncer (CODED, `apps/traefik/dynamic/crowdsec.yml`) — relation CrowdSec/Traefik confirmée

## Tests
- Ratchet mémoire/logs : tous tests structurels passent, nombre sans mem_limit conforme, logs rotate partout, aucun nouveau .env legacy
- test_compose_resource_ratchet.py : PASS
- test_compose_legacy_env_ratchet.py : PASS

## Consolidation — boucles
- Boucle 1 : chaque item touché marqué CODED, healthcheck, hooks .env et logging ratchet
- Boucle 2 : aucun doublon, debt legacy en .env en régression, suppression pfSense anesthésie routes WAN
- Boucle 3 : recommandations :
    1. Poursuivre migration secrets runtime pour tous services
    2. Généraliser rotation logs et mem_limit, tracker exceptions
    3. Continuer la coupure effective des routes WAN, confirmer suppression pfSense

## URL PR Draft
(à compléter après push et PR)

## Blocages
- RUNTIME : 1 (pfSense, routes WAN et HAProxy retirés, migration physiologique)
- DÉCISION : 1 (suite migration secrets, debt legacy .env)

## Questions restantes
1. Valider la gestion des routes WAN après suppression pfSense (Netgate 1100 gelé, Freebox routeur)
2. Déploiement CrowdSec bouncer sur plus de routes : quels services visés en priorité ?
3. Confirmation opérateur pour migration finale .env legacy et refactoring catalogue
