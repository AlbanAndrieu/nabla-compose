# Retour d'expérience — migrations Homelab (6 novembre 2026)

Ce document retient **uniquement les problèmes passés qui peuvent se reproduire**. Les décisions et les opérations encore ouvertes appartiennent à [la roadmap active](../roadmap.md). Les journaux d'incident plus anciens restent dans [l'archive approuvée](../archive/roadmap-through-2026-10-24.md) ; aucune valeur de secret ni sortie brute n'est recopiée ici.

## Identité runtime : services `STOPPED` comptés deux fois

**Symptôme (PR #326)** : les Apps TrueNAS arrêtées n'avaient aucun conteneur Docker. Une déclaration `x-nabla.runtime.containerService` seule aboutissait à un composant `declared_only` et une App distincte `observed_only`.

**Cause / prévention** : associer `runtime.appId` au nom **réel** de l'App TrueNAS, sans renommer son service Compose. Exemples confirmés : `graylog`, `bitcoind`, `elasticsearch → elastic-search`, `hermes → hermes-agent`. L'état `in_sync/STOPPED` indique une correspondance correcte, **pas** un service sain. La migration de l'identité `homeassistant` est particulière : ne jamais contourner son contrat canonique en réécrivant l'identifiant pour faire disparaître une alerte.

**Régression à tester** : rejouer la réconciliation avec une App arrêtée sans conteneur ; compter exactement une App et conserver `STOPPED`.

## Cloudflare : challenge et fausse panne d'origine

**Symptôme (4–5 novembre)** : Keycloak et LiteLLM renvoient un challenge WAF/Bot depuis l'egress de FastAPI Cloud, mais répondent sur un autre chemin. Le challenge ne démontre ni panne de l'origine ni bonne santé.

**Décision** : ne pas introduire d'exception WAF/Bot générale. Depuis FastAPI Cloud, enregistrer `warn / edge_block=challenge` ; l'observateur LAN TrueNAS doit prouver la santé. Les applications Access nécessitent `Service Auth`, pas un `Bypass` indiscriminé. Le bypass Vaultwarden `Everyone` sur un hostname complet est une dette de sécurité, pas un moyen acceptable d'obtenir `200`.

**Régression à tester** : différencier `AUTH_FAILED`, `DENIED`, `challenge`, `NOT_RUN` et véritable échec HTTP de l'origine.

## pfSense / télémétrie et exposition WAN

L'observateur FastAPI Cloud a été placé en `transport_only` / `credential_mode=disabled` conformément au périmètre WAN. Cette absence de télémétrie authentifiée côté Cloud est volontaire ; le diagnostic authentifié appartient au LAN TrueNAS. Ne pas classer le service en panne pour cette raison.

Les règles CrowdSec/PF chargées sont une preuve de **présence**, non de filtrage effectif de l'interface WAN sans attribution de cette interface et observation du trafic.

## TrueNAS : manque de mémoire et redémarrages contre-productifs

En octobre, la pression mémoire TrueNAS, les processus OOM et la saturation des conteneurs (indexeurs, processus zombies et services concurrents) ont compliqué les reprises. Les erreurs de DNS, de healthcheck et les délais de démarrage n'ont pas tous la même cause.

**Prévention** : contrôler `MemAvailable`, PSI, ARC, OOM, descripteurs containerd, limites réelles et volume des snapshots avant de modifier le réseau, redémarrer ou effacer des fichiers. Ne jamais lancer `docker system prune` ou `docker volume prune` pour « réparer » sans inventaire et sauvegarde.

## Runtime secrets / LiteLLM / OpenClaw

Une clé présente dans un fichier n'est pas nécessairement chargée dans le conteneur. À l'inverse, l'enregistrement des deux clés virtuelles main/cron TrueNAS et leur budget `below_cap` n'atteste ni le routage réel ni les limites RPM/TPM. Les anciens symptômes `429` ne doivent pas être attribués à OpenClaw sans métadonnées de requête.

Le diagnostic OpenClaw a aussi montré un parent `agent:cron:main` absent, un Digest dont la plage `3-5` ne respecte pas le type entier de `--top`, et des journaux TrueNAS inaccessibles sans droit Docker : **problèmes distincts**. Préserver les preuves redigées, sans exposer clé, session ou message privé. Une session `BW_SESSION` exposée doit être invalidée, jamais réutilisée.

## Pièges d'automatisation

- Un hook Pre-commit `language: system` qui importe PyYAML échoue si le Python de `mise` n'a pas `yaml`. Déclarer l'environnement Python isolé et un test de contrat.
- Un diagnostic lancé localement sur TrueNAS ne doit pas tenter SSH vers TrueNAS depuis lui-même. Détecter le contexte et conserver `sudo -n` explicite.
- La présence d'un script `--apply` ou d'une PR fusionnée ne démontre pas son exécution, l'absence de régression ou la migration des données.
- Pour Joplin/Scanopy/ntopng, valider les bases, volumes et secrets et la politique de réseau **avant** une première création d'App ; un conteneur `RUNNING` n'est pas une preuve de données persistées.
- Le chemin / l'`appId` du service historique et le chemin d'une nouvelle Custom App peuvent diverger ; conserver un plan de rollback documenté avant toute suppression.

Ces problèmes sont des **repères de diagnostic**, pas des tickets ouverts ni une autorisation de replay d'anciennes commandes.
