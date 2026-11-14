# pfSense : retrait des cibles workstation 172.17.0.57 (14/11/2026)

## Contexte

Le relevé des journaux de la workstation du 14/11 (dépôt
ansible-workstation, `docs/stabilisation-workstation-truenas.md`, ligne 12)
attribue l'essentiel des `[UFW BLOCK]` à pfSense `172.17.0.1`. Rien n'écoute
plus sur ces ports de la workstation : les services sont partis sur TrueNAS.

Comptage sur 24 h (13/11 → 14/11, journalisation ufw limitée en débit,
le volume réel est plus élevé) :

| Port | Paquets journalisés | Remarque |
| --- | ---: | --- |
| UDP 1514 | 1 391 | syslog pfSense |
| TCP 3000 | 1 295 | health-checks HAProxy, toutes les secondes |
| TCP 9000 | 499 | health-check HAProxy |
| TCP 8081 | 349 | 13/11 de 14 h à 20 h seulement |

## État relevé le 14/11 (lecture seule)

Relevé par SSH (`ssh -p 9922 admin@172.17.0.1`) dans `/conf/config.xml`,
`/var/etc/haproxy/haproxy.cfg` et l'état runtime HAProxy. L'alias SSH
`pfsense` de `~/.ssh/config` ne résout pas depuis le LAN : utiliser l'IP.

| Objet pfSense | Cible | Service aujourd'hui | Décision |
| --- | --- | --- | --- |
| Syslog `remoteserver` | `172.17.0.57:1514` | Alloy TrueNAS `172.17.0.24:1514`, déjà en `remoteserver2` | Promouvoir TrueNAS en slot 1, retirer `.57` |
| HAProxy `ntopng` (`ntopng.albandrieu.com`, frontend WAN :8082) | `172.17.0.57:3000` | App TrueNAS `172.17.0.24:31080` | Serveur `inactive` : pas de réexposition WAN du login ntopng |
| HAProxy `graylog` (`graylog.albandrieu.com`, :443 et :8082) | `172.17.0.57:9000` | App TrueNAS arrêtée volontairement (`planned`) | Serveur `inactive` |
| HAProxy `albandrieu-apache-login-honeypot` (frontend `login`, WAN :3000) | `172.17.0.57:3000` | Aucun | Serveur `inactive` et frontend `login` désactivé |
| NAT rdr WAN :8081 « albandrieu nexus 8081 » et sa règle pass associée | `172.17.0.57:8081` | Nexus TrueNAS `172.17.0.24:8081`, servi par `nexus.int.albandrieu.com` | Supprimer : la politique d'ingress bloque l'accès direct à l'origine Nexus |

Le `:8081` n'est pas un health-check HAProxy : le pool `nexus` n'est
référencé par aucun frontend. Les paquets venaient de la redirection NAT,
réfléchie depuis le LAN (source réécrite en `172.17.0.1`).

Les backends `ntopng`, `graylog` et `albandrieu-apache-login-honeypot`
répondent déjà 503 : la décision ne retire aucun accès fonctionnel.

## Hors périmètre

- `apache` / `famp` / `albandrieu` → `172.17.0.57:8082` : le service est
  vivant et ufw l'autorise depuis le LAN. Inchangé.
- Pools `nexus` (`.57:8081`) et `vault` (`.57:8200`) : référencés par aucun
  frontend, donc ni générés ni sondés. Périmés mais inertes.
- `prod_back` → `heimdall-https 172.17.0.24:30120` est DOWN : c'est le
  backend par défaut des frontends `Web_HTTPS` et `freenas`. À traiter à part.

## Procédure

### 1. Syslog

Clé dédiée : Vaultwarden `nabla/prod/pfsense-observability`, à charger dans
`PFSENSE_OBSERVABILITY_API_KEY` sans l'afficher. Lever le mode lecture
seule global de pfREST le temps du PATCH, puis le rétablir.

```bash
scripts/observability/configure-pfsense-syslog.sh --plan
```

```bash
scripts/observability/configure-pfsense-syslog.sh --apply
```

Le script reconnaît la disposition `remoteserver=.57` / `remoteserver2=Alloy`,
promeut Alloy en `remoteserver` et vide `remoteserver2`.

### 2. HAProxy et NAT

`scripts/pfsense/retire-workstation-targets.php` s'exécute sur pfSense.
`check` n'écrit rien. `apply` refuse d'écrire si l'un des objets attendus
manque, sauvegarde la configuration (une entrée dans l'historique
`Diagnostics > Backup & Restore > Config History`), recharge HAProxy puis
le filtre.

```bash
ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/retire-workstation-targets.php
```

```bash
ssh -p 9922 admin@172.17.0.1 "php -- apply" < scripts/pfsense/retire-workstation-targets.php
```

Un second `check` doit n'afficher que des lignes `OK:`.

## Vérification

Sur pfSense :

```bash
ssh -p 9922 admin@172.17.0.1 "grep -n 172.17.0.57 /var/etc/haproxy/haproxy.cfg /var/etc/syslog.d/pfSense.conf"
```

Seules les lignes `:8082` doivent rester.

Sur la workstation, après dix minutes :

```bash
journalctl -k --since -10min | grep -c 'UFW BLOCK.*SRC=172.17.0.1 '
```

## Retour arrière

Restaurer l'entrée précédente de `Diagnostics > Backup & Restore >
Config History`, ou réappliquer les valeurs du tableau ci-dessus dans
l'UI HAProxy et NAT.
