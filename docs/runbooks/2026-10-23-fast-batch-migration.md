# Maintenance accélérée Talos / Kubernetes / Apps TrueNAS — 23–24 octobre 2026

**Statut : procédure préparée ; aucune exécution live par l'agent.**
Les scripts sont versionnés dans la PR Draft #271. Aucun runner GitHub Actions
n'est requis. Les deux phases s'exécutent sur **des machines différentes** :
Talos depuis la workstation équipée de `talosctl/kubectl` ; Apps via
`midclt` **local sur TrueNAS**.

## Changement de stratégie demandé

- Pas de snapshot ni sauvegarde etcd **imposés par les scripts**.
- **Talos 1.14.4 : les trois nœuds** 172.17.0.50 / .51 / .52
  reçoivent les commandes `talosctl upgrade` **en parallèle** (trois
  workers Python). Le cluster a un **seul control-plane/etcd** : cette
  opération peut rendre l'API et le stockage Kubernetes indisponibles
  simultanément. Sans sauvegarde etcd, une corruption peut entraîner une
  **perte irréversible des objets Kubernetes** ; Talos ne reçoit jamais
  `--force`, `reset` ou `bootstrap`.
- **Kubernetes 1.37.1** est lancé par `talosctl upgrade-k8s` une seule fois
  après récupération complète des trois nœuds ; cet outil orchestre ses
  propres composants. Exécuter une mise à niveau Kubernetes simultanément
  avec un Talos control-plane hors ligne n'est pas une opération valide.
- **Apps TrueNAS** : `app.redeploy` en lots parallèles, avec
  `--scope all` pour les  Apps RUNNING, fondations puis applications
  (chaque groupe parallèle). Les Apps STOPPED ne sont pas démarrées.
  Ce chemin tire les images puis redémarre, mais **ne modifie ni le tag
  Docker figé dans Compose ni la version d'un chart TrueNAS**.
- Aucune opération en masse sur les datasets, les secrets ou les versions
  PHP/Python *à l'intérieur* d'une image tierce. Une App contenant un PHP
  vulnérable nécessite une image corrigée, pas simplement un redémarrage.

Références opérateur :
https://api.truenas.com/v26.0/api_methods_app.redeploy.html
et https://docs.siderolabs.com/talos/v1.14/reference/cli .

## Préparer le checkout

La PR doit être **revue et fusionnée**, puis
`master` propre et actualisé. Les scripts acceptent `--check` avant
merge ; les modes `--apply` refusent les worktrees/branches non validés.
Ne pas faire de `git reset --hard`, ni réutiliser une empreinte de plan
après un changement du parc, ni divulguer les logs TrueNAS/credentials.

### 1. Workstation — Talos 3 nœuds en parallèle

```bash
cd ~/w/nabla-compose
git status --short
mise exec -- bash scripts/talos/validate-cluster.sh
mise exec -- bash scripts/talos/image-factory.sh
```

La dernière commande produit `TALOS_INSTALLER_IMAGE`. Confirmer que
l'image contient le schéma `qemu-guest-agent` et termine en
`:v1.14.4`. Pour préparer le plan, remplacer les placeholders localement
**sans committer l'URL ou l'empreinte sous forme d'autorisation permanente**.

```bash
IMAGE='factory.talos.dev/metal-installer/<schematic-id-64-hex>:v1.14.4'
mise exec -- python3 scripts/talos/fast-batch-upgrade.py \
  --check --installer-image "$IMAGE"
```

Après validation du hash du plan et **acceptation expresse d'une possible
perte du cluster sans sauvegarde etcd**, exécuter depuis `master` :

```bash
HASH='<planHash-64-hex-de-la-sortie>'
mise exec -- python3 scripts/talos/fast-batch-upgrade.py \
  --apply --installer-image "$IMAGE" --expected-plan-hash "$HASH" \
  --acknowledge I_ACCEPT_FULL_CLUSTER_OUTAGE_WITHOUT_ETCD_BACKUP
```

Le script soumet les 3 upgrades en parallèle. Il attend le vrai
`Server: Tag: v1.14.4` de chaque nœud, et non la seule version du client
`talosctl`. Ensuite seulement, il exécute `upgrade-k8s --dry-run`,
l'upgrade K8s, et le preflight final. Tout échec retourne non zéro ;
**aucun lancement automatique de Kubernetes après échec Talos**.

Après cela, vérifier également les charges et le stockage :

```bash
mise exec -- bash scripts/talos/validate-cluster.sh
mise exec -- bash scripts/talos/smoke-truenas-csi-nfs.sh --check
mise exec -- kubectl get nodes -o wide
mise exec -- kubectl get pods -A
```

### 2. TrueNAS — rafraîchissement parallèle des Apps RUNNING

```bash
cd /mnt/cpool/compose/nabla-compose
git status --short
just fast-maintenance-test

# En lecture seule, fondations + applications, parallèle 8 :
sudo python3 scripts/truenas/fast-bulk-redeploy-apps.py \
  --check --scope all --parallel 8
```

Le plan contient un hash SHA-256 fondé sur les Apps réellement RUNNING,
le périmètre et la concurrence. Après acceptation de l'indisponibilité
des Apps RUNNING (Postgres, Redis, Traefik inclus en `--scope all`) :

```bash
HASH='<planHash-apps-64-hex>'
sudo python3 scripts/truenas/fast-bulk-redeploy-apps.py \
  --apply --scope all --parallel 8 \
  --expected-plan-hash "$HASH" \
  --acknowledge I_ACCEPT_BULK_TRUENAS_APP_DOWNTIME
```

`--scope applications` est l'autre option si les services de fondation
ne doivent pas être redémarrés. La garde vérifie le checkout canonique
`/mnt/cpool/compose/nabla-compose`, `master` propre, root et l'état
live juste avant mutation. Chaque lot doit passer
`verify-app-runtime-health.sh` pour permettre le suivant. Le parallélisme
est borné à 16 ; 8 est une option agressive pour le homelab.

**Important :** le champ `upgrade_available` d'une App chart peut
signaler une release catalogue différente : `app.redeploy` ne la met
pas à jour. Pour une montée de version de chart, préparer un plan distinct
fondé sur `app.upgrade` et la compatibilité des données. De même, une
image `python:3.14.9` inscrite dans Compose ne change pas tant que le
runtime de l'App n'a pas réellement incorporé la nouvelle définition.

### 3. Validation post-opération

```bash
sudo bash scripts/truenas/finish-migrations-20261024.sh --check
sudo python3 scripts/truenas/audit-live-language-runtimes.py --check
sudo bash scripts/truenas/check-homelab-services.sh --deep
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
```

Confirmer sur la workstation : Kubernetes v1.37.1, trois nœuds Ready,
CSI/NFS, CNI/DNS, probes Gatus/Prometheus. Un échec de déploiement,
l'absence de la clé Anthropic, une image PHP obsolète, ou une App STOPPED
ne sont **pas réparés** automatiquement par ce script ; documenter
les écarts et corriger individuellement.

## Tests, limites et retrait du script temporaire

`just fast-maintenance-test` vérifie en local la détermination du plan,
l'absence d'actions par défaut, la garde hash/ack, les trois opérations
concurrentes Talos, l'interruption de Kubernetes si Talos échoue, les
lots TrueNAS et leurs health gates. Les tests utilisent des mocks ;
ils ne prouvent pas qu'une montée Talos ou TrueNAS live réussira.

Retirer ou archiver les scripts temporaires après l'opération une fois
le compte rendu vérifié. **Aucun upgrade automatique non approuvé.**
