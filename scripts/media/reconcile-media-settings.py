#!/usr/bin/env python3
"""Reconcile *arr media application settings declared in config/media/settings.yml.

Covers what terraform/media cannot manage with a maintained OpenTofu provider:
qBittorrent preferences and categories, the Prowlarr global proxy, the Lidarr
root folder and download client, and Jellyfin metrics and libraries.

Partial merge: only declared keys are compared and written. --check never
writes and exits 3 on drift; --apply converges. Credentials are read from the
environment only (Vaultwarden) and are never printed:

  QBITTORRENT_WEBUI_USERNAME (default admin), QBITTORRENT_WEBUI_PASSWORD,
  PROWLARR_API_KEY, HTTPPROXY_USER, HTTPPROXY_PASSWORD, LIDARR_API_KEY,
  JELLYFIN_API_KEY. Optional <APP>_URL overrides the declared URL.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / "config" / "media" / "settings.yml"
APPS = ("qbittorrent", "prowlarr", "lidarr", "jellyfin")
EXIT_DRIFT = 3


class Http:
    """Minimal JSON/form client; headers (credentials) are never logged."""

    def __init__(self, base: str, headers: dict[str, str] | None = None) -> None:
        self.base = base.rstrip("/")
        self.headers = headers or {}
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def request(self, method: str, path: str, body=None, form=None):
        headers = dict(self.headers)
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        with self.opener.open(request, timeout=20) as response:
            raw = response.read()
        if raw[:1] in (b"{", b"["):
            return json.loads(raw)
        return raw.decode("utf-8", errors="replace")


class Report:
    def __init__(self) -> None:
        self.drifts: list[str] = []
        self.applied: list[str] = []

    def drift(self, app: str, what: str) -> None:
        self.drifts.append(f"{app}: {what}")


def secret(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"{name} is not set (read it from Vaultwarden, never from a file)")
    return value


def url_for(app: str, cfg: dict) -> str:
    return os.environ.get(f"{app.upper()}_URL", cfg["url"])


def reconcile_qbittorrent(cfg: dict, apply: bool, report: Report, client=None) -> None:
    base = url_for("qbittorrent", cfg)
    client = client or Http(base, {"Referer": base})
    login = client.request("POST", "/api/v2/auth/login", form={
        "username": os.environ.get("QBITTORRENT_WEBUI_USERNAME", "admin"),
        "password": secret("QBITTORRENT_WEBUI_PASSWORD"),
    })
    if str(login).strip() != "Ok.":
        raise SystemExit("qbittorrent: WebUI login refused")
    current = client.request("GET", "/api/v2/app/preferences")
    changes = {key: value for key, value in cfg["preferences"].items() if current.get(key) != value}
    for key in sorted(changes):
        report.drift("qbittorrent", f"preference {key}")
    if changes and apply:
        client.request("POST", "/api/v2/app/setPreferences", form={"json": json.dumps(changes)})
        report.applied.append(f"qbittorrent: {len(changes)} preference(s)")
    categories = client.request("GET", "/api/v2/torrents/categories") or {}
    for name, save_path in cfg["categories"].items():
        existing = categories.get(name)
        if existing is not None and existing.get("savePath") == save_path:
            continue
        endpoint = "/api/v2/torrents/createCategory" if existing is None else "/api/v2/torrents/editCategory"
        report.drift("qbittorrent", f"category {name}")
        if apply:
            client.request("POST", endpoint, form={"category": name, "savePath": save_path})
            report.applied.append(f"qbittorrent: category {name}")


def reconcile_prowlarr(cfg: dict, apply: bool, report: Report, client=None) -> None:
    client = client or Http(url_for("prowlarr", cfg), {"X-Api-Key": secret("PROWLARR_API_KEY")})
    host = client.request("GET", "/api/v1/config/host")
    desired = {**cfg["host"], "proxyUsername": secret("HTTPPROXY_USER")}
    changes = {key: value for key, value in desired.items() if host.get(key) != value}
    for key in sorted(changes):
        report.drift("prowlarr", f"host {key}")
    if changes and apply:
        # The password is write-only in the API: send it with any proxy change.
        body = {**host, **changes, "proxyPassword": secret("HTTPPROXY_PASSWORD")}
        client.request("PUT", f"/api/v1/config/host/{host['id']}", body=body)
        report.applied.append(f"prowlarr: {len(changes)} host field(s)")


def with_fields(resource: dict, values: dict) -> dict:
    """Copy a Servarr resource and set field values by name; unknown names fail."""
    body = json.loads(json.dumps(resource))
    known = {field["name"] for field in body.get("fields", [])}
    unknown = sorted(set(values) - known)
    if unknown:
        raise SystemExit(f"unknown download client field(s): {', '.join(unknown)}")
    for field in body["fields"]:
        if field["name"] in values:
            field["value"] = values[field["name"]]
    return body


def reconcile_lidarr(cfg: dict, apply: bool, report: Report, client=None) -> None:
    client = client or Http(url_for("lidarr", cfg), {"X-Api-Key": secret("LIDARR_API_KEY")})
    root = cfg["root_folder"]
    folders = client.request("GET", "/api/v1/rootfolder")
    if not any(folder.get("path", "").rstrip("/") == root["path"] for folder in folders):
        report.drift("lidarr", f"root folder {root['path']}")
        if apply:
            quality = client.request("GET", "/api/v1/qualityprofile")
            metadata = client.request("GET", "/api/v1/metadataprofile")
            if not quality or not metadata:
                raise SystemExit("lidarr: create a quality and a metadata profile first")
            client.request("POST", "/api/v1/rootfolder", body={
                "name": root["name"], "path": root["path"],
                "defaultQualityProfileId": quality[0]["id"],
                "defaultMetadataProfileId": metadata[0]["id"],
                "defaultMonitorOption": "all", "defaultNewItemMonitorOption": "all",
                "defaultTags": [],
            })
            report.applied.append("lidarr: root folder")

    wanted = cfg["download_client"]
    fields = {**wanted["fields"], "username": os.environ.get("QBITTORRENT_WEBUI_USERNAME", "admin")}
    clients = client.request("GET", "/api/v1/downloadclient")
    existing = next((item for item in clients if item.get("name") == wanted["name"]), None)
    if existing is None:
        report.drift("lidarr", f"download client {wanted['name']} missing")
        if apply:
            schema = next(item for item in client.request("GET", "/api/v1/downloadclient/schema")
                          if item.get("implementation") == wanted["implementation"])
            body = with_fields(schema, {**fields, "password": secret("QBITTORRENT_WEBUI_PASSWORD")})
            body.update(name=wanted["name"], enable=True, priority=1,
                        removeCompletedDownloads=False, removeFailedDownloads=True)
            client.request("POST", "/api/v1/downloadclient", body=body)
            report.applied.append("lidarr: download client")
        return
    current = {field["name"]: field.get("value") for field in existing.get("fields", [])}
    changed = sorted(key for key, value in fields.items() if current.get(key) != value)
    for key in changed:
        report.drift("lidarr", f"download client field {key}")
    if changed and apply:
        body = with_fields(existing, {**fields, "password": secret("QBITTORRENT_WEBUI_PASSWORD")})
        client.request("PUT", f"/api/v1/downloadclient/{existing['id']}", body=body)
        report.applied.append(f"lidarr: {len(changed)} download client field(s)")


def reconcile_jellyfin(cfg: dict, apply: bool, report: Report, client=None) -> None:
    token = secret("JELLYFIN_API_KEY")
    client = client or Http(url_for("jellyfin", cfg), {"Authorization": f'MediaBrowser Token="{token}"'})
    system = client.request("GET", "/System/Configuration")
    changes = {key: value for key, value in cfg["system"].items() if system.get(key) != value}
    for key in sorted(changes):
        report.drift("jellyfin", f"system {key}")
    if changes and apply:
        client.request("POST", "/System/Configuration", body={**system, **changes})
        report.applied.append(f"jellyfin: {len(changes)} system setting(s)")
    folders = client.request("GET", "/Library/VirtualFolders")
    for library in cfg["libraries"]:
        folder = next((item for item in folders if item.get("Name") == library["name"]), None)
        if folder is not None and library["path"] in (folder.get("Locations") or []):
            continue
        report.drift("jellyfin", f"library {library['name']}")
        if not apply:
            continue
        if folder is None:
            query = urllib.parse.urlencode({
                "name": library["name"], "collectionType": library["collectionType"],
                "paths": library["path"], "refreshLibrary": "false",
            })
            client.request("POST", f"/Library/VirtualFolders?{query}", body={"LibraryOptions": {}})
        else:
            client.request("POST", "/Library/VirtualFolders/Paths?refreshLibrary=false",
                           body={"Name": library["name"], "Path": library["path"]})
        report.applied.append(f"jellyfin: library {library['name']}")


RECONCILERS = {
    "qbittorrent": reconcile_qbittorrent,
    "prowlarr": reconcile_prowlarr,
    "lidarr": reconcile_lidarr,
    "jellyfin": reconcile_jellyfin,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="report drift, never write")
    mode.add_argument("--apply", action="store_true", help="converge declared settings")
    parser.add_argument("--app", action="append", choices=APPS, help="limit to one app (repeatable)")
    args = parser.parse_args(argv)

    settings = yaml.safe_load(SETTINGS.read_text(encoding="utf-8"))
    if settings.get("version") != 1:
        print(f"{SETTINGS.relative_to(ROOT)} must be version 1", file=sys.stderr)
        return 2
    report = Report()
    for app in args.app or APPS:
        try:
            RECONCILERS[app](settings[app], args.apply, report)
        except urllib.error.HTTPError as error:
            print(f"{app}: HTTP {error.code} on {urllib.parse.urlsplit(error.url).path}", file=sys.stderr)
            return 1
        except urllib.error.URLError as error:
            print(f"{app}: unreachable ({type(error.reason).__name__})", file=sys.stderr)
            return 1

    for line in report.drifts:
        print(f"DRIFT {line}")
    for line in report.applied:
        print(f"APPLIED {line}")
    if not report.drifts:
        print("✅ media settings converged")
    if args.check and report.drifts:
        return EXIT_DRIFT
    return 0


if __name__ == "__main__":
    sys.exit(main())
