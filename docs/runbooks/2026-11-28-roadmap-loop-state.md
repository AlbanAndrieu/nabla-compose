# Boucle roadmap du 28/11/2026 : état

Mode sprint ([skill](../../.agents/skills/nabla-roadmap-loop/SKILL.md)). PR de
consolidation nabla-compose : [#454](https://github.com/AlbanAndrieu/nabla-compose/pull/454)
(branche `fix/nexus-enabled-formats-20261127`, aucune PR sur la branche du checkout).
D'autres sessions travaillent en parallèle (site-alban, OpenClaw coder, pfSense, Vercel WAF #450) :
leurs périmètres ne sont pas repris ici.

## Compteur

| Passe | Début | Fin | Réconciliation |
|---|---|---|---|
| 1 | 28/11 | en cours | après la passe 3 |

## Journal

| Item | Statut | Preuve |
|---|---|---|
| H08 Nexus : dépôts APT/npm/PyPI | DEPLOYED (27/11) | plan/apply par format, plan final `No changes` ; ab96054b, ec609b05 (défaut `enabled_formats` figé) |
| H08 Nexus : identifiants Vaultwarden | fait (27/11) | `nabla/prod/nexus-infrastructure` (rôle `nabla-opentofu`, `security/*` 403) ; AWS_* de la clé Garage `opentofu` dans `infrastructure-bootstrap` ; plan du README `No changes` |
| Commit `drop the workstation Grafana service` resté sans PR | replié | 277fff1b (cherry-pick de d1f89735) |
| Snapshots : tâches 17-19 de `cpool` doublent les 62 datasets classés | DEPLOYED (nexus3, bitcoind) | fe3e85eb (ligne `doubled` du plan, test) ; exclusion 17-19 + purge : nexus3 931 Mio → 36 Mio, bitcoind 39,1 Gio → 0, dernière `auto-` gardée |
| Dérive OpenTofu : racine `nexus` enrôlée | DEPLOYED | compte lecture seule `nabla-opentofu-drift` (rôle `nabla-opentofu-read`), `nexus.env` root 0600 ; verdict `DRIFT` (6 destructions) sur `origin/master` 8aab83f6, attendu `IN_SYNC` après fusion de #454 |

## Questions parquées

- Fusion de #454 (propriétaire) : sans elle, `OpenTofuDrift` se déclenche chaque jour à 09:00.
- Mot de passe `admin` de Nexus à changer et à retirer de `~/.m2/settings.xml` (propriétaire).
- Doublons de snapshots des 60 autres datasets classés : exclure de 17-19 et purger classe par classe (`critical` compris) ou garder la double couverture ?
- Après le 01/12 04:00 : supprimer la dernière `auto-` historique de nexus3 et bitcoind une fois le premier point mensuel de classe créé.
