# TrueNAS — critères de clôture des migrations de secrets

> État au 25 octobre 2026 : **BLOCKED / NON TERMINÉ**. Les copies canoniques
> cohérentes n'impliquent pas que le secret soit complet, chargé par l'App,
> ni que le fichier legacy puisse être supprimé ou remplacé par un lien.

## Observations de l'opérateur

| Service | Preuve établie | Dette restante |
| --- | --- | --- |
| OpenRAG | Backend/frontend `running+healthy`, copie canonique `staged` cohérente | Deux clés obligatoires absentes (`LITELLM_IDE_API_KEY`, `OPENRAG_ENCRYPTION_KEY`) ; legacy non finalisé |
| OpenSearch | Comparaison échouée **avant lecture de la valeur** | Au moins un candidat possède des droits/métadonnées non acceptés ; égalité des passwords non attestée |
| LiteLLM | App running, transport accessible | Secret canonique incomplet : `LITELLM_IDE_API_KEY`, `LANGFUSE_SECRET_KEY` |
| Scrutiny | Secret canonique examiné et déclaré prêt par le diagnostic global | App STOPPED ; statut runtime séparé, aucune validation de déploiement |
| Autres Apps | Pas de preuve globale récente fournie | Inventaire de clôture complet non attesté |

`bootstrap-repository-env-files.sh --check openrag` a indiqué
`1 staged legacy path(s) remain intact` et **finalize pending**.
Le script n'a pas automatiquement finalisé ce chemin.

## Procédure d'inspection sans afficher les secrets

Sur TrueNAS, exécuter les étapes séparément depuis la révision revue :

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check openrag
sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check --strict --scope openrag
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
```

Le mode `--scope openrag` est disponible dans la PR #280 ;
ne pas l'utiliser avec une version antérieure du script.

Lorsque le comparateur indique `source=canonical_env`,
`canonical_secret`, `legacy_env` ou `operator_selected`, examiner
**uniquement les métadonnées du fichier correspondant** :

```bash
for path in \
  /mnt/cpool/secrets/runtime/opensearch/.env \
  /mnt/cpool/secrets/runtime/opensearch/.env.secrets \
  /mnt/cpool/compose/nabla-compose/apps/opensearch/.env
do
  if sudo test -e "$path"; then
    sudo stat -Lc 'path=%n uid=%u gid=%g mode=%a type=%F' -- "$path"
  fi
done
```

Le comparateur attend **uid 0** et mode **0600, 0400 ou 0640**
sur un fichier régulier. Il refuse le candidat non conforme
sans afficher `OPENSEARCH_PASSWORD`. Ne pas lancer un `chmod -R`
ni changer le propriétaire de tous les fichiers. Une correction
ciblée exige d'identifier la source d'autorité et ses ACL ZFS.

## Gates obligatoires avant `--finalize openrag`

1. Restaurer les **identifiants existants** depuis leur source
   d'autorité, sans les régénérer ni afficher leurs valeurs.
2. Vérifier les quatre noms de clés OpenRAG requis et les deux
   clés LiteLLM absentes du dernier diagnostic.
3. Vérifier l'égalité du mot de passe OpenSearch après correction
   des métadonnées de fichier. La comparaison n'atteste pas
   automatiquement l'identifiant effectivement chargé par OpenSearch.
4. Examiner la configuration Custom App TrueNAS effective et son
   `env_file`, sans l'afficher publiquement.
5. Confirmer qu'une réconciliation ciblée et sauvegardée est réversible.
6. Confirmer une connexion authentifiée et un smoke fonctionnel
   OpenRAG/LiteLLM/OpenSearch.
7. Seulement après acceptation runtime, envisager
   `bootstrap-repository-env-files.sh --finalize openrag` avec revue
   explicite, puis refaire tous les contrôles.

**Interdictions :** rotation automatique `OPENSEARCH_PASSWORD`,
suppression de fichiers legacy avant acceptation, copie de dotenv
dans Git, redéploiement de masse, réindexation de `cpool/bababou`
et confusion entre transport HTTP 401 et auth validée.

[Roadmap](../roadmap.md) ·
[Relevé du 25 octobre](2026-10-25-critical-acceptance-followup.md) ·
[Runbook migration](truenas-migration-operator.md).
