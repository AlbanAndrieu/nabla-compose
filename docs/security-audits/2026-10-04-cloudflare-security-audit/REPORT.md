# Audit sécurité one-shot — nabla-compose

**Date :** 2026-10-04  
**Méthode :** Cloudflare `security-audit-skill`, profil `quick`  
**Source auditée :** `e8acbc56121e520359824e6e353e611ee573fea3`  
**Run précédent :** `2026-10-01-cloudflare-security-audit`  
**Statut :** **INCOMPLETE / partial source review / couverture partielle**

> No confirmed vulnerabilities. Aucun runtime partagé n'a été sondé et cette
> session ne fournit ni sandbox OS complète ni vérificateur indépendant. Le
> rapport ne constitue donc ni un pentest complet ni une attestation d'absence
> de vulnérabilités.

## Résumé

Le run du 1er octobre a été réutilisé conformément au contrat du skill. Les
cinq surfaces source précédemment couvertes n'ont pas changé entre
`4fa9eb8…` et `e8acbc56…`; elles ont donc été revalidées comme couverture
antérieure sur source identique plutôt que relancées artificiellement.

Le lead **Scanopy daemon** reste `needs_validation` : le dépôt continue de lui
accorder `network_mode: host`, `privileged: true` et le socket Docker brut,
avec une image `:latest`. La révision réellement déployée, l'état
d'initialisation et le filtrage réseau live ne sont pas prouvés par Git.

Les nouveaux changements depuis le run précédent concernent surtout les outils
d'audit du dépôt, le reboot/recovery TrueNAS et le diagnostic pfSense. La revue
source-first de ces scripts privilégiés n'a pas établi de nouvelle violation de
frontière démontrable dans ce profil quick.

## Findings confirmés

Aucun finding confirmé.

| Sévérité | Titre | Résultat |
| --- | --- | --- |
| — | Aucun | Aucune violation de frontière démontrée de bout en bout |

## NEEDS VALIDATION

| Lead | Bloqueur | Validation sûre |
| --- | --- | --- |
| Scanopy daemon first-initialization boundary | digest live, état d'initialisation, listener/firewall | relever passivement digest/listener/firewall/config puis reproduire uniquement avec le digest exact sur hôte jetable |

Détail : [NEEDS-VALIDATION.md](./NEEDS-VALIDATION.md).

## Évolutions positives depuis le run précédent

- le skill Cloudflare est maintenant vendored et versionné dans le dépôt ;
- ses validateurs JSON sont couverts par un contrat Pre-commit local ;
- les opérations de reboot TrueNAS ont gagné des gardes transactionnels et de
  convergence supplémentaires ;
- les diagnostics pfSense séparent mieux preuves read-only et mutations
  explicitement demandées ;
- le projet conserve l'approche local-first et n'utilise pas GitHub Actions
  comme boucle de format/lint.

## Hardening toujours recommandé

1. **Scanopy :** pinner image/tag+digest, réduire l'exposition du daemon et
   remplacer le socket Docker brut par un proxy filtré si les appels nécessaires
   sont compatibles.
2. **NVM/pyenv bootstrap :** éviter les installateurs distants streamés
   directement vers `bash`; préférer `mise` ou un artefact vérifié.
3. **Doco-CD :** ne publier le webhook que s'il est réellement utilisé et
   protégé ; le polling reste suffisant sinon.
4. **Images privilégiées :** éliminer en priorité les `:latest` sur les
   composants ayant accès hôte/socket/control-plane.

## Couverture

Le ledger contient les mêmes cinq unités quick que le run précédent. Quatre
sont marquées `prior_covered_same_source`; Scanopy est
`prior_needs_validation`.

Artefacts :

- [architecture.md](./architecture.md)
- [coverage-ledger.json](./coverage-ledger.json)
- [findings.json](./findings.json)
- [FINDINGS-DETAIL.md](./FINDINGS-DETAIL.md)
- [NEEDS-VALIDATION.md](./NEEDS-VALIDATION.md)
- [run-metadata.json](./run-metadata.json)

## Limites explicites

- aucun probe actif contre TrueNAS, Talos, pfSense, Scanopy ou la production ;
- aucun accès aux secrets/runtime live ;
- aucun code cible exécuté faute de sandbox OS conforme au skill ;
- pas de vérificateur indépendant dans cette session API-only ;
- les validateurs Node vendored doivent être exécutés localement avant merge.

Le prochain audit complet doit reprendre ce ledger, résoudre le lead Scanopy,
puis élargir les surfaces au lieu d'interpréter ce run quick comme une
couverture exhaustive.
