# CrowdSec pfSense Small — preuve d'application et de retrait PF

> Procédure de réception P0 — 27 octobre 2026. **Aucune commande de ce
> document n'est exécutée par l'agent.** Les deux étapes de mutation
> ci-dessous requièrent une décision explicite de l'opérateur.

## État établi

- LAPI centrale TrueNAS : `172.17.0.24:8084`; bouncer pfSense actif,
  authentifié (HTTP 200), moteur CrowdSec local pfSense arrêté.
- Dernier diagnostic central : **0 décision active**.
- Les tables `crowdsec_blacklists` et `crowdsec6_blacklists` contiennent
  des milliers d'entrées historiques. Leur présence, leur variation
  (4 085 puis 4 074) et un `last_pull` ne prouvent pas qu'une décision
  **nouvelle** de TrueNAS est appliquée dans PF. Un probe d'authentification
  peut lui-même actualiser la date de `last_pull`.

## Option A — observation naturelle, sans mutation (préférée)

1. **TrueNAS** : attendre une décision `ban` IPv4 réellement nouvelle ;
   consulter `sudo docker exec crowdsec cscli decisions list -o json`.
   Consigner l'IP exacte, le type, l'origine et l'heure **sans données
   personnelles**. Si aucune décision n'existe : `NOT_VERIFIED`.
2. **Workstation → pfSense** : vérifier cette IP précise, sans exporter
   la liste des autres adresses PF :

   ```bash
   ssh -T home.albandrieu.com \
     'pfctl -v -t crowdsec_blacklists -T test <IP_IPV4_OBSERVEE>'
   ```

   Le marqueur verbose `M` confirme une correspondance dans la table.
   Il ne prouve pas à lui seul que toutes les règles firewall référencent
   correctement cette table.
3. Attendre l'expiration de cette décision, puis vérifier sa suppression
   du niveau LAPI et de la table PF. L'expiration/résolution d'une décision
   naturelle peut être suivie sans provoquer de trafic hostile.

## Option B — décision synthétique réversible (autorisation requise)

**Préconditions :** accès administrateur TrueNAS et pfSense, système sain,
absence d'autre décision sur `203.0.113.77` (TEST-NET-3), absence de
correspondance PF avant essai, aucune utilisation de cette adresse dans
l'infrastructure. Cette adresse de documentation ne doit pas être une IP
de gestion ou une IP réelle d'un utilisateur. Certaines politiques peuvent
écarter les adresses réservées : dans ce cas le test est **inconcluant**,
pas un échec de migration.

1. **TrueNAS — lecture seule, précondition :**

   ```bash
   sudo docker exec crowdsec cscli decisions list --ip 203.0.113.77
   ```

2. **Workstation — lecture seule, précondition :**

   ```bash
   ssh -T home.albandrieu.com \
     'pfctl -v -t crowdsec_blacklists -T test 203.0.113.77'
   ```

   **Arrêter** si une décision ou correspondance préexiste. Conserver
   l'état initial et prévoir l'étape 5 avant toute modification.

3. **TrueNAS — mutation exceptionnelle, uniquement avec accord explicite :**

   ```bash
   sudo docker exec crowdsec cscli decisions add \
     --ip 203.0.113.77 --duration 15m --type ban \
     --reason homelab-pfsense-cutover-proof
   ```

4. **Lecture seule, pendant la durée de la décision :**
   vérifier l'existence de l'IP dans `cscli decisions list --ip
   203.0.113.77`, puis le marqueur `M` de `pfctl -v -t
   crowdsec_blacklists -T test 203.0.113.77` depuis la workstation.
   Observer si nécessaire `sudo docker exec crowdsec cscli bouncers list`.
   Ne pas attribuer `last_pull` à pfSense sur cette seule base.

5. **TrueNAS — retour arrière obligatoire, indépendamment du résultat :**

   ```bash
   sudo docker exec crowdsec cscli decisions delete --ip 203.0.113.77
   ```

   `--ip` retire toutes les décisions visant cette IP : c'est pourquoi
   l'étape 1 interdit de continuer si une décision préexiste.
   Ne jamais utiliser `--all`, `pfctl -T flush` ou relancer
   le moteur CrowdSec local pfSense.

6. **Lecture seule, après la propagation :** répéter `cscli decisions
   list --ip 203.0.113.77` et `pfctl -v -t crowdsec_blacklists
   -T test 203.0.113.77`. Vérifier l'absence de décision centrale
   **et** de correspondance PF.

## Verdict et limites

**`PF_DECISION_CYCLE_PASS`** exige :
1. aucune décision et aucune correspondance PF au départ ;
2. décision centrale créée/observée, puis correspondance de **cette même IP**
   dans PF après propagation ;
3. décision supprimée/expirée puis disparition de **cette même IP** de PF ;
4. bouncer toujours opérationnel ; moteur pfSense toujours arrêté.

Sinon `PF_DECISION_CYCLE_NOT_VERIFIED`, avec le stade exact manquant.
La vérification reste séparée de l'audit HAProxy/DNS/Cloudflare.
Un match de table ne démontre pas à lui seul le blocage d'un paquet WAN :
les règles PF actives et, si nécessaire, une sonde depuis une vraie source
WAN doivent être vérifiées indépendamment.

## Références

- [CrowdSec — Gestion des décisions](https://docs.crowdsec.net/u/user_guides/decisions_mgmt/)
- [CrowdSec 1.8 — `cscli decisions list`](https://docs.crowdsec.net/docs/cscli/cscli_decisions_list/)
- [pfctl — `-T test` et marqueur `M`](https://man.openbsd.org/pfctl.8)
- [pfSense CrowdSec Small](https://docs.crowdsec.net/docs/getting_started/install_crowdsec_pfsense/)
