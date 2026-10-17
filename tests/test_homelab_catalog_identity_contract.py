import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "homelab-services.json"


def _services() -> list[dict]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))["services"]


def test_every_homelab_service_declares_an_explicit_id() -> None:
    # Consumers derive a fallback id from tunnelUrl/name; an implicit id let a
    # legacy entry silently collide with a newer x-nabla id (LanguageTool).
    missing = [item.get("name") for item in _services() if not str(item.get("id") or "").strip()]
    assert not missing, f"homelab services without explicit id: {missing}"


def test_homelab_service_ids_are_unique_case_insensitively() -> None:
    seen: dict[str, str] = {}
    duplicates = []
    for item in _services():
        key = str(item.get("id") or "").casefold()
        if key in seen:
            duplicates.append((seen[key], item.get("name")))
        seen[key] = str(item.get("name"))
    assert not duplicates, f"duplicate homelab service ids: {duplicates}"


def test_homelab_service_names_are_unique_case_insensitively() -> None:
    names = [str(item.get("name") or "").casefold() for item in _services()]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"duplicate homelab service names: {duplicates}"


def test_languagetool_has_a_single_entry_with_its_observed_public_route() -> None:
    entries = [item for item in _services() if "languagetool" in str(item.get("id")) + str(item.get("name")).lower().replace(" ", "")]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["id"] == "languagetool"
    assert entry["internalPort"] == 8010
    # Cloudflare Access answers for this hostname (302 to the Access login).
    assert entry["tunnelUrl"] == "https://languagetool.albandrieu.com"
    assert entry["external"] is True
