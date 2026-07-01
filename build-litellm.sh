#!/bin/bash
set -xv
cd litellm
echo "docker run --rm --network intranet -e DATABASE_URL=\"$DATABASE_URL\" docker.litellm.ai/berriai/litellm:main-stable prisma migrate deploy"
docker stop litellm-litellm-1
docker compose --env-file .env -f docker-compose.yml up --no-build -d
echo "docker logs litellm-litellm-1 -f"
exit 0
