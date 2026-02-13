```bash
git submodule add -f git@github.com:AlbanAndrieu/my-temporal-dockercompose.git temporal
git submodule add -f https://github.com/cybertec-postgresql/pgwatch pgwatch
git submodule add -f https://github.com/xitanggg/open-resume.git open-resume
git submodule add -f https://github.com/AlbanAndrieu/reactive-resume.git reactive-resume
git submodule add -f git@github.com:stanfrbd/cyberbro.git
git submodule add -f https://github.com/getsentry/self-hosted.git sentry
git submodule add -f https://github.com/AlbanAndrieu/platform.git plumber-platform
git submodule add -f git@github.com:AlbanAndrieu/litellm.git

git pull origin master --allow-unrelated-histories
git pull && git submodule init && git submodule update && git submodule status

```

```bash
docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions

sudo systemctl disable prometheus
sudo systemctl disable ntopng

docker compose --env-file .env --env-file .env.secrets -f  docker-compose.yml up -d
```

```bash
cd temporal

docker volume create portainer_data
docker network create temporal-network
docker network create proxy
docker compose --env-file .env --env-file .env.secrets -f compose-postgres.yml -f compose-services.yml up --detach
```

```bash
cd pgwatch/docker
docker compose -f compose.postgres.yml up --build  --force-recreate

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

```bash
cd open-resume

docker build -t open-resume .
docker run -p 3006:3000 open-resume

cd reactive-resume

# Start all services
docker compose up -d

# Access the app
open http://localhost:3007
```

```bash
cd cyberbro
cp secrets-sample.json secrets.json

docker compose up
```

# See https://develop.sentry.dev/self-hosted/

```bash
VERSION=$(curl -Ls -o /dev/null -w %{url_effective} https://github.com/getsentry/self-hosted/releases/latest)
VERSION=${VERSION##*/}
cd sentry

git checkout ${VERSION}

docker buildx rm local-builder || true
docker network rm build || true
docker network create --subnet $V4_PREFIX.0/24 --gateway $V4_PREFIX.1 --ip-range $V4_PREFIX.128/25 build
docker buildx create --name local-builder --driver docker-container --driver-opt network=build --use

./install.sh
# After installation, run the following to start Sentry:
docker compose up --wait
```

# See https://getplumber.io/docs/installation/docker-compose-local

```bash
cd plumber-platform
docker compose -f compose.local.yml up -d
```
