# Référence de ressources par service — RAM, GPU et stockage

**26 octobre 2026 · TrueNAS / workstation · catalogue Backstage v2**

## Observations de l'incident

Le premier relevé TrueNAS donnait environ **2 Gio de MemAvailable
sur 62 Gio**, sans swap, avec PSI \`some avg300=23.35\` et
\`full avg300=19.65\`. Le journal noyau entre 21:27 et 22:18
établit plusieurs **global_oom**, ayant tué des processus Java,
Python, Obsidian, mais aussi **deux processus QEMU**. Les VM
Talos/CSI doivent donc faire l'objet d'un contrôle de santé ciblé
avant de poursuivre les redémarrages de services.

\`docker stats\` à ce moment attribuait **~9,55 Gio à MongoDB**,
mais **~572 Mio à Netdata** et **~129 Mio à l'initializer
DefectDojo**. On ne peut donc pas attribuer les OOM à Netdata ou
DefectDojo sans preuves de tendance ou d'association cgroup.
Une mesure ultérieure montrait ~8,3 Gio disponibles et PSI 10 s
nul, mais ceci ne prouve pas l'absence de nouveaux OOM.

**Actions immédiates** : laisser arrêtés les services non indispensables,
ne pas redémarrer toutes les applications et VM, diagnostiquer les
victimes OOM du journal et surveiller MongoDB/JVM/VM avant toute
migration ou réinitialisation de base.

## Modèle et source de vérité

Les noms des services et leur identité viennent des
\`catalog/generated/entities.json\` et
\`catalog/generated/identity-map.json\`, via le label Docker
\`com.albandrieu.nabla.entity-ref\` ou la correspondance exacte
\`apps/<project>/compose.yml#services/<service>\`.
Un nom ressemblant à un service n'est **pas** une preuve suffisante.
Les conteneurs ambigus/non indexés restent non attribués.

Les observations sont volontairement distinctes du catalogue
déclaratif : elles sont **horodatées**, propres à un hôte et
**ne doivent pas être commitées dans Git**.

| Signal | Source ponctuelle | Limite |
| --- | --- | --- |
| RAM du conteneur | \`docker stats --no-stream\` | Échantillon de working set, pas le pic mémoire |
| GPU | \`nvidia-smi\`, PID → cgroup Docker | GPU sur workstation : relevé workstation obligatoire ; pas de valeur zéro inventée |
| Couche écrivable | \`docker ps --size\` | N'inclut pas les bind mounts et volumes |
| ZFS datasets | \`zfs list -Hp\` + \`docker inspect .Mounts\` | \`used\` inclut descendants/snapshots ; datasets partagés signalés, **jamais sommés** |
| Identité | label Backstage v2 ou Compose project+service exact | Pas de repli sur un simple nom similaire |
| Disponibilité | **pas** déterminée par les métriques | Absence = \`unverified\`, non \`DOWN\` |

C'est une **inspection ponctuelle existante**, pas un daemon de
surveillance supplémentaire : Prometheus/cAdvisor demeure la source
de l'historique CPU/RAM et des courbes sur TrueNAS. Le relevé
GPU NVIDIA par processus exige des droits sur le GPU de l'hôte.

## Collecte TrueNAS

Après intégration des fichiers du dépôt et si Docker répond
sans délai excessif :

\`\`\`bash
cd /mnt/cpool/compose/nabla-compose

sudo install -d -o root -g root -m 0700 \
  /mnt/cpool/var/nabla/service-resources

sudo python3 scripts/truenas/collect-service-resource-evidence.py \
  --check --host truenas \
  --output "/mnt/cpool/var/nabla/service-resources/resources-$(date -u +%Y%m%dT%H%M%SZ).json"
\`\`\`

La sortie console est un **résumé** ; le JSON privé complet
(mode \`0600\`) contient les champs :

- \`schema=nabla-service-resources/v1\`, \`catalog_revision\`,
  \`observed_at_utc\`, \`source_host\` ;
- \`services[].entityRef\`, \`memory.working_set_bytes\` ;
- \`gpu.process_memory_bytes\` (nullable) ;
- \`storage.writable_layer_bytes\`, \`datasets[].name\`,
  \`used_bytes_including_children\`, \`shared_by_services\` ;
- les états de disponibilité des métriques, jamais une valeur
  \`0\` lorsque la source n'a pas répondu.

La collecte utilise Docker Stats, Docker inspect des **montages
uniquement** (pas de \`.Config.Env\`), ZFS et \`nvidia-smi\`,
avec limites et délais par commande. Si TrueNAS est encore
en forte pression/OOM, remettre cette opération à plus tard :
la capture doit aider le diagnostic, pas l'aggraver.

## GPU de la workstation

Si le GPU est sur \`172.17.0.57\`, collecter sur **cet hôte** :

\`\`\`bash
cd ~/w/nabla-compose
python3 scripts/truenas/collect-service-resource-evidence.py \
  --check --host workstation
\`\`\`

Le GPU non visible sur TrueNAS reste \`unverified\`, pas \`0 Mio\`.
Une tâche NVIDIA non attribuable sans ambiguïté à un cgroup
Docker reste également \`unverified\`. Les données GPU hôte
ne sont pas recopiées artificiellement sur des services TrueNAS.

## Affichage dans le site

La PR du site \`feat/homelab-service-resource-snapshots-20261026\`
permet, en mode OWNER seulement, d'importer le fichier de
ressources JSON **depuis le navigateur**. Il est stocké
localement, sans envoi au cloud ni accès public. Les cartes
affichent RAM / GPU / couche Docker / datasets ZFS partagés.
Au-delà de 30 minutes, le relevé est présenté comme
**historique**. Une révision différente du catalogue est signalée.

Un flux automatique devra passer par le collecteur LAN
autorisé et un endpoint OWNER authentifié. Aucune donnée
de capacité brute ne doit être exposée à SERVICE/public.

## Tests locaux hors LAN

\`\`\`bash
python3 -m pytest -q tests/test_service_resource_evidence.py
\`\`\`

La collecte est strictement en lecture seule. Ne pas lancer
\`du\` récursif sur le pool pendant une crise mémoire, ni
modifier l'ARC ZFS ou les limites mémoire Docker sans mesure.
