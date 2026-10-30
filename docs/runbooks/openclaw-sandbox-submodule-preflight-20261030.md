# Préflight du déplacement de `apps/openclaw/compose.yml` (read-only)

Le dossier `apps/openclaw` sera à terme le **submodule directement**
`AlbanAndrieu/nabla-openclaw`. Le premier lot de migration est effectué :
14 fichiers Workstation déplacés sous `ops/openclaw-workstation/`
avec références Python et tests adaptés. **Quatre fichiers sandbox**
restent dans `apps/openclaw/`.

**Attention :** le fichier Compose du sandbox peut être référencé par
une application TrueNAS via `custom_compose_config.include`.
Le nouveau script lit seulement `app.config` pour les deux noms
`openclaw` et `openclaw-sandbox` et expurge toute configuration.
Il ne peut pas vérifier tous les autres noms d'application : une
absence de référence observée n'est **pas** une autorisation de
déplacement, et son exit code est toujours `2`.

Sur **TrueNAS** (après pull de la branche #295) :

```bash
cd /mnt/cpool/compose/nabla-compose
python3 -m unittest discover -s tests -p 'test_openclaw_sandbox_binding.py' -v
python3 scripts/truenas/check-openclaw-sandbox-binding.py
# Seulement si le compte exige une élévation déjà autorisée :
python3 scripts/truenas/check-openclaw-sandbox-binding.py --noninteractive-sudo
```

Les réponses `blocked_legacy_include_in_use` et
`unverified_no_global_app_reference_scan` signifient
**NE PAS déplacer le fichier Compose**. Ne pas publier les sorties
brutes de `midclt call app.config`, qui peuvent contenir des secrets.

Après validation indépendante des apps et consommateurs :
1. Mettre à jour la référence TrueNAS de `include` **dans une
   opération distincte**, avec sauvegarde et rollback.
2. Déplacer les 4 fichiers sandbox vers `apps/openclaw-sandbox/`,
   en conservant le service et le catalogue opérationnel.
3. Vérifier le runtime et l'absence de référence à l'ancien chemin.
4. Seulement alors ajouter le submodule `apps/openclaw`, avec
   pin d'un SHA testé de `nabla-openclaw`. Aucun déploiement de
   Gateway/heartbeat pendant le changement de chemin Git.

L'API TrueNAS 26 `app.config` est une lecture de configuration
requérant `APPS_READ`, pas une commande de modification.
