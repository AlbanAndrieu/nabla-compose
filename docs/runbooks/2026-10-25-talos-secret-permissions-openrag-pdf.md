# Reprise Talos, permissions de secrets et PDF OpenRAG — 25 octobre 2026

Nouvelle preuve operateur : **trois VM Talos RUNNING** sur TrueNAS.
Le premier vm.start control-plane a expire mais le passage suivant
a confirme RUNNING ; les deux workers sont egalement RUNNING.
**Talos/etcd/Kubernetes/CSI restent NOT_VERIFIED.** Aucun upgrade lance.

Audit global secret : une correction de mode OpenClaw 0644 vers 0640
appliquee avec uid/gid inchanges. Les 12 tests de contrat Python/Bash
sont PASS sur le checkout operateur.

Le PDF prive est valide sur l'hote (849129 octets), lisible par OpenRAG
mais **Docling NOT_READY**. Conversion, ingestion et retrieval NON TESTES.
Aucune action runtime TrueNAS ni lecture de PDF effectuee par l'agent.

## 1. Talos : VM arretees (TrueNAS)

    sudo python3 scripts/truenas/resume-stopped-talos-vms.py --check
    sudo bash scripts/truenas/reconcile-talos-vm-policy.sh --check
    TALOS_REQUIRE_RUNNING=false bash scripts/truenas/verify-talos-vm-autostart.sh --check

La premiere commande lit vm.query pour taloscp01, taloswk01 et taloswk02.
Elle refuse des VM absentes, ambigues ou dans un etat de transition.
Si la revue autorise leur redemarrage, executer UNE seule fois :

    sudo python3 scripts/truenas/resume-stopped-talos-vms.py --start \
      --acknowledge I_ACCEPT_STARTING_EXISTING_TALOS_VMS

Ce script ne change ni la version Talos, ni Kubernetes, ni etcd, ni
les volumes des VM. Il confirme RUNNING via le middleware, pas la sante
Kubernetes. Il respecte les VM deja RUNNING et demarre le control-plane
avant les workers.

Ensuite, depuis la workstation avec mise, talosctl et kubectl :

    mise exec -- bash scripts/talos/validate-cluster.sh
    mise exec -- bash scripts/talos/smoke-truenas-csi-nfs.sh --check
    mise exec -- kubectl get nodes -o wide
    mise exec -- kubectl get pods -A

Ne lancer aucun upgrade Talos/Kubernetes pendant que les VM sont STOPPED.
Le batch versionne (Talos 1.14.4/K8s 1.37.1) vise les TROIS noeuds en
parallele, y compris le singleton etcd : risque d'indisponibilite
globale et de perte de donnees sans sauvegarde etcd validee.

### Timeout vm.start

Un `TimeoutExpired` de `midclt call vm.start` ne signifie pas
forcement que la VM a echoue a demarrer. Le script actuel observe
`vm.query` apres la commande, meme en cas de timeout. S'il confirme
RUNNING, il accepte la VM sans deuxieme demande de demarrage.
Sinon l'etat reste UNVERIFIED : ne pas insister sans verifier le
middleware TrueNAS. **Ne pas relancer `--start` pour le moment**
puisque les trois VM sont maintenant RUNNING.

## 2. Correction groupee des modes des secrets canoniques

    sudo python3 scripts/truenas/audit-runtime-secret-permissions.py --check

Le scope est SEULEMENT /mnt/cpool/secrets/runtime, et ses repertoires.
Le script inspecte les metadonnees SANS lire les secrets. Il refuse les
symlinks, hardlinks, proprietaires non-root et types non classiques.
Il retire la lecture/ecriture/traversee des autres utilisateurs et
l'ecriture du groupe ; il preserve uid/gid ET group-read/traverse.
Il corrige les modes de TOUS les fichiers reguliers sous ce root,
y compris JSON/PEM/.key et les dotenv ; seuls les fichiers dotenv
perdent aussi leur bit executable. Les uid/gid sont preserves.
Il ne corrige pas les anciens chemins legacy en dehors du scope.

Apres revue du rapport, action explicite et bornee :

    sudo python3 scripts/truenas/audit-runtime-secret-permissions.py --apply \
      --acknowledge I_ACCEPT_SCOPED_SECRET_MODE_REPAIR

Ne pas utiliser chmod -R 600 ni chown -R root:root. Ne pas supprimer ou
finaliser en masse les anciens chemins utilises par les conteneurs.

## 3. OpenRAG et PDF prive (TrueNAS)

Les PDF Mickey dans /mnt/cpool/bababou restent PRIVES. La capture du
billet contient des codes QR et des numeros de reservation. Ne pas les
copier vers un fournisseur externe.

    sudo bash scripts/truenas/check-openrag-private-pdf.sh --check \
      --file 'mickey-l7k-0029666509-uFeeX6VP.pdf'

Le script confirme un vrai fichier PDF sur l'hote, la visibilite
en lecture seule depuis openrag-backend, la readiness Docling depuis
l'hote et le reseau OpenRAG, puis la sante de /search/health.
Il n'extrait, n'upload, n'indexe et ne recherche AUCUN contenu du PDF.

Les tests d'ingestion E2E et de retrieval sont NON EXECUTES. Commencer
par un PDF synthetique et verifier Docling/ready, OpenSearch indexing et
une recherche OpenRAG qui retourne la valeur attendue. Avec la copie
personnelle, utiliser ensuite une execution volontairement autorisee.

### Etat reel des services apres les tests du 25/10

- Talos 1.13.9 / Kubernetes 1.36.3 : trois noeuds Ready.
- `validate-cluster.sh` : exit=0, 5 OK, 2 avertissements.
- CSI TrueNAS : controller recent 5/5, node plugins Ready,
  StorageClass declaree, mais **ancien controller 0/5 Error**
  (144 redemarrages) a qualifier par ReplicaSet.
- `smoke-truenas-csi-nfs.sh --check` : PASS preflight, mais n'a
  cree aucun PVC ; pas encore de smoke cross-node + reclaim.
- Secrets canoniques : second audit `mode_changes=0 blockers=0`.
- Node22 : version correcte selectionnee avec mise, mais npm 12
  etait encore trouve dans PATH (5 tests PASS/1 FAIL). La recette
  `just node22-fast` appelle maintenant le npm CLI embarque dans
  la meme installation Node22. Gate complete a rejouer.
- Docling : App ABSENT et conteneur absent ; port host et reseau
  Docker non joignables. PDF OpenRAG valide et lisible en montage RO
  mais conversion/ingestion/retrieval non effectues.

### Recette CSI restante (sur la workstation)

```bash
mise exec -- kubectl -n truenas-csi get deploy truenas-csi-controller -o wide
mise exec -- kubectl -n truenas-csi get rs -o wide
mise exec -- kubectl -n truenas-csi get pods -o wide
```

Le controller recent est pret, mais l'ancien pod Error existe toujours.
Verifier son owner ReplicaSet et le nombre de replicas desires avant
une suppression. **Ne pas supprimer le controller sain et ne pas
deployer un deuxieme CSI**. Pour le smoke `--apply`, le script exige
`kubectl`, `jq`, `midclt`, `zfs` et un kubeconfig valable lorsque
`--keep` n'est pas selectionne. Le TrueNAS operator doit disposer
de ces outils, sinon le reclaim ne peut pas etre prouve. Aucun
`--apply` execute a ce stade.

### Diagnostic Docling dedie (sans ingest)

    sudo python3 scripts/truenas/diagnose-docling-readiness.py --check

Cette commande distingue App TrueNAS, conteneur Docling, readiness
`172.17.0.24:5001/ready` et readiness depuis
`openrag-backend -> docling:5001`. Elle ne lit aucun fichier prive.
Le diagnostic actuel montre `app=ABSENT`. Faire le preflight de la
creation unique :

```bash
sudo bash scripts/truenas/deploy-docling.sh --check
```

Le preflight verifie le Compose, les deux reseaux externes et l'image
CPU deja presente dans le cache Docker. **Il ne telecharge rien**.
Apres validation, l'action explicite est
`sudo bash scripts/truenas/deploy-docling.sh --apply`.
Ne pas lancer `app.update` sur une App absente et ne pas multiplier
les jobs d'installation. Le test PDF protege maintenant explicitement
le montage Docker `/mnt/bababou` en lecture seule.

## 4. Pannes toujours ouvertes

    sudo bash scripts/truenas/triage-critical-failures.sh --check --remaining
    python3 scripts/prometheus/diagnose-failed-scrapes.py --check --scope remaining
    sudo python3 scripts/truenas/check-akvorado-metadata-config.py --check
    sudo bash scripts/truenas/diagnose-akvorado-config.sh --check
    sudo python3 scripts/truenas/diagnose-akvorado-flow.py \
      --strict --fail-on-blocked --observe-seconds 60

Derniere preuve : Prometheus 7 cibles DOWN (2 HTTP 401, 5 TCP refuses),
mais Prometheus lui-meme fonctionne. Akvorado : +20 flux, +20 erreurs
metadata missing, 0 lot ClickHouse. Un SHA du fichier Akvorado monte
n'atteste pas le reload en memoire de son Outlet.
