FROM python:3.13-slim

ARG DSOMM_BASELINE_REF=3255561bc9162e335d2c79b72e12b1478075e610

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git gh \
    && rm -rf /var/lib/apt/lists/*

RUN git init /opt/dsomm-baseline \
    && git -C /opt/dsomm-baseline remote add origin https://github.com/tweag/dsomm-baseline.git \
    && git -C /opt/dsomm-baseline fetch --depth 1 origin "${DSOMM_BASELINE_REF}" \
    && git -C /opt/dsomm-baseline checkout --detach FETCH_HEAD \
    && pip install --no-cache-dir -r /opt/dsomm-baseline/requirements.txt

COPY run-baseline.sh /usr/local/bin/run-dsomm-baseline
RUN chmod 0755 /usr/local/bin/run-dsomm-baseline

WORKDIR /opt/dsomm-baseline
ENTRYPOINT ["/usr/local/bin/run-dsomm-baseline"]
