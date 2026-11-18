"""Contracts for the opt-in Traefik CrowdSec bouncer and Traefik log acquisition."""

from __future__ import annotations

import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
TRAEFIK = ROOT / "apps" / "traefik" / "compose.yml"
MIDDLEWARE = ROOT / "apps" / "traefik" / "dynamic" / "crowdsec.yml"
CROWDSEC = ROOT / "apps" / "crowdsec" / "compose.yml"
ACQUIS = ROOT / "apps" / "crowdsec" / "acquis.d" / "traefik.yaml"
MANIFEST = ROOT / "config" / "secrets" / "manifest.json"
LOG_DIR = "/mnt/cpool/traefik/logs"


def traefik_service() -> dict:
    return yaml.safe_load(TRAEFIK.read_text(encoding="utf-8"))["services"]["traefik"]


def crowdsec_service() -> dict:
    return yaml.safe_load(CROWDSEC.read_text(encoding="utf-8"))["services"]["crowdsec"]


def test_plugin_is_pinned_to_an_exact_release() -> None:
    command = traefik_service()["command"]
    assert (
        "--experimental.plugins.bouncer.modulename="
        "github.com/maxlerebourg/crowdsec-bouncer-traefik-plugin"
    ) in command
    versions = [c for c in command if c.startswith("--experimental.plugins.bouncer.version=")]
    assert len(versions) == 1
    assert re.fullmatch(r"--experimental\.plugins\.bouncer\.version=v\d+\.\d+\.\d+", versions[0])


def test_middleware_fails_open_and_reads_key_from_canonical_env() -> None:
    bouncer = yaml.safe_load(MIDDLEWARE.read_text(encoding="utf-8"))["http"]["middlewares"][
        "crowdsec"
    ]["plugin"]["bouncer"]
    assert bouncer["crowdsecMode"] == "stream"
    # A LAPI outage or a slow LAPI at startup must not take the ingress down.
    assert bouncer["updateMaxFailure"] == -1
    assert bouncer["streamStartupBlock"] is False
    assert bouncer["crowdsecLapiHost"] == "crowdsec:8080"
    # The key comes from the canonical runtime dotenv through the file-provider
    # template, never from a raw key-file mount (no secret-audit exception).
    assert bouncer["crowdsecLapiKey"] == '{{ env "CROWDSEC_BOUNCER_LAPI_KEY" }}'
    assert "crowdsecLapiKeyFile" not in bouncer
    traefik = traefik_service()
    assert not any("/run/secrets/crowdsec" in str(volume) for volume in traefik["volumes"])
    assert traefik["env_file"][0] == {
        "path": "/mnt/cpool/secrets/runtime/traefik/.env.secrets",
        "required": False,
    }
    # The debug template log would print the rendered key.
    assert not any("debugLogGeneratedTemplate" in c for c in traefik["command"])
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    item = next(i for i in manifest["items"] if i["app"] == "traefik")
    assert "CROWDSEC_BOUNCER_LAPI_KEY" in {s["env"] for s in item["secrets"]}


def test_middleware_is_not_attached_by_traefik_itself() -> None:
    labels = " ".join(traefik_service()["labels"])
    assert "crowdsec" not in labels
    assert "traefik.enable=true" not in [label.strip() for label in traefik_service()["labels"]]


def test_access_log_is_json_file_shared_read_only_with_crowdsec() -> None:
    traefik = traefik_service()
    assert "--accesslog.format=json" in traefik["command"]
    assert "--accesslog.filepath=/var/log/traefik/access.log" in traefik["command"]
    # Authorization/Cookie headers stay out of the log.
    assert "--accesslog.fields.headers.defaultmode=drop" in traefik["command"]
    assert f"{LOG_DIR}:/var/log/traefik" in traefik["volumes"]

    crowdsec = crowdsec_service()
    assert f"{LOG_DIR}:/logs/traefik:ro" in crowdsec["volumes"]
    assert "crowdsecurity/traefik" in crowdsec["environment"]["COLLECTIONS"].split()
    acquis = yaml.safe_load(ACQUIS.read_text(encoding="utf-8"))
    assert acquis["source"] == "file"
    assert acquis["filenames"] == ["/logs/traefik/access.log"]
    assert acquis["labels"]["type"] == "traefik"


def test_crowdsec_joins_traefik_network_without_being_routed() -> None:
    crowdsec = crowdsec_service()
    assert crowdsec["networks"] == ["default", "traefik_network"]
    assert not any(str(label).startswith("traefik.") for label in crowdsec["labels"])
    text = CROWDSEC.read_text(encoding="utf-8")
    assert "docker.sock" not in text
