# Catalog v2 — standards, correspondances et provenance

*Décision d'architecture : 20 octobre 2026. Sources de référence officielles indiquées ci-dessous.*

## Règle de déduplication

Une **identité déclarative** est identifiée par la référence canonique Backstage
`kind:namespace/name`, et jamais par un nom d'affichage, une adresse IP, un
port TCP, un conteneur observé ou une URL Gatus.

| Responsabilité | Autorité canonique | Schéma / standard réutilisé |
| --- | --- | --- |
| Identité logique, propriétaire, relations, système, classification | `catalog-info.yaml` | [Backstage Software Catalog](https://backstage.io/docs/features/software-catalog/descriptor-format/) |
| Composition et runtime | `apps/*/compose.yml`, étiquette `com.albandrieu.nabla.entity-ref` | [Compose Specification](https://compose-spec.io/) |
| Readiness/health et preuves synthétiques | `config/monitoring/gatus-endpoints.yml` | [Gatus YAML](https://github.com/TwiN/gatus) ; AutoKuma généré |
| Observabilité par instance et environnement | Prometheus / OpenTelemetry / Grafana | [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/resource/service/) |
| Échange d'inventaire sécurité/SaaS et graphe de dépendances | `catalog/generated/homelab.cdx.json` | [CycloneDX 1.7 / ECMA-424](https://cyclonedx.org/specification/overview/) |
| SBOM packages et licences (si nécessaire) | Sortie des scanners, non les descripteurs Backstage | [SPDX 3.0.1](https://spdx.github.io/spdx-spec/v3.0/) |
| Événements et détection | Logs enrichis au collecteur, sans changer l'asset ID | [OCSF](https://github.com/ocsf/ocsf-schema), OTel |
| Contrôles et preuves de conformité | Référentiel de contrôles / DSOMM, pas un catalogue de conteneurs | [NIST OSCAL](https://pages.nist.gov/OSCAL/learn/concepts/layer/control/catalog/) |
| Findings, SBOM et décisions de vulnérabilité | DefectDojo / Dependency-Track | CycloneDX, CVE/CVSS ; VEX via [CSAF](https://docs.oasis-open.org/csaf/csaf/v2.0/csaf-v2.0-csd02.html) uniquement pour un cas documenté |

**Ne pas construire un méta-schéma Nabla** qui regroupe ces modèles. Les
projections servent l'interopérabilité, jamais la maintenance d'un deuxième
registre de services.

## Correspondances des cinq outils étudiés

| Service déclaré | Rôle réel | Correspondance, sans copier la source |
| --- | --- | --- |
| `component:default/scanopy` + `scanopy-daemon` | Découverte active du LAN, ports et conteneurs | Distinguer actifs **observés** des services **déclarés**. Une association n'est validée qu'avec une identité fournisseur et sa provenance. |
| `component:default/cartography` | Ingesteur de graphe de sécurité, profil Compose `manual` | Dépend de `resource:default/neo4j-security`. Neo4j n'est pas la CMDB canonique des déclarations. |
| `component:default/akvorado-*` (4 entités, état `planned`) | Collecteur, processeur, contrôleur et console IPFIX/NetFlow | `system:default/nabla-homelab`, Kafka et ClickHouse ; **ne pas** les considérer en production tant que l'état déclaré reste `planned`. |
| `component:default/ntopng` | Analyse de trafic réseau | `dependsOn: resource:default/clickhouse`. Le flux ne crée aucune entité Backstage. |
| `component:default/dsomm` et `dsomm-baseline` | Évaluation maturité DevSecOps et collecteur de preuves GitHub | Relation `subcomponentOf`. Une preuve automatisée ne valide pas à elle seule une pratique ou un niveau DSOMM. |

**Dépendance ne signifie pas ingérer deux fois :** Akvorado, ntopng et
Cartography conservent des données distinctes avec des finalités différentes.
Ne pas envoyer directement les flux bruts dans Neo4j ni déclarer un `dependsOn`
entre Cartography et Scanopy sans un vrai connecteur de données.

### Identifiants et rapprochement : contrat recommandé

- **Déclaratif** : Backstage `entityRef` stable, sans adresse IP.
- **Docker** : project/service Compose + ID de conteneur *observé* et date.
- **Kubernetes** : namespace, Service et UID des objets observés.
- **Réseau** : identité du collecteur + IP/MAC/port + horodatage et périmètre ;
  une adresse IP DHCP est un attribut temporel, **jamais** un identifiant stable.
- **Provenance** : source, identifiant fournisseur, environnement, horodatage,
  confiance, et lien éventuel vers un `entityRef`. Garder plusieurs observations
  concurrentes sans écraser l'autorité déclarative.

Relier les informations dans Cartography/Neo4j via un adaptateur d'enrichissement
**lecture seule** quand des API d'export documentées existent. Ne pas inventer
de contrat direct Scanopy/ntopng/Akvorado avant vérification.

## Correspondances aux cadres de sécurité reconnus

| Cadre | Usage pertinent | Exemple de preuve, non preuve automatique de conformité |
| --- | --- | --- |
| [NIST CSF 2.0](https://www.nist.gov/cyberframework/informative-references) | Gouvernance et suivi du risque ; catégorie **ID.AM** | Couverture des actifs déclarés et découverts |
| [CIS Controls v8.1](https://www.cisecurity.org/controls/cis-controls-list) | Contrôles 1 (actifs), 2 (logiciels), 7 (vulnérabilités), 8 (logs), 12 (réseau) | Différence entre actifs Docker/Scanopy et actifs Backstage |
| ISO/IEC 27001:2022 / 27002:2022 | SMSI et contrôles organisationnels/techniques, inventaire et gestion des actifs | Evidence d'inventaire et journal de revue ; pas de badge « ISO compliant » implicite |
| [NIST SP 800-207](https://csrc.nist.gov/pubs/sp/800/207/final) | Zero Trust, identités, privilèges et accès aux APIs | Restrictions par identité et absence de socket Docker administrateur direct |
| [OWASP SAMM](https://owaspsamm.org/model/) et DSOMM | Maturité AppSec / DevSecOps | Baselines DSOMM à valider humainement, ne pas les confondre avec SAMM |
| [OSCAL](https://pages.nist.gov/OSCAL/learn/concepts/layer/control/catalog/) | Interopérabilité machine-readable des contrôles/profils et résultats d'évaluation | Références de contrôle et evidence séparées des services |
| [OCSF](https://github.com/ocsf/ocsf-schema) | Événements de sécurité, *pas* CMDB | Normalisation d'événements au collecteur puis jointure sur identité/provenance |

Aucun tag `nist-*`, `security` ou `devsecops` du catalogue ne représente
une certification, un contrôle satisfait ou un score de maturité. Les vrais
statuts d'évaluation viennent du système de preuves et des revues.

## Risques de sécurité détectés

**P1 — Scanopy :** le daemon utilise `privileged: true`, le réseau host
et `/var/run/docker.sock:/var/run/docker.sock:ro`. Le suffixe `:ro`
empêche l'écriture sur le fichier monté, **pas** les appels d'administration
possibles via l'API Docker. L'accès est donc particulièrement sensible.
[Scanopy documente un *Docker Proxy credential*](https://scanopy.net/docs/guides/integrations/docker/)
pour la découverte limitée. Réutiliser le `docker-socket-proxy` TrueNAS
**après** vérification des ACL et du chemin réseau. Garder `POST`/`EXEC`
bloqués par défaut : leur activation autoriserait de l'exécution dans les
conteneurs et nécessiterait une acceptation de risque explicite. Ne pas exposer
le proxy sur le WAN.

**P1 — Flux :** Akvorado écoute UDP 2055 uniquement sur l'adresse LAN
déclarée. Éviter toute publication WAN. Akvorado et ntopng peuvent capter
des adresses/pairs de trafic et des métadonnées sensibles ; exporter seulement
des agrégats nécessaires, avec rétention et accès restreints.

**P2 — Cartography/Neo4j :** utiliser des credentials strictement limités,
ne pas accorder à l'ingesteur un accès admin universel. Les graphes peuvent
révéler des privilèges et chemins d'attaque ; les garder privés.

**P2 — DSOMM :** le baseline GitHub n'est qu'une collecte technique.
Conserver le statut `planned` et éviter d'afficher une validation
d'un contrôle sans validation humaine et preuve traçable.

## Gates de contrat, sans parité v1 forcée

- Les `entityRef` doivent être uniques ; un `dependsOn` doit référencer
  une entité existante.
- Les services `planned/disabled` ne deviennent pas des cartes activables
  ni des sondes attendues en production.
- Les artefacts Gatus/AutoKuma doivent être dérivés du même YAML natif.
- Les projections CycloneDX excluent `Group`, `Domain` et `System`
  des services exécutables.
- La qualité CI et les contrôles de secrets restent applicables ; aucune
  exigence de correspondance exhaustive entre l'ancien et le nouveau catalogue.

## Provisional BIA assumptions (not audited conclusions)

Gatus and ntopng are independent application capabilities, not subcomponents
of another service. They therefore have provisional **direct** BIA profiles
rather than a fictional Backstage parent or fabricated dependent.

- Gatus: current provisional `low` business-criticality; the ability to
  manually verify endpoints is the stated continuity baseline.
- ntopng: provisional `medium` based on confidentiality impacts of traffic
  metadata; flow observability can be reconstructed from authoritative sources.

The values `MTPD=P7D`, `RTO=P3D` are **planning assumptions** for the
repository contract, not operator-validated recovery objectives. Review
business impacts, RTO/RPO and retention with the service owner before relying
on them for a formal ISO 27001 or continuity assessment. These labels never
represent runtime health evidence.
