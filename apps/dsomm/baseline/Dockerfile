FROM python:3.13-slim

ARG DSOMM_BASELINE_REF=3255561bc9162e335d2c79b72e12b1478075e610

# Upstream Debian package versions move with the base image; the baseline git commit stays pinned.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git gh \
    && rm -rf /var/lib/apt/lists/*

# Upstream requirements.txt only lists PyYAML/tabulate without versions.
# Pin the compatible runtime explicitly so rebuilding the same git ref stays deterministic.
# hadolint ignore=DL3013
RUN git init /opt/dsomm-baseline \
    && git -C /opt/dsomm-baseline remote add origin https://github.com/tweag/dsomm-baseline.git \
    && git -C /opt/dsomm-baseline fetch --depth 1 origin "${DSOMM_BASELINE_REF}" \
    && git -C /opt/dsomm-baseline checkout --detach FETCH_HEAD \
    && test "$(git -C /opt/dsomm-baseline rev-parse HEAD)" = "${DSOMM_BASELINE_REF}" \
    && pip install --no-cache-dir PyYAML==6.0.3 tabulate==0.10.0

COPY run-baseline.sh /usr/local/bin/run-dsomm-baseline
COPY summarize.py /usr/local/bin/summarize-dsomm-baseline.py
WORKDIR /opt/dsomm-baseline
ENTRYPOINT ["bash", "/usr/local/bin/run-dsomm-baseline"]
