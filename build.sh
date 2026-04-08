#!/bin/bash
set -xv

echo "killall gpg-agent"
echo "gpg-agent --daemon"

echo "docker stop $(docker ps -q)"
echo "docker rm -f $(docker ps -aq)"

export DOCKER_CLIENT_TIMEOUT=240
export COMPOSE_HTTP_TIMEOUT=2000

docker version --format '{{.Server.Version}}'
docker buildx version
docker buildx inspect nablabuilder

echo "docker buildx use nablabuilder"

docker buildx ls

echo "build postgres-standby"
echo "./build-postgres.sh"

docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up --no-build postgres -d
docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up --no-build redis-server -d

echo "docker logs -f postgres"

echo "./build-sentry.sh"

docker compose build web
docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml build sentry-cleanup

docker volume create sentry-kafka || true

echo "docker system prune -a"
docker network create temporal-network
docker network create proxy
docker network create intranet
docker network ls

docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up --pull=never clickhouse -d
docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up --pull=never vroom-cleanup -d

netstat |  grep 3000

docker compose pull --ignore-pull-failures
# DOCKER_BUILDKIT=1 docker compose pull 2>&1|  tee pull.log

docker pull registry.community.greenbone.net/community/gsa:stable

COMPOSE_BAKE=true

echo "docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up --force-recreate -d"

docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up --pull=never --no-build -d

echo "docker images --filter dangling=true"

exit 0
