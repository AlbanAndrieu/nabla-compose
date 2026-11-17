# Upgrade pfSense Plus 26.03.1 → 26.07 (Netgate arm64)

Cette procédure prépare la mise à niveau du Netgate 1100 de
`26.03.1-RELEASE` vers la version stable `26.07-RELEASE`. Elle ne lance pas
l'installation à distance. pfSense est la passerelle LAN/DNS (`172.17.0.1`)
et l'accès d'administration est publié via HAProxy (`home.albandrieu.com:10443`)
; prévoir l'interruption complète du réseau du homelab pendant le redémarrage.

## 1. Inventaire avant intervention

Depuis une station ayant un alias SSH configuré pour le pare-feu :

```bash
scripts/pfsense/prepare-upgrade.sh --ssh <alias-ssh-pfsense>
```

Ajouter `--port <port>` si l'alias n'utilise pas le port SSH par défaut. Le
rapport est en lecture seule : version, architecture, modèle, mémoire, espace,
environnements de démarrage ZFS éventuels, paquets installés et présence du
paquet REST API. Il n'inclut pas `config.xml` ni des clés API.

Vérifier que le rapport confirme `26.03.1-RELEASE` et `aarch64` (ou la valeur
d'architecture réellement affichée par le système), puis conserver l'inventaire
des paquets pour la réinstallation après upgrade. Ne pas mettre les paquets à
jour avant pfSense.

Le Netgate 1100 dispose d'environ 1 Gio de RAM. Si le relevé montre peu de
mémoire disponible ou des erreurs OOM récentes, suivre les conseils Netgate
pour les appareils 1100/2100 : redémarrage préalable facultatif et arrêt
temporaire des services non essentiels. Ne pas supprimer ni désactiver à
l'aveugle Unbound, le filtrage ou les règles réseau.

## 2. Sauvegarde et retour arrière

Dans `Diagnostics → Backup & Restore` :

1. Choisir `All` dans la zone de sauvegarde et télécharger la configuration.
2. Vérifier que le fichier téléchargé existe et le copier dans deux emplacements
   sécurisés, chiffrés et hors du pare-feu.
3. Ne jamais placer `config.xml` dans Git, un ticket ou une conversation : il
   contient des secrets et des éléments de configuration sensibles.
4. Si Auto Config Backup est activé, vérifier qu'une sauvegarde récente est
   effectivement disponible. Cela complète le fichier local, sans le remplacer.
5. Depuis l'interface, noter les environnements de démarrage ZFS et conserver
   l'environnement précédent jusqu'à la validation post-upgrade. Si le système
   est UFS ou si l'interface signale un problème d'EFI, préparer le média
   d'installation AARCH64 Netgate et la procédure de restauration avant de
   continuer.

## 3. REST API et paquets tiers

`pfSense-pkg-RESTAPI` est un paquet communautaire non supporté par Netgate.
Sa documentation liste pfSense Plus 26.07 comme version compatible et indique
qu'il doit être réinstallé après une mise à jour, car pfSense peut supprimer
les paquets non officiels. Elle précise également que les tests automatisés
couvrent amd64, et que le support d'autres architectures 64 bits n'est pas
garanti. Ton arm64 doit donc être traité comme une compatibilité à revalider,
même si la version pfSense est listée.

Après l'upgrade, ne réinstaller REST API que si le pare-feu a redémarré
correctement et si la release du paquet fournit bien l'artefact pour la version
26.07. Vérifier le nom exact de l'artefact sur la page [des releases
pfREST](https://github.com/pfrest/pfSense-pkg-RESTAPI/releases). Pour pfSense
Plus, la commande documentée utilise `pkg-static -C /dev/null add` avec le
paquet correspondant à la version ; ne pas réutiliser un paquet 26.03.1 pour
26.07. Puis vérifier le numéro REST API, l'accès authentifié et les droits
minimaux des comptes opérateurs.

Pour les autres paquets, suivre la recommandation Netgate : inventorier avant
l'upgrade et réinstaller ceux requis après, à partir du dépôt correspondant à
la version cible. Ne pas supposer que les paquets tiers sont restaurés.

## 4. Installation et validation

Dans `System → Update`, sélectionner la branche **Current Stable Version
(26.07)**, confirmer que l'offre affichée est bien `26.07-RELEASE`, puis lancer
l'upgrade depuis l'interface locale ou un accès console surveillé. Ne pas
sélectionner une branche snapshot/de développement.

Après le redémarrage, vérifier dans cet ordre :

1. version affichée `26.07-RELEASE`, interfaces WAN/LAN et règles PF chargées ;
2. accès WebGUI LAN et via `https://home.albandrieu.com:10443` ;
3. DHCP, DNS Unbound depuis le LAN (`172.17.0.1:53`), résolution split-horizon
   et accès Internet ;
4. HAProxy et les chemins publiés vers TrueNAS ;
5. paquets indispensables et éventuelle réinstallation de REST API ;
6. état mémoire/OOM et journaux système avant de réactiver les services
   facultatifs.

En cas de problème avec ZFS, démarrer l'ancien environnement depuis le menu de
démarrage/gestion des environnements. En cas de réinstallation, utiliser le
média AARCH64 approprié puis restaurer la sauvegarde vérifiée. Le script de
préflight ne modifie ni l'appliance ni sa sauvegarde.

## Références

- [Notes de version pfSense Plus 26.07](https://docs.netgate.com/pfsense/en/latest/releases/26-07.html)
- [Préparation d'une mise à niveau Netgate](https://docs.netgate.com/pfsense/en/latest/install/upgrade-guide-prepare.html)
- [Upgrade sur Netgate 1100/2100](https://docs.netgate.com/pfsense/en/latest/troubleshooting/upgrades-1100-2100.html)
- [Installation REST API et compatibilité](https://pfrest.org/INSTALL_AND_CONFIG/)
