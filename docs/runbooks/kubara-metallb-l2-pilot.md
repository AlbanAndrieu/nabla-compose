# MetalLB L2 via Kubara · essai Talos contrôlé

**28 novembre 2026 — CODED / NOT_DEPLOYED.** Propriétaire : `nabla-compose`,
[PR #456](https://github.com/AlbanAndrieu/nabla-compose/pull/456).
Pas d'installation ni d'allocation d'adresse IP réalisée depuis GitHub.

## Architecture et justification

- Cilium reste le **CNI** (`ipam.mode=kubernetes`), protège les NetworkPolicy
  et conserve `kubeProxyReplacement: false`; kube-proxy assure les Services.
- MetalLB sera uniquement l'**annonceur L2 d'une VIP de service** (ARP).
  Les CRD MetalLB ne remplacent ni Cilium, ni kube-proxy, ni TrueNAS CSI.
- Kubara est l'unique propriétaire prévu de l'installation Helm MetalLB /
  Traefik ; le manifeste `metallb-intent.REVIEW-ONLY.yaml` généré ne doit
  **jamais** être appliqué en parallèle de la configuration générée par Kubara.
- Premier service : `traefik` Kubernetes, un `LoadBalancer` sur une VIP
  `172.17.0.0/24` réservée, distincte de TrueNAS (`.24`) et des VMs
  Talos (`.50-.52`). Pas de second 443 sur `172.17.0.24`.
  La première valeur `externalTrafficPolicy` sera `Cluster`, à mesurer.
- Pas de BGP, de Cilium L2 announcement, de `externalIPs`, de route WAN
  ni de DNS public vers la VIP. `external-dns` reste désactivé.

Documentation : [Kubara v0.14 MetalLB](https://docs.kubara.io/v0.14.0/1_getting_started/bootstrapping/),
[MetalLB IPAddressPool/L2Advertisement](https://metallb.io/configuration/),
[MetalLB kube-proxy IPVS strictARP](https://metallb.io/installation/),
[Cilium L2 requirements](https://docs.cilium.io/en/stable/network/l2-announcements/).

## Gate M0 · État réel sans mutation

Depuis un opérateur avec kubeconfig privé Talos, conserver les sorties sans
token ni certificats :

```bash
python3 scripts/talos/audit-kubara-integration.py
python3 scripts/talos/audit-kubara-integration.py \
  --cluster-readonly --ack-cluster-readonly
bash scripts/talos/preflight-kubara.sh --pre-bootstrap

kubectl get nodes -o wide
kubectl -n kube-system get ds cilium kube-proxy -o wide
kubectl -n kube-system get cm cilium-config kube-proxy -o yaml
kubectl get svc -A -o wide
kubectl get ingressclass
kubectl get ipaddresspools.metallb.io -A --ignore-not-found
kubectl get l2advertisements.metallb.io -A --ignore-not-found
```

Si `kube-proxy` utilise **IPVS**, MetalLB exige `ipvs.strictARP=true`.
En mode `iptables`, cette exigence IPVS spécifique ne s'applique pas.
Un ConfigMap manquant est **UNVERIFIED** : comparer le service effectif
Talos plutôt que supposer le mode. Dans ce pilote, **ne pas activer**
`CiliumL2AnnouncementPolicy` ni `l2announcements.enabled`.

Vérifier le DaemonSet Cilium, les objets `LoadBalancer` existants et
les éventuels MetalLB/MetalLB Operator installés. Un seul acteur doit
annoncer chaque VIP. Refuser toute collision de plage annoncée.

## Gate M1 · Réserver l'IPv4 sur R7000

La plage DHCP réelle du **Netgear R7000** après retrait de pfSense
reste à relever. La plage `172.17.0.100–200` est une ancienne valeur
pfSense, **pas** une preuve de configuration R7000 actuelle.

Choisir manuellement **une seule** IPv4 statique libre sur
`172.17.0.0/24`, hors DHCP actuel et hors allocations statiques ;
vérifier le DHCP, le registre ARP du R7000, le voisinage Linux et les
VMs Talos. Tester `arping -D` depuis une interface réellement reliée
au même domaine L2 ; un ping sans réponse **ne prouve pas** l'absence
de propriétaire. Documenter le test, son interface et son heure.

Le script refuse les adresses déjà identifiées comme utilisées
(`.1`, `.24`, `.50`, `.51`, `.52`, `.57`) et l'ancienne plage DHCP
`.100–.200` mais **ne peut pas prouver** une réservation R7000.

```bash
# Exemples : remplacer VIP par l'IP réellement réservée.
export VIP='<adresse-ipv4-verifiee-et-reservee>'
python3 scripts/talos/prepare-metallb-kubara.py --vip "$VIP"

# Répertoire jetable, hors dépôt (ne contient pas de secrets).
REVIEW="$(mktemp -d)"
python3 scripts/talos/prepare-metallb-kubara.py --vip "$VIP" \
  --output-dir "$REVIEW" --ack-dhcp-reserved
```

La commande ne change **aucune** ressource réseau. Elle fournit
`config.yaml` Kubara (MetalLB activé, pool privé /32),
`metallb-intent.REVIEW-ONLY.yaml` (pool `autoAssign: false`,
annonce L2 limitée aux workers, *référence uniquement*),
et `README.txt`. Permissions : répertoire `0700`, fichiers `0600`.

## Gate M2 · Schéma Kubara, Helm et ressources générées

```bash
# Depuis un répertoire d'essai ne contenant aucune identité Git/deploiement.
cd "$REVIEW"
git init -q
KUBARA_UPDATE_CHECK=0 kubara --version       # DOIT correspondre à 0.14.0
KUBARA_UPDATE_CHECK=0 kubara schema --output config.schema.json

# Le schéma généré n'est PAS à lui seul une validation du config.yaml.
# Valider la donnée contre ce schéma via jsonschema (outil d'audit local).
python3 - <<'PY'
import json
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator, validators
schema = json.loads(Path("config.schema.json").read_text())
data = yaml.safe_load(Path("config.yaml").read_text())
Validator = validators.validator_for(schema)
Validator.check_schema(schema)
Validator(schema, format_checker=Validator.FORMAT_CHECKER).validate(data)
print("kubara_candidate_schema=PASS")
PY
KUBARA_UPDATE_CHECK=0 kubara generate --helm --dry-run
```

Examiner le rendu Helm (pas seulement le code retour) : images/versions,
CRD, Namespace, `IPAddressPool` et `L2Advertisement`, pool `/32`,
`autoAssign: false`, éventuels `externalIPs` ou annoncer L2 en double,
Traefik `Service.type=LoadBalancer`, classe `traefik` unique, PSA/RBAC,
NetworkPolicy, ressources CPU/RAM, Argo CD et secrets. Si Kubara génère
ses propres objets avec un autre nom et `autoAssign: true`, corriger
son overlay/catalogue **avant** bootstrap ; ne pas superposer le manifeste
de référence. C'est un **blocage**, pas une invitation à bypasser la gate.

## Gate M3 · Installation/essai opt-in

Après plan revu, sauvegarde etcd hors nœud, snapshot des manifests et
approbation explicite du bootstrap :
1. Installer MetalLB **par Kubara/Argo CD**, pas en parallèle par `helm
   upgrade --install metallb` manuel.
2. Attendre le controller Deployment et les speakers DaemonSet Ready.
3. Vérifier la configuration `IPAddressPool`/`L2Advertisement` finale,
   puis annoter explicitement **seulement** le Service Traefik pour
   demander la VIP (en respectant les labels/overlays générés par Kubara).
4. Vérifier `kubectl get svc` = adresse demandée, ARP/MAC sur le LAN,
   requêtes HTTP(S) depuis une source LAN autorisée, et **refus WAN**
   depuis une source indépendante. Réaliser un test de panne d'un worker :
   vérifier les annonces L2 et le délai de bascule.
5. Conserver Cilium, kube-proxy, CSI et le Traefik de TrueNAS intacts.

**Aucun déploiement automatique n'est exécuté par
`prepare-metallb-kubara.py`.** Un manque d'IP, de schéma Kubara validé,
de certificat backend vérifiable ou de test WAN bloque la promotion.

## Gate M4 · TLS strict entre les deux Traefik

Dans `apps/traefik/compose.yml` la configuration **versionnée**
passe à `--serversTransport.insecureSkipVerify=false` ; cela n'atteste
pas la valeur en cours d'exécution. Le certificat Let's Encrypt
`*.int.albandrieu.com` de TrueNAS protège ses connexions entrantes ;
il **n'authentifie pas** automatiquement le Traefik déployé sur Talos.
Le second Traefik devra présenter son propre certificat pour le nom SNI
`test.int.albandrieu.com`, via un secret TLS géré/renouvelé (par exemple
cert-manager DNS-01) ou une réplication sécurisée et suivie d'un
certificat existant. Ne pas copier `acme.json` dans Git/Kubernetes.

L'exemple `apps/traefik/examples/talos-kubara-bridge.example.yml`
reste non chargé. Son `serversTransport` impose `insecureSkipVerify:
false`, une CA de confiance et le SNI ; pour une chaîne publique Let's
Encrypt valide, un `rootCAs` personnalisé est inutile et peut être
omis après vérification de la chaîne. Le certificat/le nom doivent être
acceptés sans `-k` ou `curl --insecure`.

Pour chaque route HTTPS **existante**, relever le backend effectif
avant le changement global, tester la confiance du certificat depuis
le conteneur Traefik (et pas uniquement depuis le navigateur). Le
commentaire historique « Proxmox 500 » n'est pas une preuve d'une route
Proxmox active : l'inventaire runtime doit confirmer. Si le backend
présente une CA privée, ajouter une `serversTransport` dédiée avec
`rootCAs` et `serverName`, **pas** un bypass TLS global.

## Gate M5 · Réversibilité

- Pas de bascule Cloudflare pendant le pilote L2. L'edge TrueNAS sert
  toujours les applications TrueNAS ; aucune route externe Talos n'est
  créée par défaut.
- En cas d'échec VIP, retirer l'annotation/Service LoadBalancer du
  pilote et désactiver son annonce, sans toucher à Cilium, CSI, PV ou
  datasets. Conserver la classe/routage internes non exposés.
- En cas d'échec TLS TrueNAS après la bascule globale, restaurer le
  Compose Traefik **versionné précédent uniquement après diagnostic**,
  ou installer le certificat de confiance manquant. Éviter de
  rétablir durablement `insecureSkipVerify=true`.
- Consigner toutes les preuves (révision Git, source des observations,
  date/heure, statut complet/incomplet) dans la roadmap.

**État :** scripts/tests/docs CODED ; VIP, DHCP, ARP, schéma Kubara, Helm
dry-run, signature/renouvellement TLS, déploiement et test WAN **NOT_RUN**.
