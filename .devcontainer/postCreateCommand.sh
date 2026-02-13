#!/bin/bash
set -ex
WORKSPACE_DIR=$(pwd)
export POETRY_VERSION=${POETRY_VERSION:-"2.2.1"}
pip install "poetry==$POETRY_VERSION"
poetry config cache-dir "$WORKSPACE_DIR/.cache"
poetry config virtualenvs.in-project true
poetry install --with format,test,extra,open_telemetry,api,deployment,influxdb,panda,temporal,utils,webui
echo "Done!"
