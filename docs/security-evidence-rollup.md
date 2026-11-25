# Reporting consolidé des preuves de sécurité

Le workflow GitHub Security evidence rollup (read-only) produit un rapport HTML
et JSON (durée de conservation 7 jours) pour quatre dépôts Nabla.

- Données : uniquement métadonnées GitHub Actions sur un ensemble fermé de
  workflows, SHA/ID de run et présence de certains artefacts de sécurité.
- Aucune commande n'est lancée sur TrueNAS, Talos ou la workstation.
- Aucune analyse DAST active n'est déclenchée par ce reporting.
- Aucun rapport de vulnérabilité, secret, CVE, URL interne ou preuve HTTP n'est publié.
- CI_SUCCESS signifie réussite du workflow et non validation du scanner ou
  import DefectDojo. Les findings restent inconnus (null, jamais zéro).
- CI_FAILED, INCOMPLETE, NOT_RUN, UNVERIFIED, FRESH et STALE sont distincts.
- Aucun ancien succès ne remplace un run récent échoué.
- DefectDojo, Dependency-Track, Plumber, Prowler, Trivy K8s, FreshRSS et
  Dependabot restent UNVERIFIED tant qu'aucune preuve runtime fiable n'existe.

Les fichiers security-controls.html et security-controls.json sont disponibles
comme artifacts du workflow. Le rapport sert de vue de **qualité des preuves**,
pas de tableau de bord de vulnérabilités confirmé.

Validation hors ligne :

    python3 scripts/security/report-github-controls.py --check
    python3 -m unittest tests/test_security_control_rollup.py -v

Pour aller plus loin, ajouter depuis TrueNAS un export **privé** lecture seule
des Tests et findings DefectDojo, des SBOM traités par Dependency-Track et des
preuves Talos/Prowler/FreshRSS. Rapprocher par service, environnement, scanner,
révision et horodatage ; vérifier les reimports sans doublons. Ne jamais publier
ces données privées comme artifact GitHub d'un dépôt public.
