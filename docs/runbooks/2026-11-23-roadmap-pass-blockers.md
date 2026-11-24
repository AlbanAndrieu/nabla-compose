# Passe de roadmap du 23/11/2026 : bloqueurs et questions

Aucun commit code cette passe. Consolidation roadmap, statuts et recommandations.

## Blocages principaux

| Item             | Classe     | Blocage                                                          | Question ou commande de réception                 |
|------------------|-----------|------------------------------------------------------------------|---------------------------------------------------|
| Dependency-Track | RUNTIME    | Secret `DT_DATASOURCE_PASSWORD` non accessible depuis devbox      | Tester la recette sur Workstation, poste Vaultwarden |
| H17 Site         | RUNTIME    | Recette réelle sur SHA déployé non faisable depuis devbox         | Lancer la vérification depuis le poste, noter SHA   |
| Amass externe    | DÉCISION   | Campagne active GitHub non déclenchée ce week-end                 | Attendre confirmation opérateur, artefact         |

## Questions restantes

1. Qui peut exposer le secret runtime Dependency-Track côté Vaultwarden sur Workstation ?
2. SHA de l'App Site sur le poste, comment coordonner validation du catalogue ?
3. Peut-on lancer Amass externe en découverte active ce lundi ?
