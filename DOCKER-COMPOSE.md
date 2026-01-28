# Docker Compose Guide

Complete guide for using Docker Compose with this FastAPI application.

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Configuration Files](#configuration-files)
- [Development Workflow](#development-workflow)
- [Production Deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

## Quick Start

### Prerequisites

- Docker Engine 20.10+
- Docker Compose V2 (comes with Docker Desktop)

### Starting the Application

1. **Clone the repository and navigate to the project directory**

```bash
cd nabla-compose
```

2. **Create environment file**

```bash
cp .env.example .env
# Edit .env with your configuration if needed
```

3. **Start all services**

```bash
# Development mode (uses docker-compose.override.yml automatically)
docker compose up -d

# View logs
docker compose logs -f
```

4. **Access the application**

- API: http://localhost:8000
- API Documentation: http://localhost:8000/docs
- Health Check: http://localhost:8000/health
- API Info: http://localhost:8000/api/info

## Architecture

The docker-compose setup includes four main services:

```
┌─────────────┐     ┌─────────────┐
│   Nginx     │────▶│  FastAPI    │
│  (Port 80)  │     │ (Port 8000) │
└─────────────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    │             │
            ┌───────▼──┐   ┌──────▼────┐
            │PostgreSQL│   │   Redis   │
            │(Port 5432│   │(Port 6379)│
            └──────────┘   └───────────┘
```

### Services

1. **web** - FastAPI application
   - Built from local Dockerfile
   - Hot-reload enabled in development
   - Exposes port 8000

2. **postgres** - PostgreSQL database
   - PostgreSQL 15 Alpine
   - Persistent data storage
   - Exposes port 5432

3. **redis** - Redis cache
   - Redis 7 Alpine
   - Session management and caching
   - Exposes port 6379

4. **nginx** - Reverse proxy
   - Nginx Alpine
   - SSL/TLS termination (production)
   - Exposes ports 80 and 443

## Configuration Files

### docker-compose.yml

Base configuration used in all environments. Defines:
- Service definitions
- Networks
- Volumes
- Basic health checks

### docker-compose.override.yml

Development overrides (automatically applied in `docker compose up`):
- Hot-reload enabled
- Source code mounted as volumes
- Debug mode enabled
- Nginx disabled (access FastAPI directly)

### docker-compose.prod.yml

Production configuration:
- Resource limits
- Production-grade restart policies
- Optimized for performance
- No source code mounting

### .env

Environment variables for configuration:

```env
# Application
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=info

# Database
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_DB=appdb
DATABASE_URL=postgresql://user:password@postgres:5432/appdb

# Redis
REDIS_URL=redis://redis:6379/0
```

## Development Workflow

### Starting Services

```bash
# Start all services in foreground
docker compose up

# Start all services in background
docker compose up -d

# Build and start (force rebuild)
docker compose up --build

# Start specific service
docker compose up web
```

### Viewing Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f web

# Last 100 lines
docker compose logs --tail=100 web
```

### Executing Commands

```bash
# Open bash in web container
docker compose exec web bash

# Run Python shell
docker compose exec web python

# Run database migrations
docker compose exec web alembic upgrade head

# Run tests
docker compose exec web pytest
```

### Database Operations

```bash
# Access PostgreSQL CLI
docker compose exec postgres psql -U user -d appdb

# Create database backup
docker compose exec postgres pg_dump -U user appdb > backup.sql

# Restore database backup
docker compose exec -T postgres psql -U user -d appdb < backup.sql
```

### Redis Operations

```bash
# Access Redis CLI
docker compose exec redis redis-cli

# Monitor Redis commands
docker compose exec redis redis-cli MONITOR

# Check Redis stats
docker compose exec redis redis-cli INFO
```

### Stopping Services

```bash
# Stop all services
docker compose down

# Stop and remove volumes (WARNING: deletes data!)
docker compose down -v

# Stop specific service
docker compose stop web

# Restart service
docker compose restart web
```

## Production Deployment

### Using Production Configuration

```bash
# Start with production settings
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# View configuration
docker compose -f docker-compose.yml -f docker-compose.prod.yml config

# Stop production stack
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

### Environment Setup

1. **Create production environment file**

```bash
cat > .env.prod << EOF
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=warning

POSTGRES_USER=prod_user
POSTGRES_PASSWORD=<secure-password>
POSTGRES_DB=prod_db
DATABASE_URL=postgresql://prod_user:<secure-password>@postgres:5432/prod_db

REDIS_URL=redis://redis:6379/0

# Add additional production secrets
SECRET_KEY=<secure-secret-key>
API_KEY=<secure-api-key>
EOF
```

2. **Use production environment**

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Scaling Services

```bash
# Scale web service to 3 instances
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale web=3

# Note: Requires load balancer (nginx) configuration
```

### Health Monitoring

```bash
# Check service health
docker compose ps

# Check container stats
docker stats

# View health check logs
docker compose exec web cat /proc/1/status
```

## Troubleshooting

### Common Issues

#### Services Won't Start

```bash
# Check logs for errors
docker compose logs

# Check individual service
docker compose logs web

# Verify configuration
docker compose config
```

#### Port Already in Use

```bash
# Check what's using the port
sudo lsof -i :8000

# Change port in .env or docker-compose.yml
```

#### Database Connection Issues

```bash
# Verify database is ready
docker compose exec postgres pg_isready -U user -d appdb

# Check environment variables
docker compose exec web env | grep DATABASE

# Test connection from web container
docker compose exec web psql postgresql://user:password@postgres:5432/appdb
```

#### Permission Issues

```bash
# Check file permissions
docker compose exec web ls -la /app

# Fix permissions (if needed)
docker compose exec web chown -R appuser:appuser /app
```

### Debugging

```bash
# View container details
docker inspect <container_name>

# Check network connectivity
docker compose exec web ping postgres
docker compose exec web ping redis

# View Docker networks
docker network ls
docker network inspect nabla-compose_app-network
```

## Advanced Usage

### Custom Networks

```bash
# Create external network
docker network create my-custom-network

# Reference in docker-compose.yml
networks:
  app-network:
    external: true
    name: my-custom-network
```

### Volume Management

```bash
# List volumes
docker volume ls

# Inspect volume
docker volume inspect nabla-compose_postgres-data

# Backup volume
docker run --rm -v nabla-compose_postgres-data:/data -v $(pwd):/backup alpine tar czf /backup/postgres-backup.tar.gz /data

# Restore volume
docker run --rm -v nabla-compose_postgres-data:/data -v $(pwd):/backup alpine tar xzf /backup/postgres-backup.tar.gz -C /
```

### Resource Limits

Add to docker-compose.yml:

```yaml
services:
  web:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
```

### Logging Configuration

```yaml
services:
  web:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Using Secrets

For production, use Docker secrets:

```bash
# Create secret
echo "my-secret-password" | docker secret create db_password -

# Reference in docker-compose.yml
services:
  postgres:
    secrets:
      - db_password
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password

secrets:
  db_password:
    external: true
```

## CI/CD Integration

The project includes GitHub Actions workflow for automated testing:

- Validates docker-compose.yml syntax
- Builds Docker images
- Starts the stack
- Runs health checks
- Tests service connectivity
- Security scanning with Trivy

See `.github/workflows/docker-compose.yml` for details.

## Best Practices

1. **Never commit .env files** - Use .env.example as template
2. **Use named volumes** for data persistence
3. **Define health checks** for all services
4. **Use specific image tags** instead of `latest`
5. **Implement proper logging** with rotation
6. **Set resource limits** in production
7. **Use secrets management** for sensitive data
8. **Regular backups** of volumes and databases
9. **Monitor container health** and logs
10. **Keep images updated** for security patches

## References

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [PostgreSQL Docker Hub](https://hub.docker.com/_/postgres)
- [Redis Docker Hub](https://hub.docker.com/_/redis)
- [Nginx Docker Hub](https://hub.docker.com/_/nginx)

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review GitHub Actions logs
3. Consult copilot instructions in `.github/instructions/docker-compose.instructions.md`
4. Open an issue on GitHub
