FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

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
 && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/khal /usr/local/bin/khal \
 && ln -sf /usr/bin/vdirsyncer /usr/local/bin/vdirsyncer
 
RUN python3 -m pip install --break-system-packages --no-cache-dir \
    "feedparser>=6.0.0" \
    "jsonschema>=4.0.0"
    
RUN useradd --create-home --shell /bin/bash sandbox

USER sandbox
WORKDIR /home/sandbox

CMD ["sleep", "infinity"]
