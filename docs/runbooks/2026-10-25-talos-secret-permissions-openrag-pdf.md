# Reprise Talos, permissions de secrets et PDF OpenRAG — 25 octobre 2026

Etat : scripts publies dans la PR #280 ; AUCUN demarrage VM ou ingestion PDF
effectue par l'agent. Les operations TrueNAS doivent etre validees localement.

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

## 2. Correction groupee des modes des secrets canoniques

    sudo python3 scripts/truenas/audit-runtime-secret-permissions.py --check

Le scope est SEULEMENT /mnt/cpool/secrets/runtime, et ses repertoires.
Le script inspecte les metadonnees SANS lire les secrets. Il refuse les
symlinks, hardlinks, proprietaires non-root et types non classiques.
Il retire la lecture/ecriture/traversee des autres utilisateurs et
l'ecriture du groupe ; il preserve uid/gid ET group-read/traverse.
Il corrige les modes des .env, .env.secrets, .env.compose et
.env.*.secrets ; il ne touche pas aux autres types de fichiers.
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
