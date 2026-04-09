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

echo "docker system prune -a"
docker network create temporal-network
docker network create proxy
docker network create intranet
docker network ls

echo "build postgres-standby"
echo "./build-postgres.sh"

docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up postgres -d
docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up --no-build redis-server -d

echo "docker logs -f postgres"

echo "./build-sentry.sh"

docker compose build web
docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml build sentry-cleanup

docker volume create sentry-kafka || true
docker volume create sentry-clickhouse || true
docker volume create sentry-clickhouse-log || true
docker volume create sentry-seaweedfs || true
docker volume create sentry-data || true

docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml build clickhouse

# docker compose run --pull=never --rm web upgrade --noinput --create-kafka-topics

docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up --pull=never clickhouse -d
# docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up -d --force-recreate clickhouse
docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up --pull=never vroom-cleanup -d

netstat |  grep 3000

docker compose pull --ignore-pull-failures
# DOCKER_BUILDKIT=1 docker compose pull 2>&1|  tee pull.log

docker pull registry.community.greenbone.net/community/gsa:stable
docker pull registry.community.greenbone.net/community/openvas-scanner:stable

echo "docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up --force-recreate -d"

docker compose --env-file .env --env-file .env.secrets -f docker-compose.yml up --pull=never --no-build -d --force-recreate --remove-orphans

echo "docker images --filter dangling=true"

# docker run --rm --network intranet \
#   -e DATABASE_URL="$DATABASE_URL" \
#   docker.litellm.ai/berriai/litellm:main-stable \
#   prisma migrate deploy

exit 0
