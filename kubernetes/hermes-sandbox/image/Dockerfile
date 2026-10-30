# hermes-homelab-sandbox: image for the hermes-homelab-offline SandboxTemplate.
# Offline homelab checks only: git, just, pre-commit, docker-compose config.
# No kubectl, no Docker daemon/CLI, no credentials. Tool versions and
# checksums mirror mise.lock; update both together.
FROM python:3.14.10-slim-bookworm
LABEL name="hermes-homelab-sandbox" \
      version="0.1.0"

ARG TARGETARCH
ARG COMPOSE_VERSION=5.5.1
ARG COMPOSE_SHA256_AMD64=db1889184726840f75c4f9c001048430d4f25b3be3cb084d3ddd762bc0aed576
ARG COMPOSE_SHA256_ARM64=732e3a84c1a0f67256ce80bc2598a24546b10ca05f9faa97efceb1171ece2ef7
ARG JUST_VERSION=1.58.0
ARG JUST_SHA256_AMD64=4a5cc2f53e6f0f8c59092a6cc38291eb729d46a7dd95d3ae582008881b84931d
ARG JUST_SHA256_ARM64=748237128c4c40cbdabc65e841d05ceba13cc23a91eaba395495894c1d9764df
ARG PRE_COMMIT_VERSION=4.6.2
ARG PRE_COMMIT_SHA256=43c09a73d82af8efff09900e60d76d67a2c3d990613c3c770b2b5c4418a16c4b

# Debian package versions move with the pinned base image.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/*

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      amd64) compose_arch=x86_64; just_arch=x86_64; compose_sha="${COMPOSE_SHA256_AMD64}"; just_sha="${JUST_SHA256_AMD64}" ;; \
      arm64) compose_arch=aarch64; just_arch=aarch64; compose_sha="${COMPOSE_SHA256_ARM64}"; just_sha="${JUST_SHA256_ARM64}" ;; \
      *) echo "unsupported arch: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSLo /usr/local/bin/docker-compose \
      "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-${compose_arch}"; \
    echo "${compose_sha}  /usr/local/bin/docker-compose" | sha256sum -c -; \
    curl -fsSLo /tmp/just.tar.gz \
      "https://github.com/casey/just/releases/download/${JUST_VERSION}/just-${JUST_VERSION}-${just_arch}-unknown-linux-musl.tar.gz"; \
    echo "${just_sha}  /tmp/just.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/just.tar.gz -C /usr/local/bin just; \
    curl -fsSLo /usr/local/lib/pre-commit.pyz \
      "https://github.com/pre-commit/pre-commit/releases/download/v${PRE_COMMIT_VERSION}/pre-commit-${PRE_COMMIT_VERSION}.pyz"; \
    echo "${PRE_COMMIT_SHA256}  /usr/local/lib/pre-commit.pyz" | sha256sum -c -; \
    printf '#!/bin/sh\nexec python3 /usr/local/lib/pre-commit.pyz "$@"\n' > /usr/local/bin/pre-commit; \
    chmod 0755 /usr/local/bin/docker-compose /usr/local/bin/just /usr/local/bin/pre-commit; \
    rm -f /tmp/just.tar.gz; \
    apt-get purge -y --auto-remove curl; \
    docker-compose version; just --version; pre-commit --version; git --version; \
    if command -v kubectl || command -v docker; then exit 1; fi

RUN groupadd --gid 1000 sandbox \
    && useradd --uid 1000 --gid 1000 --home-dir /workspace --no-create-home --shell /bin/bash sandbox

ENV HOME=/workspace \
    PRE_COMMIT_HOME=/tmp/pre-commit \
    PYTHONDONTWRITEBYTECODE=1
USER 1000:1000
WORKDIR /workspace
CMD ["sleep", "infinity"]
