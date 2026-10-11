"""data/ham/ altındaki ham ilan yanıtlarından staj veri setini (data/ilanlar_tr.json) oluşturur.

- Yalnızca aşağıda listelenen ilanlar alınır (teknik roller + ön kontrol örnekleri).
- Lever ve Greenhouse kendi biçimlerinde bırakılır; HTML yalnızca düz metne çevrilir.
  Ortak şablona dönüştürme jobs.py'nin işidir.
- Tarih alanları ve başvuru adresleri alınmaz; e-posta ve telefon numaraları metinden silinir.
Kullanım:  python scripts/veri_seti_olustur.py
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HAM = ROOT / "data" / "ham"
OUT = ROOT / "data" / "ilanlar_tr.json"

KAYNAKLAR = {  # dosya: (şirket, sistem, ilan adresi)
    "trendyol": ("Trendyol", "lever", "https://api.lever.co/v0/postings/trendyol?mode=json"),
    "insiderone": ("Insider One", "lever", "https://api.lever.co/v0/postings/insiderone?mode=json"),
    "getmidas": ("Midas", "lever", "https://api.lever.co/v0/postings/getmidas?mode=json"),
    "dreamgames": ("Dream Games", "greenhouse",
                   "https://boards-api.greenhouse.io/v1/boards/dreamgames/jobs?content=true"),
}

SECIM = [  # (dosya, kaynak ilan kimliğinin başı)
    ("getmidas", "79cce898"),    # Software Engineer
    ("getmidas", "536b118f"),    # Senior Software Engineer
    ("getmidas", "06b3a906"),    # Quantitative Developer
    ("getmidas", "ebd7df4f"),    # Analytics Manager
    ("insiderone", "ee932b8c"),  # Software Engineer - (AI Native)
    ("insiderone", "48999122"),  # Information Security Engineer
    ("insiderone", "0ac29396"),  # AI Product Manager
    ("insiderone", "8c54696c"),  # Technical Support Specialist (German Speaker)
    ("trendyol", "33c48e9f"),    # Data Scientist (Pre-Search)
    ("trendyol", "13ea3eea"),    # Fraud Process & Analytics Professionals
    ("trendyol", "e11c5931"),    # Operations Strategy and Business Intelligence (Kocaeli)
    ("trendyol", "a82ac003"),    # Business Development / Category Management Graduates (Riyad)
    ("trendyol", "bf52bd92"),    # Marketplace Development Lead (Bükreş)
    ("dreamgames", "4958794101"),  # AI Engineer, Performance Marketing
]

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<!\d)(?:\+?90[\s-]?)?\(?0?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")


def duz_metin(s: str | None) -> str | None:
    """HTML'i düz metne çevirir, kişisel iletişim bilgilerini siler."""
    if s is None:
        return None
    s = html.unescape(s)
    s = re.sub(r"<\s*(br|/p|/li|/div|/h\d)\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<li[^>]*>", "\n- ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("\xa0", " ")
    s = EMAIL.sub("[e-posta]", s)
    s = PHONE.sub("[telefon]", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def lever_kaydi(j: dict) -> dict:
    c = j["categories"]
    return {
        "id": j["id"], "text": j["text"],
        "categories": {k: c.get(k) for k in ("location", "commitment", "team", "department", "allLocations")},
        "country": j.get("country"), "workplaceType": j.get("workplaceType"),
        "salaryRange": j.get("salaryRange"),
        "descriptionPlain": duz_metin(j.get("descriptionPlain")),
        "lists": [{"text": duz_metin(x["text"]), "content": duz_metin(x["content"])} for x in j.get("lists", [])],
        "hostedUrl": j["hostedUrl"],
    }


def greenhouse_kaydi(j: dict) -> dict:
    return {
        "id": j["id"], "title": j["title"], "location": {"name": j["location"]["name"]},
        "departments": [d["name"] for d in j.get("departments", [])],
        "offices": [o["name"] for o in j.get("offices", [])],
        "content": duz_metin(j.get("content")), "absolute_url": j["absolute_url"],
    }


def main() -> None:
    ham = {}
    for dosya in KAYNAKLAR:
        d = json.loads((HAM / f"{dosya}.json").read_text(encoding="utf-8"))
        ham[dosya] = d["jobs"] if isinstance(d, dict) else d
    posts = []
    for no, (dosya, onek) in enumerate(SECIM, start=1):
        sirket, sistem, _ = KAYNAKLAR[dosya]
        eslesen = [j for j in ham[dosya] if str(j["id"]).startswith(onek)]
        if len(eslesen) != 1:
            raise SystemExit(f"{dosya}/{onek}: {len(eslesen)} ilan bulundu (ilan kapanmış olabilir)")
        j = eslesen[0]
        kayit = lever_kaydi(j) if sistem == "lever" else greenhouse_kaydi(j)
        posts.append({"id": no, "company": sirket, "source": sistem, "raw": kayit})
    veri = {
        "description": "Türk teknoloji şirketlerinin kariyer sayfalarındaki ilanlar; işe alım sistemlerinin "
                       "herkese açık ilan uçlarından (Lever, Greenhouse) alındı.",
        "sources": [{"company": s, "system": t, "url": u} for s, t, u in KAYNAKLAR.values()],
        "posts": posts,
    }
    OUT.write_text(json.dumps(veri, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(posts)} ilan -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
