# Modèle de menaces — accès temporaire Cloudflare aux services TrueNAS

Statut : proposition de contrôle, **aucune exposition modifiée par ce document**. Référence : `TM-TRUENAS-001`. À rattacher à l'évaluation OWASP DSOMM par les UUID officiels du snapshot, sans créer d'activité DSOMM fictive.

## Identités et séparation des privilèges

- L'accès interactif à Cloudflare Zero Trust s'effectue avec une **YubiKey / FIDO2** : ne pas confondre cette authentification humaine forte avec les droits d'une API key ou d'un API token.
- L'**Account ID** Cloudflare est un identifiant de ressource, **pas un secret ni un droit**.
- Préférer des **API tokens** à portée restreinte aux *Global API Keys*. Ne jamais inclure leur valeur dans la documentation, les logs ou le dépôt.
- **Observer** : token lecture seule, restreint au compte, autorisations Tunnel Read, Access Apps/Policies Read ; Service Tokens Read seulement si la corrélation l'exige. Il ne peut ni publier un hostname ni modifier une politique Access.
- **Opérateur d'exposition temporaire** : autre identité/token, non réutilisé par FastAPI, avec les seules permissions d'édition des objets Tunnel/Access explicitement gérés ; le cloisonner dans un secret runtime lisible uniquement par l'opérateur. Les permissions exactes doivent être vérifiées sur l'API Cloudflare effective avant activation.
- **Connecteur cloudflared** : identifier ses réseaux, privilèges et routes sortantes ; le secret du connecteur n'accorde pas de facto le droit d'administrer l'API Cloudflare, mais sa compromission crée un risque de pivot réseau.

## Sens de `external`

`external: false` signifie **exposition extérieure non souhaitée dans la politique du catalogue** ; ce n'est ni une preuve d'inaccessibilité réseau ni un indicateur de santé. Une `tunnelUrl` préexistante n'est pas la preuve qu'un Tunnel est configuré, qu'Access protège la route ou que l'origine répond. L'audit doit corréler catalogue, Cloudflare Tunnel, Access et tests externes.

LanguageTool : une seule identité canonique `languagetool`, `external: false`, sonde interne HTTP sur `172.17.0.24:8010/v2/check`. Ne pas créer de route publique à partir de cette déclaration.

## Accès extérieur ponctuel — politique proposée

Pour AdGuard Home, Heimdall et les interfaces administratives, privilégier d'abord une **route permanente protégée par Access** (aucun accès applicatif sans authentification), si l'objectif est un accès d'urgence rapide. Il n'est alors pas nécessaire de basculer l'exposition à chaque usage. Tester depuis l'extérieur :
1. anonyme sans redirection suivie : challenge/refus par Access, jamais le contenu de l'interface ;
2. identité autorisée FIDO2 : accès fonctionnel à l'application ;
3. route WAN directe / autre domaine / port alternatif : pas de contournement d'Access ;
4. accès API ou origin : vérification explicite des droits applicatifs et des logs.

Pour un service **désactivé par défaut**, l'automatisation JIT (just-in-time) peut activer une route Tunnel **et** une application/politique Access restrictives, pour une durée courte, puis les désactiver automatiquement. Conditions minimales :
- liste blanche de hostnames et backends ; jamais d'URL arbitraire ni de wildcard ;
- création/vérification de la politique Access **avant** toute publication de route ;
- fail-closed en cas de politique introuvable ou d'API inaccessible ;
- expiration **côté serveur** avec réconciliation périodique indépendante du poste initiateur, y compris après reboot ;
- verrou d'exécution, idempotence, audit d'identité et d'heure, dry-run et confirmation avant mutation ;
- désactivation de la route au terme du bail ; conserver l'application Access restrictive plutôt que la supprimer en premier ;
- refus par défaut pour TrueNAS admin, pfSense admin, Secrets/DB et interfaces Docker ; ces actifs passent par VPN/WARP privé.
- ne pas supposer qu'un `external: false` doit automatiquement déclencher une publication.

**À ne pas faire** : script local `sleep 1h && disable` comme seule protection, publication sans Access, jeton administrateur global dans FastAPI, bascule d'Access sur « bypass » ou désactivation d'Access pour « ouvrir » un service.

## STRIDE — TM-TRUENAS-001

| Risque | Scénario | Contrôle / preuve |
| --- | --- | --- |
| Spoofing | Vol de session ou identité de service | FIDO2, session Access restrictive, credentials isolés |
| Tampering | Modification DNS AdGuard / de la configuration Tunnel | least privilege, journal d'audit, revue des changements |
| Repudiation | Bascule JIT sans traçabilité | identité initiatrice, journal immuable des actions |
| Information disclosure | Route alternative non protégée, API Garage ou TrueNAS exposée | test négatif depuis Internet, inventaire des ingress |
| Denial of service | Saturation de la route Cloudflare/origine | rate limiting, quotas, alarmes, politique de timeout |
| Elevation of privilege | Pivot cloudflared vers TrueNAS :7000 ou pfSense | segmentation Docker/LAN et tests egress négatifs |

## Contrat de validation avant déploiement

- Inventaire réel des Public Hostnames Tunnel et des applications/politiques Access, sans inférer de sécurité depuis HTTP 200 seul.
- Matrice des privilèges de l'API token observateur et de l'opérateur de changement, compte et ressources autorisées.
- Évaluation de l'accès depuis le réseau de `cloudflared` vers `172.17.0.24:7000` et `172.17.0.1:10443`.
- Tests automatisés : dry-run, idempotence, erreur 401/403/5xx, coupure réseau, expiration du bail, double demande concurrente et protection contre ouverture anonyme.
- Corrélation DSOMM : activités officielles de threat modeling, contrôle d'accès, infrastructure hardening, segmentation et monitoring, avec UUID upstream et preuves de test référencées.
