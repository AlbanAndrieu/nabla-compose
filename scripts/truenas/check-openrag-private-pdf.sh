#!/usr/bin/env bash
# Read-only PDF mount + Docling acceptance. Never uploads or indexes private files.
set -euo pipefail
[[ "$#" == 3 && "$1" == "--check" && "$2" == "--file" ]] || { echo "Usage: --check --file <basename.pdf>" >&2; exit 2; }
basename="$3"
[[ "$basename" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,180}\.pdf$ && "$basename" != *..* ]] || { echo "BLOCKED: invalid PDF basename" >&2; exit 2; }
root="/mnt/cpool/bababou"
file="$root/$basename"
[[ -d "$root" && ! -L "$root" && -f "$file" && ! -L "$file" ]] || { echo "UNVERIFIED: PDF missing/symlink" >&2; exit 2; }
size="$(stat -c %s -- "$file")"
[[ "$size" =~ ^[0-9]+$ && "$size" -gt 100 && "$size" -le 50000000 ]] || { echo "UNVERIFIED: PDF size invalid" >&2; exit 2; }
[[ "$(head -c 5 -- "$file")" == "%PDF-" ]] || { echo "UNVERIFIED: PDF magic invalid" >&2; exit 2; }
printf "PASS: host_pdf=valid bytes=%s\n" "$size"
state="$(docker inspect --type container --format "{{.State.Status}}" openrag-backend 2>/dev/null || true)"
[[ "$state" == running ]] || { echo "UNVERIFIED: openrag_backend_not_running" >&2; exit 2; }
if ! docker exec openrag-backend sh -c 'test -r "$1" && test -f "$1"' _ "/mnt/bababou/$basename" >/dev/null 2>&1; then
  echo "FAIL: private_pdf_mount_unreadable" >&2; exit 1;
fi
mount_record="$(docker inspect --type container --format '{{range .Mounts}}{{if eq .Destination "/mnt/bababou"}}{{printf "%s|%t" .Source .RW}}{{end}}{{end}}' openrag-backend 2>/dev/null || true)"
if [[ "$mount_record" != "$root|false" ]]; then
  echo "UNVERIFIED: private_pdf_bind_read_only_not_attested" >&2
  exit 2
fi
echo "PASS: openrag_pdf_mount=readable_and_read_only"
if curl -fsS --max-time 8 http://172.17.0.24:5001/ready >/dev/null 2>&1; then
  echo "PASS: docling_host_ready"
else
  echo "UNVERIFIED: docling_host_not_ready"
  echo "NEXT: python3 scripts/truenas/diagnose-docling-readiness.py --check"
  echo "NOT_TESTED: pdf_ingestion_and_retrieval"
  exit 2
fi
if docker exec openrag-backend curl -fsS --max-time 8 http://docling:5001/ready >/dev/null 2>&1; then
  echo "PASS: docling_openrag_network_ready"
else
  echo "UNVERIFIED: docling_openrag_network_not_ready"
  echo "NEXT: python3 scripts/truenas/diagnose-docling-readiness.py --check"
  echo "NOT_TESTED: pdf_ingestion_and_retrieval"
  exit 2
fi
if docker exec openrag-backend curl -fsS --max-time 8 http://127.0.0.1:8000/search/health >/dev/null 2>&1; then
  echo "PASS: openrag_search_health=reachable"
else
  echo "UNVERIFIED: openrag_search_health"; exit 2;
fi
echo "NOT_TESTED: pdf_conversion_indexing_retrieval"
