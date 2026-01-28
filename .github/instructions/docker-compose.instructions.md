# Docker Compose Instructions for Copilot

## Overview

This document provides guidance for working with Docker Compose configurations in this project. Docker Compose is used to orchestrate multi-container applications with FastAPI, PostgreSQL, Redis, and Nginx.

## Architecture

The docker-compose.yml defines a multi-service architecture:

- **web**: FastAPI application container
- **postgres**: PostgreSQL database for persistent data storage
- **redis**: Redis cache for session management and caching
- **nginx**: Nginx reverse proxy for production deployment (optional)

## Best Practices

### 1. Service Configuration

- Always specify explicit version numbers for base images (e.g., `postgres:15-alpine`, `redis:7-alpine`)
- Use Alpine-based images when possible for smaller image sizes
- Define health checks for all critical services to ensure proper startup order
- Use `depends_on` to declare service dependencies

### 2. Environment Variables

- Never hardcode sensitive credentials in docker-compose.yml
- Use `.env` files for environment-specific configuration
- Reference secrets from environment variables: `${DATABASE_PASSWORD}`
- Provide sensible defaults for development environments

### 3. Volumes and Data Persistence

- Use named volumes for database data persistence: `postgres-data`, `redis-data`
- Mount source code as volumes in development for hot-reload: `./api:/app/api`
- Never mount sensitive files or directories unnecessarily
- Use `:ro` (read-only) flag for configuration files that shouldn't be modified

### 4. Networking

- Create custom networks to isolate services: `app-network`
- Use service names for inter-service communication (e.g., `postgres`, `redis`)
- Only expose ports that need to be accessed from the host
- Use internal networks for services that don't need external access

### 5. Security

- Run containers as non-root users when possible
- Limit container capabilities using `cap_drop` and `cap_add`
- Use secrets management for production deployments
- Regularly update base images to patch security vulnerabilities
- Enable health checks to detect and restart unhealthy containers

### 6. Resource Management

```yaml
services:
  web:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
```

### 7. Logging

- Configure log drivers for centralized logging
- Set log rotation to prevent disk space issues
- Use structured logging in applications

```yaml
services:
  web:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## Common Commands

### Development Workflow

```bash
# Start all services (automatically uses docker-compose.override.yml)
docker-compose up

# Start in detached mode
docker-compose up -d

# Build and start services
docker-compose up --build

# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes data)
docker-compose down -v

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f web

# Execute command in running container
docker-compose exec web bash

# Run one-off command
docker-compose run web python manage.py migrate
```

### Production Deployment

```bash
# Use production compose file
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Pull latest images
docker-compose -f docker-compose.yml -f docker-compose.prod.yml pull

# Scale services (stateless services only)
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale web=3
```

### Docker Compose Files

- **docker-compose.yml**: Base configuration for all environments
- **docker-compose.override.yml**: Local development overrides (automatically applied)
- **docker-compose.prod.yml**: Production-specific configuration

To use production configuration:
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Testing and Debugging

```bash
# Validate docker-compose.yml syntax
docker-compose config

# Check service status
docker-compose ps

# Restart specific service
docker-compose restart web

# View resource usage
docker stats

# Inspect networks
docker network ls
docker network inspect nabla-compose_app-network
```

### Production Deployment

```bash
# Use production compose file
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Scale services (stateless services only)
docker-compose up -d --scale web=3

# Pull latest images
docker-compose pull

# Remove unused images
docker system prune -a
```

## Environment Files

Create a `.env` file in the project root:

```env
# Application
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=info

# Database
POSTGRES_USER=myuser
POSTGRES_PASSWORD=supersecretpassword
POSTGRES_DB=myapp
DATABASE_URL=postgresql://myuser:supersecretpassword@postgres:5432/myapp

# Redis
REDIS_URL=redis://redis:6379/0

# API Keys (use secrets manager in production)
API_KEY=your-api-key-here
```

## Health Checks

Health checks ensure services are running correctly:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

- **test**: Command to run to check health
- **interval**: Time between health checks
- **timeout**: Maximum time to wait for health check
- **retries**: Number of consecutive failures before unhealthy
- **start_period**: Grace period before first health check

## Troubleshooting

### Service won't start

```bash
# Check logs
docker-compose logs web

# Inspect service configuration
docker-compose config --services

# Check network connectivity
docker-compose exec web ping postgres
```

### Database connection issues

```bash
# Verify database is ready
docker-compose exec postgres pg_isready -U user -d appdb

# Check environment variables
docker-compose exec web env | grep DATABASE
```

### Volume permission issues

```bash
# Change ownership (if needed)
docker-compose exec web chown -R appuser:appuser /app/data
```

## Migration Strategy

### Development to Production

1. Create separate compose files: `docker-compose.yml` (base), `docker-compose.prod.yml` (production overrides)
2. Use environment-specific `.env` files
3. Implement proper secrets management (Docker Secrets, Vault, etc.)
4. Configure production-grade logging and monitoring
5. Set resource limits and health checks
6. Use orchestration platforms (Kubernetes, Docker Swarm) for production scale

## Testing Docker Compose

Always validate your docker-compose.yml:

```bash
# Syntax validation
docker-compose config

# Dry run
docker-compose up --no-start

# Check services are healthy
docker-compose ps
```

## CI/CD Integration

Integrate Docker Compose validation in GitHub Actions:

```yaml
- name: Validate docker-compose
  run: |
    docker-compose config --quiet
    docker-compose up -d
    docker-compose ps
    docker-compose down
```

## References

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Compose file version 3 reference](https://docs.docker.com/compose/compose-file/compose-file-v3/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [FastAPI in Docker](https://fastapi.tiangolo.com/deployment/docker/)

## When Modifying Docker Compose

1. **Always validate syntax** with `docker-compose config` before committing
2. **Test locally** with `docker-compose up` to ensure services start correctly
3. **Check health checks** are passing with `docker-compose ps`
4. **Review logs** with `docker-compose logs` for any errors or warnings
5. **Document changes** in commit messages and update this file if needed
6. **Use meaningful service names** that reflect their purpose
7. **Keep development and production configs separate** using override files
8. **Version control** exclude sensitive `.env` files (add to `.gitignore`)
