# Dormant GitHub Actions runner on TrueNAS 26 LXC

This runbook prepares a GitHub Actions self-hosted runner inside a TrueNAS 26 Linux container without registering or activating it.

The repository is public. GitHub explicitly recommends using self-hosted runners only with private repositories because a malicious pull request from a fork can execute untrusted code on the runner. For that reason, this runner must remain disconnected until a dedicated trusted workflow and access policy are designed.

## Current status

The default CI does **not** use this runner.

Pull requests run infrastructure static checks on GitHub-hosted `ubuntu-latest` runners. They do not receive homelab credentials, access the internal state backend, or execute a real Terragrunt plan.

This LXC preparation is therefore optional and dormant.

## Why LXC

TrueNAS 26 fully supports Linux containers (LXC). They are lightweight and keep their own filesystem, processes, and network configuration while sharing the TrueNAS kernel.

The current `PjSalty/truenas` provider does not expose a dedicated LXC/container resource, so the initial container creation remains a manual TrueNAS operation.

## Recommended TrueNAS container settings

Create the container from **Containers → Create New Container** with settings similar to:

| Setting | Recommended value |
| --- | --- |
| Name | `github-runner` |
| Image | Ubuntu 24.04 LTS or Debian 13 |
| Autostart | **OFF** |
| CPU | 2 vCPU initially |
| Memory | 2–4 GiB initially |
| Storage | ~20 GiB initially |
| ID Map Type | **Default** / unprivileged |
| Capabilities | **DEFAULT** |
| Network | existing trusted bridge such as `br0`, or TrueNAS automatic NAT |
| Host filesystem mounts | none initially |
| Docker socket | never mount the TrueNAS Docker socket |

Do not choose `Privileged` or `Capabilities=ALLOW` for a normal GitHub runner. TrueNAS documents those options for nested container runtimes such as Docker-in-LXC, but privileged mode removes UID isolation from the TrueNAS host.

If future Actions jobs genuinely require Docker container actions, prefer a separate VM or a more strongly isolated ephemeral runner instead of weakening this LXC.

## Network policy

The dormant LXC only needs outbound connectivity to prepare the runner package.

When it is eventually activated, allow only the outbound GitHub endpoints required by GitHub Actions plus explicitly approved internal endpoints. Do not give the runner broad access to Vaultwarden, TrueNAS management, storage datasets, or other homelab services by default.

## Prepare the runner files

Copy the repository script into the LXC and run it as root:

```bash
sudo bash scripts/github-runner/prepare-lxc.sh
```

The script currently pins GitHub Actions Runner `2.336.0` and verifies the official SHA-256 checksum for Linux x64 or arm64 before extraction.

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
4. Use explicit labels such as `truenas`, `infra`, and `trusted`; do not reuse the old `infra-runners` label automatically.
5. Test with a workflow that can only be triggered from trusted branches or a protected environment.
6. Install/start the service only after the isolation and permissions have been reviewed.
7. Enable TrueNAS LXC Autostart only if persistent availability is actually desired.

Example shape only — use the fresh command shown by GitHub at activation time:

```bash
sudo -u github-runner -H bash -c \
  'cd /opt/actions-runner && ./config.sh --url <trusted GitHub scope> --token <fresh token> --labels truenas,infra,trusted'
```

Do not commit the registration token. GitHub registration tokens are time-limited and should be generated only at activation time.

## Future preferred architecture

For infrastructure jobs that need homelab access, prefer an isolated trusted execution path:

```text
public pull request
  -> GitHub-hosted runner
  -> fmt / lint / static security checks only

trusted manual/protected workflow
  -> isolated self-hosted runner
  -> internal state / TrueNAS API / real Terragrunt plan
```

Once Talos/Kubernetes is available, evaluate GitHub Actions Runner Controller with ephemeral runners instead of keeping a long-lived privileged runner.

## References

- TrueNAS 26 containers: https://www.truenas.com/docs/scale/26/containers/
- TrueNAS container management: https://www.truenas.com/docs/scale/26/containers/managingcontainers/
- GitHub self-hosted runners: https://docs.github.com/en/actions/concepts/runners/self-hosted-runners
- Adding a self-hosted runner: https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners
- GitHub runner releases: https://github.com/actions/runner/releases
