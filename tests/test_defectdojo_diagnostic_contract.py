"""DefectDojo private ingress diagnostic contract (offline, fake CLIs)."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-defectdojo.sh"
PREFLIGHT = ROOT / "scripts/truenas/preflight-defectdojo.sh"

FAKES = {
    "ip": "printf '2: br0    inet 172.17.0.24/24 brd 172.17.0.255 scope global br0\\n'\n",
    "docker": """case "$1" in
  inspect)
    case "$*" in
      *State.Status*) printf 'running\\n' ;;
      *NetworkSettings.Networks*) printf '{"traefik_network":{}}\\n' ;;
    esac ;;
  port) printf '172.17.0.24:31085\\n' ;;
esac
""",
    "curl": """case "$*" in
  *api/v2*) printf '403' ;;
  *31085/*) if [[ "${FAKE_UI_BAD_CODE:-0}" == 1 ]]; then
               printf 'BAD|text/html'
             elif [[ "${FAKE_UI_DOWN:-0}" == 1 ]]; then
               printf '000'; exit 7
             elif [[ "${FAKE_UI_JSON:-0}" == 1 ]]; then
               printf '200|application/json'
             elif [[ "${FAKE_UI_HTML:-0}" == 1 ]]; then
               printf '200|text/html; charset=utf-8'
             else
               printf '302'
             fi ;;
  *) if [[ "${FAKE_HTTPS_DENIED:-0}" == 1 ]]; then
       printf '403'
     elif [[ "${FAKE_HTTPS_JSON:-0}" == 1 ]]; then
       printf '200|application/json'
     else
       printf '302'
     fi ;;
esac
""",
    "dig": """resolver=""
for arg in "$@"; do [[ "${arg}" == @* ]] && resolver="${arg#@}"; done
if [[ "${FAKE_DNS_FAIL:-}" == "${resolver}" ]]; then exit 9; fi
status="${FAKE_DNS_RCODE:-NOERROR}"
if [[ "${resolver}" == 1.1.1.1 && "${FAKE_PUBLIC_DNS:-0}" != 1 && -z "${FAKE_DNS_RCODE:-}" ]]; then
  status=NXDOMAIN
fi
printf ';; ->>HEADER<<- opcode: QUERY, status: %s, id: 41\\n' "$status"
if [[ "${FAKE_DNS_STALE:-}" == "${resolver}" ]]; then
  printf ';; EDE: 3 (Stale Answer)\\n'
fi
if [[ "${resolver}" != 1.1.1.1 || "${FAKE_PUBLIC_DNS:-0}" == 1 ]]; then
  printf 'defectdojo.int.albandrieu.com. 300 IN A 172.17.0.24\\n'
fi
""",
}


def _run(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # TrueNAS /tmp can be noexec: executable fake CLIs must live on the repo FS.
    with tempfile.TemporaryDirectory(prefix=".defectdojo-mock-", dir=ROOT) as temp_dir:
        for name, body in FAKES.items():
            fake = Path(temp_dir) / name
            fake.write_text("#!/usr/bin/env bash\n" + body)
            fake.chmod(0o755)
        jq = shutil.which("jq")
        assert jq, "jq is required for this contract"
        env = os.environ | {
            "PATH": f"{temp_dir}:{os.environ['PATH']}",
            "DIAG_COLOR": "never",
            "DIAG_ICONS": "never",
        } | extra_env
        return subprocess.run(
            ["bash", str(SCRIPT), "--check"], cwd=ROOT, env=env, capture_output=True, text=True, check=False,
        )


def test_private_ingress_acceptance_passes() -> None:
    result = _run({})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "== 1/4 · TrueNAS identity and Docker network (metadata only) ==" in result.stdout
    assert "OK: unauthenticated API access rejected" in result.stdout
    assert "ui_origin_http=302" in result.stdout
    assert "OK: DefectDojo HTML origin responds" in result.stdout
    assert "OK: no public A record" in result.stdout
    assert "OK: HTTPS router redirects with HTTP 302" in result.stdout
    assert "checks: warnings=0 failures=0 unknown=0" in result.stdout


def test_public_dns_record_fails_acceptance() -> None:
    result = _run({"FAKE_PUBLIC_DNS": "1"})
    assert result.returncode == 1
    assert "FAIL: public A record present" in result.stdout


def test_dns_timeout_never_looks_like_private_dns_or_public_privacy() -> None:
    for address in ("172.17.0.24", "172.17.0.1", "1.1.1.1"):
        result = _run({"FAKE_DNS_FAIL": address})
        assert result.returncode == 1, result.stdout + result.stderr
        assert f"dns_server={address} query=failed" in result.stdout
        assert f"FAIL: DNS resolver {address} unavailable" in result.stdout
        if address == "1.1.1.1":
            assert "OK: no public A record" not in result.stdout



def test_servfail_or_refused_dns_status_is_not_a_private_dns_proof() -> None:
    for rcode in ("SERVFAIL", "REFUSED"):
        result = _run({"FAKE_DNS_RCODE": rcode})
        assert result.returncode == 1, result.stdout + result.stderr
        assert "dns_server=1.1.1.1 query=invalid_response" in result.stdout
        assert "OK: no public A record" not in result.stdout


def test_stale_private_dns_is_not_accepted() -> None:
    result = _run({"FAKE_DNS_STALE": "172.17.0.24"})
    assert result.returncode == 1, result.stdout + result.stderr
    assert "dns_server=172.17.0.24 query=stale_answer" in result.stdout
    assert "no current DNS acceptance" in result.stdout


def test_api_403_does_not_mask_broken_html_ui() -> None:
    result = _run({"FAKE_UI_DOWN": "1"})
    assert result.returncode == 1
    assert "api_http=403" in result.stdout
    assert "ui_origin_http=000" in result.stdout
    assert "evidence=api_reachable_but_ui_origin_unavailable" in result.stdout
    assert "FAIL: DefectDojo HTML origin unreachable" in result.stdout


def test_origin_200_requires_html_content_type() -> None:
    html = _run({"FAKE_UI_HTML": "1"})
    assert html.returncode == 0, html.stdout + html.stderr
    assert "ui_origin_http=200 ui_mime=html" in html.stdout
    bad = _run({"FAKE_UI_JSON": "1"})
    assert bad.returncode == 1
    assert "ui_origin_http=200 ui_mime=other" in bad.stdout
    assert "FAIL: DefectDojo origin returned HTTP 200 without HTML Content-Type" in bad.stdout


def test_invalid_http_metadata_is_redacted_and_fails_closed() -> None:
    result = _run({"FAKE_UI_BAD_CODE": "1"})
    assert result.returncode == 1
    assert "ui_origin_http=000 ui_mime=html" in result.stdout
    assert "FAIL: DefectDojo HTML origin unreachable" in result.stdout
    assert "BAD|text/html" not in result.stdout + result.stderr


def test_https_forbidden_and_json_are_not_ui_acceptance() -> None:
    for env_var, expected in (
        ("FAKE_HTTPS_DENIED", "FAIL: HTTPS browser access denied (HTTP 403)"),
        ("FAKE_HTTPS_JSON", "FAIL: HTTPS router returned HTTP 200 without HTML Content-Type"),
    ):
        result = _run({env_var: "1"})
        assert result.returncode == 1
        assert expected in result.stdout


def test_failed_html_origin_has_actionable_private_diagnostic() -> None:
    result = _run({"FAKE_UI_DOWN": "1"})
    assert result.returncode == 1
    assert "NEXT origin: check Nginx/uWSGI containers and LAN :31085" in result.stdout
    assert "READ_ONLY: no app restart, DNS edit, database migration or secret read" in result.stdout


def test_private_dns_mismatch_does_not_trigger_public_route_recommendation() -> None:
    src = SCRIPT.read_text(encoding="utf-8")
    assert "NEXT DNS: verify Pi-hole A record and pfSense Unbound forward/reachability" in src
    assert "never publish a public A record" in src
    assert "NEXT HTTPS: verify Traefik router labels, SNI and TLS" in src
    assert "DD_PROXY_NETWORK_FAILED" in src
    assert "DD_PRIVATE_DNS_FAILED" in src
    assert "DD_HTTPS_FAILED" in src


def test_servfail_dns_contains_actionable_unbound_diagnostic() -> None:
    result = _run({"FAKE_DNS_RCODE": "SERVFAIL"})
    assert result.returncode == 1
    assert "query=invalid_response status=SERVFAIL" in result.stdout
    assert "NEXT DNS: verify Pi-hole A record and pfSense Unbound forward/reachability" in result.stdout
    assert "public A record present" not in result.stdout


def test_usage_and_preflight_syntax() -> None:
    usage = subprocess.run(["bash", str(SCRIPT), "--apply"], capture_output=True, text=True, check=False)
    assert usage.returncode == 2
    assert subprocess.run(["bash", "-n", str(PREFLIGHT)], check=False).returncode == 0
    source = PREFLIGHT.read_text(encoding="utf-8")
    assert "diag_summary" in source
    for forbidden in ("docker restart", "manage.py migrate", "midclt call app."):
        assert forbidden not in source
