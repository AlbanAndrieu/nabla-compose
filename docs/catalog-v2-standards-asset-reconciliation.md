# Correspondances standards : Backstage et inventaires de sécurité

## Autorité et cardinalité

**Une identité déclarée** : `kind:namespace/name` depuis Backstage
(`catalog-info.yaml`). **N données observées** par entité ou ressource,
provenant des services spécialisés. Ne jamais importer une découverte
Scanopy/ntopng/Akvorado en tant que nouveau `Component` par défaut.

| Source | Donnée qui fait autorité | Destination / représentation |
| --- | --- | --- |
| Backstage | `metadata.name`, `spec.owner`, `spec.system`, `spec.dependsOn`, `metadata.links` | Projections homelab, dashboard, CycloneDX SaaSBOM |
| Compose et ressources Talos/K8s | Images, ports, réseaux, healthchecks, instance/runtime | Métadonnées d'exécution, *pas* second registre d'identité |
| Gatus | URL, intervalle, conditions de sonde | Config Gatus native, adaptateur AutoKuma ; santé observée reste externe |
| Scanopy | Hôtes, interfaces, adresses, ports, réseau découvert | Faits observés enrichis ; joindre par identifiants vérifiés |
| Akvorado | Flux NetFlow/IPFIX, interfaces, volumes, conversation réseau | Événements réseau datés, jamais des dépendances déclarées implicites |
| ntopng | Contexte et analyse de trafic, historique ClickHouse | Observations réseau corrélées |
| Cartography/Neo4j | Graphe d'actifs, relations et attack-path avec provenance | Graphe **observé** distinct du graphe Backstage déclaré |
| DSOMM | Maturité DevSecOps, preuves et évaluations humaines | Références de contrôles et preuves ; ni découvertes ni statut santé |
| DefectDojo | Findings, suivi, déduplication de vulnérabilités | Association à une entité ou un actif existant, avec preuve source |

## Règles de jointure

- **Logiciel déclaré** : référence Backstage canonique, jamais un nom affiché.
- **Services observés** : OpenTelemetry `service.namespace`, `service.name`,
  `service.instance.id` ; la correspondance vers Backstage est établie avec
  source/provenance (label Compose, annotation K8s ou règle révisée).
- **Infrastructure** : identifiant provider stable (ID de nœud K8s, ID
  d'instance fournisseur, UUID matériel) ; **IP, port, FQDN ou adresse MAC
  ne sont pas une clé primaire universelle**. Plusieurs IP/alias peuvent
  désigner un actif, et ils peuvent changer ou être réutilisés.
- Une relation réseau *observée* ne devient pas automatiquement
  `spec.dependsOn` ; ce champ Backstage décrit une dépendance **déclarée**.
- Une observation comporte au minimum `source`, `observedAt`, `identity`,
  `entityRef` (uniquement si prouvé), `evidence` et `confidence`, et doit
  pouvoir être dédupliquée par identifiant de preuve/idempotence.
- Séparer `declared`, `observed` et `finding` : une vulnérabilité,
  une sonde négative ou une découverte ne modifie jamais `operational-state`
  dans les descripteurs Backstage.

## Référentiels et normes

| Standard | Usage recommandé | Ce qu'il ne faut pas faire |
| --- | --- | --- |
| [Backstage Catalog descriptor](https://backstage.io/docs/features/software-catalog/descriptor-format/) | Identités, ownership, système, relations | Réinventer un `services.json` manuel |
| [CycloneDX 1.7 (ECMA-424)](https://cyclonedx.org/docs/1.7/json/) | SBOM/SaaSBOM, services, dépendances et preuves supply-chain | Utiliser le BOM comme vérité runtime |
| [SPDX 3.0](https://spdx.github.io/spdx-spec/v3.0/) | Échanges SBOM et licensing quand exigés par les consommateurs | Maintenir simultanément deux BOMs à la main |
| [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/resource/service/) | Identité des services observés et instances, traces, métriques | Remplacer `service.name` par des noms d'affichage |
| [NIST CSF 2.0](https://www.nist.gov/cyberframework) | Fonctions de gouvernance, identification et détection, notamment actifs | Confondre catégories CSF et types de composants |
| [NIST OSCAL](https://pages.nist.gov/OSCAL/) | Catalogues/profils de contrôles, plans de sécurité, résultats d'évaluation | Mettre tous les contrôles dans `catalog-info.yaml` |
| [OWASP DSOMM](https://dsomm.owasp.org/) | Activités/maturité DevSecOps et éléments de preuve | Déduire automatiquement une maturité d'une simple CI verte |
| [CSAF 2.0](https://docs.oasis-open.org/csaf/csaf/v2.0/csaf-v2.0.html) | Avis de vulnérabilités et statut produit | Prendre CSAF pour un inventaire d'actifs |
| [MITRE ATT&CK](https://attack.mitre.org/) | Taxonomie des techniques et détection | Remplacer la représentation des services par des techniques |
| [CIS Controls](https://www.cisecurity.org/controls) | Mesures opérationnelles de gestion d'actifs, logiciels et défense | Conclure à la conformité à partir de scans non revus |
| [ISO/IEC 27001:2022](https://www.iso.org/standard/27001) | SMSI, gouvernance des risques et contrôles de sécurité | Dupliquer la déclaration d'applicabilité dans chaque service |

## Écarts traités dans la PR #265

- Les quatre services Akvorado disposaient de labels
  `com.albandrieu.nabla.entity-ref` mais pas des descripteurs correspondants :
  `akvorado-orchestrator`, `akvorado-inlet`, `akvorado-outlet`,
  `akvorado-console` sont maintenant décrits avec état **planned**, sans les
  considérer comme déployés. Les dépendances transverses Kafka/ClickHouse sont
  déclarées en Backstage ; le `depends_on` Compose local reste à Compose.
- Scanopy et son daemon sont liés par `spec.dependsOn` ; le stockage partagé
  PostgreSQL conserve une référence `Resource`, pas une copie de la base.
- ntopng dépend du même ClickHouse sans recréer une identité de datastore.
- Cartography ingère dans Neo4j : il produit une **vue observée**, sans
  modifier les relations Backstage à partir du trafic seul.
- DSOMM et son baseline restent `planned`; les preuves de maturité doivent
  faire l'objet d'une revue humaine.

## Poursuite proposée

1. Établir des adaptateurs d'observation *read-only* Scanopy, ntopng,
   Akvorado/ClickHouse et Cartography, avec provenance et horodatage.
2. Associer les observations à Backstage seulement sur un identifiant fiable ;
   signaler les ambiguïtés, sans inventer de référence.
3. Envoyer métriques vers Prometheus/OpenTelemetry et findings vers
   DefectDojo privé ; réutiliser les mécanismes d'import existants.
4. Conserver les standards OSCAL/CSAF/SPDX comme **formats d'échange
   optionnels selon les besoins**, sans créer de nouveau catalogue parallèle.
5. Retirer les derniers lecteurs du Catalog v1 dans FastAPI, le site et
   TrueNAS ; ne pas annoncer la suppression v1 tant que ceux-ci existent.
