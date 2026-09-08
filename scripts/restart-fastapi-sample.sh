#!/bin/bash
# Restart the fastapi-sample service on TrueNAS
# Usage: Run this on your TrueNAS host as root

COMPOSE_FILE="/mnt/cpool/compose/nabla-compose/apps/sample/compose.yml"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: Compose file not found at $COMPOSE_FILE"
  exit 1
fi

echo "Bringing up fastapi-sample from $COMPOSE_FILE..."
docker compose -f "$COMPOSE_FILE" up -d
docker compose -f "$COMPOSE_FILE" ps
echo "Done."
