# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Purpose

This repository acts as an orchestrator for deploying, updating, and managing a suite of self-hosted services via Docker Compose. It is used both:
- On **TrueNAS** (via `apps/` folders and `docker-compose-truenas.yml`), making use of TrueNAS-specific paths/networks.
- On a **workstation/server** (via `docker-compose-albandrieu.yml`), with additional or desktop-centric services.

---

## Key Usage Patterns

### 1. Compose File Entry Points

- **TrueNAS**:  
  Use `docker-compose-truenas.yml` for production-like installs leveraging TrueNAS volumes, secrets, and external network setup.
- **Workstation**:  
  Use `docker-compose-albandrieu.yml` for local installs, pulling in service fragments from the included paths for optional services.

### 2. Launching Services

#### TrueNAS Example:
```bash
docker compose --env-file .env --env-file .env.secrets -f docker-compose-truenas.yml up -d
```

#### Workstation Example:
```bash
docker compose --env-file .env --env-file .env.secrets -f docker-compose-albandrieu.yml up -d
```

- Services use the `intranet` network, which must exist:
  ```bash
  docker network create intranet
  # TrueNAS: external:true manages to reuse host networks as needed.
  ```

### 3. Included Compose Service Fragments

- Compose files assemble services from directories (`compose.redis.yml`, `compose.monitoring.yml`, etc.), shared across both TrueNAS and workstation setups.
- Services like PostgreSQL, Redis, Prometheus, Grafana, Portainer, Plumber, and more are orchestrated across these fragments.
- Included services do **not** duplicate core infra (e.g. no repeated Postgres definitions).

---

## How to Add/Update Services

- Drop new compose fragments in the root or respective `apps/` folder.
- Reference new services in your target entry file (`docker-compose-truenas.yml` or `docker-compose-albandrieu.yml`) via the `include:` YAML list.
- For TrueNAS, reference host-specific paths for volumes/secrets.

---

## Common Commands

### Submodule Management
To update all required git submodules (hosting service sources):
```bash
git pull && git submodule init && git submodule update && git submodule status
```
To add new submodules:
```bash
git submodule add -f <repo-url> <path>
```

### Compose Up/Down/Logs
```bash
docker compose -f <compose-file> up -d       # Start services
docker compose -f <compose-file> down        # Stop services
docker compose -f <compose-file> logs -f     # Follow logs
```

### Health Checks & Ports
- Check mapped ports for services (Portainer, Grafana, Plumber, etc).
- Use TrueNAS UI or local dashboard for Portainer: `http://localhost:9001/#!/init/admin`
- Grafana: `http://localhost:8085/`

---

## Networks & Volumes

- All services are conventionally attached to an external network `intranet` for cross-service communication.
- Data, secrets, and configs are mounted from TrueNAS-specific paths or workstation directories.
- **Secrets management:** via direct file mounts or external providers (e.g., 1Password, webhook as shown in `docker-compose-truenas.yml`).

---

## Code/Service Architecture Overview

- **Central orchestration:** Top-level Compose files (`docker-compose-truenas.yml`, `docker-compose-albandrieu.yml`) reference modular fragments for each service.
- **Service structure:** Each major service (Plumber, Prometheus, Redis, etc.) comes as a dedicated Compose fragment or app folder for portability.
- **TrueNAS integration:** Services and volumes are aligned to host paths and permissions; secrets resolved from `/mnt/cpool/home/albandrieu/.doco-cd/`, etc.

---

## Best Practices

- Avoid duplicate service definitions across Compose includes.
- Reference existing networks and volumes in TrueNAS.
- Keep environment-specific settings (paths, secrets) in `.env` or `.env.secrets`.
- Healthchecks configured where possible (see doco-cd example).
- Keep compose fragments modular for easy expansion/maintenance.

---

## Example: Adding a New App

1. Add a new Compose fragment for your app (e.g., `compose.appname.yml`).
2. Reference it in the entry Compose file under `include`.
3. Ensure it uses the external `intranet` network and shared volumes/secrets.
4. Run Compose up as per usage pattern above.

---

## Related Tools

- **Portainer:** For UI-based container management.
- **doco-cd:** For GitOps style polling/config updates.
- **Grafana/Prometheus:** Monitoring/metrics.

---

This guidance should enable Claude Code and future maintainers to quickly understand, operate, and extend the Docker Compose orchestration for both TrueNAS and workstation environments. Update this file if new deployment patterns arise.
