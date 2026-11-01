#!/bin/bash
# No xtrace here: it would print DATABASE_URL, which embeds the database password.
cd litellm || exit
# Print the migration command with a variable reference, never the secret value;
# `-e DATABASE_URL` forwards it from the caller's environment.
echo 'docker run --rm --network intranet -e DATABASE_URL docker.litellm.ai/berriai/litellm:main-stable prisma migrate deploy'
docker stop litellm-litellm-1
docker compose --env-file .env -f docker-compose.yml up --no-build -d
echo "docker logs litellm-litellm-1 -f"
exit 0
