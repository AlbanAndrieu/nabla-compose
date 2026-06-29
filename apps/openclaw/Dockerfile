FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ARG WACLI_VERSION=0.10.0
ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    git \
    jq \
    python3 \
    python3-pip \
    ripgrep \
    vdirsyncer \
    khal \
    python3-aiohttp-oauthlib \
    tar \
 && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/khal /usr/local/bin/khal \
 && ln -sf /usr/bin/vdirsyncer /usr/local/bin/vdirsyncer

RUN python3 -m pip install --break-system-packages --no-cache-dir \
    "feedparser>=6.0.0" \
    "jsonschema>=4.0.0"

RUN set -eux; \
    arch="${TARGETARCH:-amd64}"; \
    case "$arch" in \
      amd64) warch="amd64" ;; \
      arm64) warch="arm64" ;; \
      *) echo "Unsupported arch: $arch"; exit 1 ;; \
    esac; \
    curl -fsSL \
      "https://github.com/openclaw/wacli/releases/download/v${WACLI_VERSION}/wacli_${WACLI_VERSION}_linux_${warch}.tar.gz" \
      -o /tmp/wacli.tar.gz; \
    tar -xzf /tmp/wacli.tar.gz -C /usr/local/bin; \
    chmod +x /usr/local/bin/wacli; \
    rm -f /tmp/wacli.tar.gz; \
    wacli version

RUN useradd --create-home --shell /bin/bash sandbox

USER sandbox
WORKDIR /home/sandbox

CMD ["sleep", "infinity"]
