# Runbook canonique — localiser un défaut Catalogue → FastAPI → Site

**Propriétaire :** Compose (observateur et routage). **Mode :** lecture seule.
[Architecture et gateway](../api-gateway-selection.md).
[Contrat FastAPI](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/diagnostic-provenance-contract.md).
[Contrat Site](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/homelab-diagnostics-and-access.md).

## Interprétation

`HTTP 200` du site ne prouve pas le fonctionnement du catalogue.
`HTTP 302` Cloudflare Access signifie une décision edge, pas la
joignabilité du backend. `401/403` peut être un refus normal.
`503 catalog_validation` signifie source/catalogue invalide ;
`503 upstream_timeout` signifie absence de réponse **depuis le point
d'observation indiqué**, pas TrueNAS down. Une sonde TrueNAS en erreur
doit garder son observateur et son horodatage.

| Stage / preuve | Propriétaire | Prochain diagnostic |
| --- | --- | --- |
| `catalog_validation` | Compose artifact + FastAPI reader | digest, source, `catalogRevision` |
| `upstream_auth` | connexion Site→FastAPI ou API→catalogue | clé/role et refus sans secret |
| `upstream_network`/`upstream_timeout` | réseau de l'observateur | DNS, TCP, TLS au bon vantage |
| `api_unavailable`, `tcp_connect`, `tls_handshake` | FastAPI/TrueNAS ou pfSense | réutiliser le ledger existant |
| `owner-boundary` | identité/réseau | JWT Access, CIDR et proxy de confiance |
| `unknown`/`not-executed`/`stale` | lecteur | aucune conclusion UP/DOWN |

## Procédure opérateur

1. Relever la **date** et le `SHA` déployé sur Vercel et FastAPI.
2. Vérifier les aliases de production dans Vercel.
3. Vérifier si `/api/homelab-access` autorise seulement le mode attendu.
4. Vérifier le résultat HTTP **sans imprimer** cookies ni jetons.
5. Inspecter `X-Nabla-Diagnostic-Stage` seulement sur une requête autorisée.
6. Vérifier la révision `catalogRevision` et la source générée dans Compose.
7. Lire les diagnostics FastAPI déjà collectés ; **ne pas relancer** les sondes
   bruyantes sur pfSense/TrueNAS pour un simple 503 catalogue.
8. Vérifier séparément DNS et connectivité depuis workstation puis TrueNAS
   selon [runbook FastAPI TrueNAS](fastapi-sample-truenas-diagnostics.md).
9. Comparer l'observation Cloudflare Access à l'API origine ; aucune 302 ne
   valide l'application derrière Cloudflare.
10. Tester PUBLIC hors LAN et OWNER dans un environnement autorisé avant
    d'affirmer un succès fonctionnel.

Aucune procédure ici ne redémarre TrueNAS, Traefik, Pi-hole, pfSense ou
les collecteurs. Aucune clé ou adresse privée n'est mise dans un ticket
public. Les incidents datés restent archivés comme historique, pas comme
secondes sources actives. Le POC APISIX exige un changement séparé et un
rollback documenté.
