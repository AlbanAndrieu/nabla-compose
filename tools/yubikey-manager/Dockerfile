FROM python:3.13.15-slim-bookworm

ARG YKMAN_VERSION=5.9.2

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential libpcsclite-dev pcscd pkg-config swig \
    && pip install --no-cache-dir "yubikey-manager==${YKMAN_VERSION}" \
    && apt-get purge -y --auto-remove \
       build-essential libpcsclite-dev pkg-config swig \
    && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["ykman"]
