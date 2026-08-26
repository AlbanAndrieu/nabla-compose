# CrowdSec

This container runs as a CrowdSec **agent** and delegates the Local API (LAPI)
to the CrowdSec instance on pfSense.

Required runtime variables:

```text
PFSENSE_CROWDSEC_LAPI_URL=http://pfsense-address:8080
PFSENSE_CROWDSEC_AGENT_USERNAME=...
PFSENSE_CROWDSEC_AGENT_PASSWORD=...
```

The agent consumes pfSense syslog files and Suricata `eve.json` when those
datasets are available on the TrueNAS host.
