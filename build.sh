#!/bin/bash
set -xv
docker version --format '{{.Server.Version}}'
docker buildx version
docker buildx inspect nablabuilder
echo "docker buildx use nablabuilder"
docker buildx ls
echo "docker system prune -a"
docker network create temporal-network
docker network create proxy
docker network ls
netstat|  grep 3000
echo "docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up --force-recreate -d"
docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up -d
exit 0
