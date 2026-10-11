#!/usr/bin/env bash
# Türk teknoloji şirketlerinin kariyer sayfalarındaki ilanları, işe alım sistemlerinin
# herkese açık ilan uçlarından (Lever, Greenhouse) indirir. Giriş ya da sayfa kazıma yok;
# her şirket için tek istek atılır. Ham yanıtlar data/ham/ altına yazılır (repoya girmez).
# Kullanım:  bash scripts/ilanlari_cek.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/ham
UA="AVD-staj-is-firsati-ajani/1.0"

cek() {  # cek <dosya> <adres>
  if curl -fsS -m 30 -A "$UA" "$2" -o "data/ham/$1.json"; then
    printf '  ✔ %-14s %s\n' "$1" "$2"
  else
    printf '  ✘ %-14s %s\n' "$1" "$2"; return 1
  fi
}

echo "İlanlar indiriliyor:"
cek trendyol    "https://api.lever.co/v0/postings/trendyol?mode=json"
cek insiderone  "https://api.lever.co/v0/postings/insiderone?mode=json"
cek getmidas    "https://api.lever.co/v0/postings/getmidas?mode=json"
cek dreamgames  "https://boards-api.greenhouse.io/v1/boards/dreamgames/jobs?content=true"

PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
"$PY" - <<'PY'
import json, pathlib
for f in sorted(pathlib.Path("data/ham").glob("*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    jobs = d["jobs"] if isinstance(d, dict) else d
    print(f"  {f.stem:<12} {len(jobs):>3} ilan")
PY
