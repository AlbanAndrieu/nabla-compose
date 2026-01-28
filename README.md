# nabla-compose

Docker compose project for workstation.

## Overview

This is a docker compose application.

## Local Development

### Prerequisites

- Python 3.12 or higher

## Docker Compose Deployment

This project includes a complete Docker Compose setup for running the FastAPI application with all its dependencies.

📖 **[Full Docker Compose Guide](DOCKER-COMPOSE.md)** - Comprehensive documentation with examples

### Quick Start with Docker Compose

1. Create environment file:

```bash
cp .env.example .env
# Edit .env with your configuration
```

2. Start all services:

```bash
# Start in foreground
docker compose up

# Start in background
docker compose up -d
```

3. Access the application:

- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

### Docker Compose Services

The docker-compose.yml includes:

- **web**: FastAPI application (port 8000)
- **postgres**: PostgreSQL database (port 5432)
- **redis**: Redis cache (port 6379)
- **nginx**: Nginx reverse proxy (ports 80/443)

### Docker Compose Commands

```bash
# View running services
docker compose ps

# View logs
docker compose logs -f

# View logs for specific service
docker compose logs -f web

# Restart a service
docker compose restart web

# Stop all services
docker compose down

# Stop and remove volumes (deletes data)
docker compose down -v

# Rebuild and restart
docker compose up --build

# Execute command in container
docker compose exec web bash
```

### Validation

Validate the docker-compose configuration:

```bash
# Check syntax
docker compose config

# Verify services are running
docker compose ps

# Check health status
docker compose ps --format json | jq '.Health'
```

### Initialize opencommit and oco

1. Install opencommit:

```bash
npm install -D opencommit
npm install -D @commitlint/cli @commitlint/config-conventional @commitlint/prompt-cli commitizen cz-emoji-conventional

git add .opencommit-commitlint
oco commitlint get

oco config set OCO_PROMPT_MODULE=@commitlint
```
