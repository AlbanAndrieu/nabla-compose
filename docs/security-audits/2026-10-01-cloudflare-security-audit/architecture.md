# Architecture snapshot — security audit

Reviewed source ref: `4fa9eb8d262bab437c99773475fcf84e489be863`.

## Security-relevant planes

- **TrueNAS application plane:** repository-managed Compose/Custom Apps publish selected LAN ports and mount application datasets under `/mnt/cpool`.
- **Deployment authority:** Doco-CD consumes Git state and reaches Docker through a restricted Docker socket proxy; deployment-trigger authentication and proxy permissions are high-value boundaries.
- **Privileged discovery/observability:** scanners such as Scanopy can require host networking, host interfaces or container-runtime visibility and therefore sit close to the host trust boundary.
- **Secrets:** Vaultwarden is the transitional authority; repository metadata maps secret names while runtime materializations live outside Git under `/mnt/cpool/secrets`.
- **Kubernetes/Talos:** cluster manifests and operator scripts manage an independent privileged control plane; this quick run did not attempt live cluster verification.
- **CI/supply chain:** GitHub Actions executes repository code with scoped GitHub tokens and downloads selected third-party tooling.

## Trust boundaries prioritized in this quick pass

1. LAN/untrusted network input -> privileged host/container tooling.
2. Git/webhook input -> Doco-CD -> Docker deployment authority.
3. Pull-request/repository source -> GitHub Actions token and third-party actions.
4. Remote installer/upstream artifact -> developer/operator shell.
5. Generated script data -> privileged shell evaluation.

This is a source map for the one-shot review, not a complete attack-surface inventory.
