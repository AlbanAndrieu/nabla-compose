# Dormant GitHub Actions runner on TrueNAS 26 LXC

This runbook prepares a GitHub Actions self-hosted runner inside a TrueNAS 26 Linux container without registering or activating it.

The repository is public. GitHub explicitly recommends using self-hosted runners only with private repositories because a malicious pull request from a fork can execute untrusted code on the runner. For that reason, this runner must remain disconnected until a dedicated trusted workflow and access policy are designed.

The runner toolchain is based on the modernized `runner-build` profile from [`AlbanAndrieu/ansible-jenkins-slave-docker`](https://github.com/AlbanAndrieu/ansible-jenkins-slave-docker). Reuse its tool/version contract; do **not** run the historical all-in-one Jenkins Docker image as the LXC guest.

## Current status

The default CI does **not** use this runner.

Pull requests run infrastructure static checks on GitHub-hosted `ubuntu-latest` runners. They do not receive homelab credentials, access the internal state backend, or execute a real Terragrunt plan.

This LXC preparation is therefore optional and dormant.

## Why LXC

TrueNAS 26 fully supports Linux containers (LXC). They are lightweight and keep their own filesystem, processes, and network configuration while sharing the TrueNAS kernel.

The current `PjSalty/truenas` provider does not expose a dedicated LXC/container resource, so the initial container creation remains a manual TrueNAS operation.

## Base operating system and build-tool contract

Use **Ubuntu 24.04 LTS** for the first runner. It matches the current stable GitHub-hosted Ubuntu baseline. Treat Ubuntu 26.04 as a later compatibility target while GitHub's 26.04 runner image remains preview.

The baseline must support the two current build targets without baking their application dependencies into the LXC image:

| Tool | Baseline | Primary consumer |
| --- | --- | --- |
| Ubuntu | 24.04 LTS | runner platform |
| GitHub Actions runner | 2.337.0 or newer reviewed pinned release | Actions runtime |
| Python | 3.13.x | `fastapi-sample` |
| `uv` | repository-compatible current pinned release | `fastapi-sample` |
| Node.js | 25.9.0 | `nabla-site-alban` local/CI parity |
| npm | 11.17.0 | `nabla-site-alban` |
| `mise` | pinned current release | repository tool bootstrap |
| Docker CLI / Buildx / Compose | current supported Docker packages | image/build workflows |
| Playwright | installed by the project lockfile | `nabla-site-alban` browser tests |

Keep `git`, `curl`, `jq`, `rsync`, `openssh-client`, archive tools and native build essentials in the base. Let each project own higher-level tools through `mise.toml`, `pyproject.toml`/`uv.lock`, `package.json`/lockfiles and its quality-gate scripts.

Do not carry the historical Jenkins image's Selenium base, PHP/Apache, s6-overlay, OCR/LibreOffice, Java, Nomad, Go or other unrelated stacks into this runner unless a measured workflow requires one of them. This keeps patching, startup time, image size and attack surface bounded.

## Recommended TrueNAS container settings

Create the container from **Containers → Create New Container** with settings similar to:

| Setting | Recommended value |
| --- | --- |
| Name | `github-runner` |
| Image | Ubuntu 24.04 LTS |
| Autostart | **OFF** |
| CPU | 2 vCPU initially; raise only from measured build pressure |
| Memory | 4 GiB initially; measure Next.js/Python peak before increasing |
| Storage | 20–40 GiB plus dedicated cache/work storage |
| ID Map Type | **Default** / unprivileged for the preferred mode |
| Capabilities | **DEFAULT** for the preferred mode |
| Network | existing trusted bridge such as `br0`, or a deliberately restricted runner segment |
| Host filesystem mounts | dedicated runner work/cache only |
| Docker socket | never mount the TrueNAS Docker socket |

## Docker / nested-container decision gate

TrueNAS 26 documents nested runtimes such as Docker inside LXC, but requires **ID Map Type = Privileged** and **Capabilities = ALLOW**. That removes the normal UID isolation and materially increases host exposure.

Use this decision order:

1. keep the main runner LXC unprivileged when workflows do not need a local Docker daemon;
2. evaluate a dedicated remote BuildKit/Docker endpoint for image builds while the LXC stays unprivileged;
3. only if local nested Docker is operationally required, create a **separate trusted-only runner** using the TrueNAS documented privileged/ALLOW settings and no sensitive host mounts;
4. never mount `/var/run/docker.sock` from the TrueNAS host into either runner;
5. if the required isolation cannot be achieved safely, use a dedicated VM instead of weakening the primary LXC boundary.

Do not describe a privileged nested-Docker LXC as equivalent to the normal unprivileged LXC security boundary.

## Network and trust policy

The dormant LXC only needs outbound connectivity to prepare the runner package.

When it is eventually activated, allow only the outbound GitHub endpoints required by GitHub Actions plus explicitly approved internal endpoints. Do not give the runner broad access to Vaultwarden, TrueNAS management, storage datasets, or other homelab services by default.

- Do **not** route untrusted public pull-request code to this runner.
- Keep ordinary public PR validation on GitHub-hosted runners.
- Reserve the homelab runner for trusted/manual workflows, protected branches, or explicitly trusted commits.
- Keep registration tokens, API keys and deployment credentials out of Git and out of the LXC image.
- Inject job credentials at runtime with the smallest required scope.
- Use a dedicated work/cache dataset; never mount `cpool/ix-apps`, application-secret datasets, or TrueNAS system datasets.
- Keep LXC autostart disabled until registration, cleanup and acceptance tests are reviewed.

## Prepare the runner files

Copy the repository script into the LXC and run it as root:

```bash
sudo bash scripts/github-runner/prepare-lxc.sh
```

Update the script to the reviewed GitHub Actions Runner `2.337.0` baseline (or the then-current explicitly reviewed pinned release) and verify the official SHA-256 checksum for Linux x64 or arm64 before extraction.

It installs the runner under:

```text
/opt/actions-runner
```

with the local service identity:

```text
github-runner
```

The script intentionally does **not**:

- execute `config.sh`;
- request or consume a GitHub runner registration token;
- execute `run.sh`;
- install a systemd runner service;
- enable container autostart.

At this point the LXC is prepared but cannot accept any GitHub Actions job.

## Project acceptance gates

### `AlbanAndrieu/fastapi-sample`

A clean checkout must prove the Python 3.13/uv contract and the repository-owned agent gate:

```bash
python --version
uv --version
uv sync --locked
mise run agent-fix
mise run agent-publish
```

Docker build/test jobs must use either the reviewed nested-runtime path or a reviewed remote builder. They must never use the TrueNAS host Docker socket.

### `AlbanAndrieu/nabla-site-alban`

A clean checkout must prove Node/npm parity, the local-first quality gate and the production build:

```bash
node --version
npm --version
npm ci
npm run quality:agent:fix
npm run quality:agent:publish
npm run build
npx playwright install chromium
npm run test:baselines
```

Expected baseline is Node `v25.9.0` and npm `11.17.0`. Install the Playwright browser from the project dependency/lockfile rather than permanently baking an unrelated browser version into the LXC.

Cache npm/Next/Playwright and uv data on dedicated runner cache storage keyed by lockfiles/tool versions. Never cache repository secrets.

## Verify the dormant state

Inside the LXC:

```bash
pgrep -af Runner.Listener || true
systemctl list-unit-files 'actions.runner*' --no-pager || true
ls -la /opt/actions-runner
```

Expected result:

- no `Runner.Listener` process;
- no installed `actions.runner.*` service;
- runner binaries are present under `/opt/actions-runner`.

In GitHub **Settings → Actions → Runners**, no runner should appear because registration has not happened.

## Manual activation later

Only perform this section when the repository/workflow trust model is ready.

1. In GitHub, open **Settings → Actions → Runners → New self-hosted runner**.
2. Generate a fresh time-limited registration token.
3. Run the generated `config.sh` command as the `github-runner` user, not as root.
4. Use explicit labels such as `truenas`, `infra`, `trusted`, `python313` and `node25`; do not reuse the old `infra-runners` label automatically.
5. Test with a workflow that can only be triggered from trusted branches or a protected environment.
6. Install/start the service only after the isolation and permissions have been reviewed.
7. Enable TrueNAS LXC Autostart only if persistent availability is actually desired.

Example shape only — use the fresh command shown by GitHub at activation time:

```bash
sudo -u github-runner -H bash -c \
  'cd /opt/actions-runner && ./config.sh --url <trusted GitHub scope> --token <fresh token> --labels truenas,infra,trusted,python313,node25'
```

Do not commit the registration token. GitHub registration tokens are time-limited and should be generated only at activation time.

## Implementation roadmap

- [ ] land and validate the focused `runner-build` profile in `ansible-jenkins-slave-docker`;
- [ ] update `scripts/github-runner/prepare-lxc.sh` to the reviewed runner release and shared build-tool contract;
- [ ] add an idempotent LXC bootstrap/provision path without registering the runner;
- [ ] create the Ubuntu 24.04 LXC with autostart OFF and no sensitive host mounts;
- [ ] smoke-build `fastapi-sample` and `nabla-site-alban` from clean checkouts;
- [ ] decide unprivileged + remote builder versus separate privileged nested-Docker runner using measured workflow requirements;
- [ ] prove cleanup of `_work`, temporary credentials and per-job processes;
- [ ] register only the trusted workflow scope after the security review;
- [ ] measure build duration and cache-hit rate against GitHub-hosted runners before moving additional trusted jobs;
- [ ] evaluate Ubuntu 26.04 once GitHub's runner image is stable/GA and all project gates pass there.

## Future preferred architecture

```text
public pull request
  -> GitHub-hosted runner
  -> fmt / lint / tests / static security checks

trusted manual/protected workflow
  -> TrueNAS LXC runner (unprivileged preferred)
  -> project quality/build gates
  -> remote builder when Docker is required

exception: trusted Docker-heavy workflow
  -> separately reviewed privileged LXC or dedicated VM
  -> nested Docker
```

Once Talos/Kubernetes is sufficiently stable, evaluate GitHub Actions Runner Controller with ephemeral runners instead of keeping a long-lived privileged runner.

## References

- TrueNAS 26 containers: https://www.truenas.com/docs/scale/26/containers/
- TrueNAS container management / nested containers: https://www.truenas.com/docs/scale/26/containers/managingcontainers/
- GitHub self-hosted runners: https://docs.github.com/en/actions/concepts/runners/self-hosted-runners
- Adding a self-hosted runner: https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners
- GitHub runner releases: https://github.com/actions/runner/releases
- `ansible-jenkins-slave-docker`: https://github.com/AlbanAndrieu/ansible-jenkins-slave-docker
