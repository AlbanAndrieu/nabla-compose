# Compose examples

Load this reference only when a concrete Compose example is useful.

## Health-aware dependency

```yaml
services:
  app:
    depends_on:
      database:
        condition: service_healthy

  database:
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER"]
      interval: 10s
      timeout: 5s
      retries: 5
```

Use this only when the dependency image exposes a meaningful readiness command.

## Environment injection

```yaml
services:
  app:
    environment:
      API_URL: ${API_URL}
      LOG_LEVEL: ${LOG_LEVEL:-info}
```

Never put secret values directly in the Compose file.

## Least privilege

```yaml
services:
  app:
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
```

Add capabilities back only when the workload demonstrably needs them.

## Static validation

```bash
docker compose -f compose.yml config --quiet --no-interpolate --no-env-resolution
```

Prefer this over starting containers when checking syntax and model validity.
