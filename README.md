```bash
docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions

sudo systemctl disable prometheus
sudo systemctl disable ntopng

docker compose --env-file .env --env-file .env.secrets -f  docker-compose.yml up -d
```

```bash
git submodule add -f git@github.com:AlbanAndrieu/my-temporal-dockercompose.git temporal
git submodule add -f https://github.com/cybertec-postgresql/pgwatch pgwatch

git pull origin master --allow-unrelated-histories
git pull && git submodule init && git submodule update && git submodule status

```

```bash
cd temporal

docker volume create portainer_data
docker network create temporal-network
docker network create proxy
docker compose --env-file .env --env-file .env.secrets -f compose-postgres.yml -f compose-services.yml up --detach

cd pgwatch
docker compose -f ./docker/docker-compose.yml up

# at root
docker compose -f ./docker-compose.yml up -d
```

portainer : http://localhost:9001/#!/init/admin
grafana : http://localhost:8085/

```bash
cd openvas

docker compose --env-file .env --env-file .env.secrets -f docker-compose-openvas.yml up -d
```
