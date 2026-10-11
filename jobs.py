"""Türk şirketlerinin ilanlarını (Lever ve Greenhouse) ortak bir şablona dönüştürür.

İki işe alım sistemi aynı bilgiyi farklı alanlarda ve farklı yazımlarla veriyor
(ör. "Full-Time (Remote)" ile workplaceType="remote"; Greenhouse'ta çalışma biçimi hiç yok).
Kural: ilanda açıkça yazmayan bilgi tahmin edilmez, None olarak bırakılır.
"""
import json
import re
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

DATA = Path(__file__).parent / "data" / "ilanlar_tr.json"

# (görünen ad, düzenli ifade, büyük/küçük harf duyarlı mı)
TECH_VOCAB = [
    ("Python", r"Python", False), ("Java", r"Java(?!Script)", False), ("TypeScript", r"TypeScript", False),
    ("JavaScript", r"JavaScript", False), ("Kotlin", r"Kotlin", False), ("PHP", r"PHP", True), ("Go", r"Golang|Go(?=[,/)]| and | or )", True),
    ("React", r"React", False), ("Node.js", r"Node\.js", False), ("SQL", r"SQL", True),
    ("PostgreSQL", r"PostgreSQL|Postgres", False), ("Redis", r"Redis", False), ("Kafka", r"Kafka", False),
    ("Spark", r"Spark", False), ("BigQuery", r"BigQuery", False), ("Tableau", r"Tableau", False),
    ("Power BI", r"Power BI", False), ("Excel", r"Excel", False), ("SAP", r"SAP", True),
    ("AWS", r"AWS", True), ("GCP", r"GCP|Google Cloud", True), ("Docker", r"Docker", False),
    ("Kubernetes", r"Kubernetes", False), ("Terraform", r"Terraform", False), ("PyTorch", r"PyTorch", False),
    ("TensorFlow", r"TensorFlow", False), ("scikit-learn", r"scikit-learn", False),
    ("Hugging Face", r"Hugging ?Face", False), ("LLM", r"LLMs?", True), ("RAG", r"RAG", True),
    ("NLP", r"NLP", True), ("LangChain", r"LangChain", False), ("Solidity", r"Solidity", False),
]

COUNTRY_CODES = {"TR": "Türkiye", "SA": "Suudi Arabistan", "RO": "Romanya", "GR": "Yunanistan",
                 "FR": "Fransa", "DE": "Almanya"}
CITY_COUNTRY = {"istanbul": "Türkiye", "i̇stanbul": "Türkiye", "kocaeli": "Türkiye", "izmir": "Türkiye",
                "ankara": "Türkiye", "turkey": "Türkiye", "turkiye": "Türkiye", "türkiye": "Türkiye",
                "riyadh": "Suudi Arabistan", "bucharest": "Romanya", "athens": "Yunanistan",
                "paris": "Fransa", "berlin": "Almanya"}
LANGUAGES = {"german": "Almanca", "arabic": "Arapça", "english": "İngilizce", "turkish": "Türkçe",
             "french": "Fransızca", "romanian": "Rumence", "greek": "Yunanca", "russian": "Rusça"}
NATIONALITIES = {"saudi": "Suudi Arabistan", "turkish": "Türkiye", "romanian": "Romanya"}


class JobPosting(BaseModel):
    id: int
    company: str
    role: str
    location: Optional[str] = None
    country: Optional[str] = None
    work_mode: Optional[Literal["remote", "hybrid", "onsite"]] = None
    employment_type: Optional[str] = None
    salary: Optional[str] = None
    tech_stack: list[str] = Field(default_factory=list)
    required_languages: list[str] = Field(default_factory=list)
    nationality_only: Optional[str] = None
    source: Literal["lever", "greenhouse"]
    source_url: str


class FitReport(BaseModel):
    id: int
    company: str
    role: str
    location: Optional[str] = None
    country: Optional[str] = None
    work_mode: Optional[str] = None
    matched_skills: list[str] = Field(default_factory=list)
    eligible: bool
    reasons: list[str] = Field(default_factory=list)
    source_url: str


def load_posts() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))["posts"]


def full_text(post: dict) -> str:
    """İlanın başlık ve açıklama metinlerini tek metinde birleştirir (arama ve çıkarım için)."""
    r = post["raw"]
    parts = [r.get("text") or r.get("title") or "", r.get("descriptionPlain") or "", r.get("content") or ""]
    parts += [f"{x.get('text') or ''}\n{x.get('content') or ''}" for x in r.get("lists", [])]
    return "\n".join(parts)


def _country(location: Optional[str], code: Optional[str]) -> Optional[str]:
    if code in COUNTRY_CODES:
        return COUNTRY_CODES[code]
    for part in re.split(r"[,/]", (location or "").lower()):
        if part.strip() in CITY_COUNTRY:
            return CITY_COUNTRY[part.strip()]
    return None


def _work_mode(workplace: Optional[str], commitment: Optional[str]) -> Optional[str]:
    if workplace in ("remote", "hybrid", "onsite"):
        return workplace
    if commitment and "remote" in commitment.lower():
        return "remote"
    return None  # "unspecified" ya da alan yok: tahmin edilmez


def _employment(commitment: Optional[str]) -> Optional[str]:
    if not commitment:
        return None
    c = commitment.lower()
    if "intern" in c:
        return "Staj"
    if "part" in c:
        return "Yarı zamanlı"
    if "full" in c:
        return "Tam zamanlı"
    if "contract" in c:
        return "Sözleşmeli"
    return None


def _salary(rng: Optional[dict]) -> Optional[str]:
    if not rng or not rng.get("min"):
        return None
    return f"{rng['min']:,}–{rng['max']:,} {rng.get('currency', '')} / {rng.get('interval', '')}".strip(" /")


def _languages(title: str, text: str) -> list[str]:
    found = set()
    for m in re.finditer(r"\((\w+) Speaker\)", title):
        found.add(m.group(1).lower())
    for m in re.finditer(r"(?:fluency|proficiency|fluent|native)[^.\n]{0,40}?\bin\b([^.\n]{0,60})", text, re.I):
        for lang in LANGUAGES:
            if re.search(rf"\b{lang}\b", m.group(1), re.I):
                found.add(lang)
    return sorted(LANGUAGES[x] for x in found)


def _nationality(title: str, text: str) -> Optional[str]:
    m = re.search(r"\b(\w+) Nationals Only\b", f"{title}\n{text}", re.I)
    return NATIONALITIES.get(m.group(1).lower(), m.group(1)) if m else None


def normalize(post: dict) -> JobPosting:
    r, text = post["raw"], full_text(post)
    if post["source"] == "lever":
        cats = r["categories"]
        title, location = r["text"].strip(), cats.get("location")
        country = _country(location, r.get("country"))
        work_mode = _work_mode(r.get("workplaceType"), cats.get("commitment"))
        employment, salary, url = _employment(cats.get("commitment")), _salary(r.get("salaryRange")), r["hostedUrl"]
    else:  # greenhouse: çalışma biçimi ve türü için alan yok
        title, location = r["title"].strip(), r["location"]["name"]
        country, work_mode, employment, salary = _country(location, None), None, None, None
        url = r["absolute_url"]
    stack = [name for name, pat, cs in TECH_VOCAB
             if re.search(rf"(?<![\w.+#])(?:{pat})(?![\w+#])", text, 0 if cs else re.I)]
    return JobPosting(
        id=post["id"], company=post["company"], role=re.sub(r"\s{2,}", " ", title), location=location,
        country=country, work_mode=work_mode, employment_type=employment, salary=salary, tech_stack=stack,
        required_languages=_languages(title, text), nationality_only=_nationality(title, text),
        source=post["source"], source_url=url,
    )


def assess_fit(job: JobPosting, skills: list[str], country: str = "Türkiye",
               languages: tuple[str, ...] = ("Türkçe", "İngilizce"), wants_remote: bool = False) -> FitReport:
    """Kural tabanlı ön kontrol: uygunluk kararı değil, kararın dayanacağı gerçekler.

    - İlan başka bir ülkedeyse ve uzaktan değilse kullanıcı için uygun sayılmaz.
    - "X Nationals Only" gibi vatandaşlık şartı kullanıcının ülkesiyle uyuşmuyorsa uygun sayılmaz.
    - İlanda istenen bir dil kullanıcının dilleri arasında yoksa uygun sayılmaz.
    - Beceri eşleşmesi yalnız ilanda açıkça geçen teknolojiler üzerinden yapılır.
    """
    stack = {t.lower(): t for t in job.tech_stack}
    matched = sorted(stack[s.lower()] for s in skills if s.lower() in stack)
    blocking, notes = [], []
    if job.country is None:
        notes.append("ilanın ülkesi belirtilmemiş")
    elif job.country != country and job.work_mode != "remote":
        blocking.append(f"konum: {job.location} ({job.country}); kullanıcı {country}'de")
    if job.nationality_only and job.nationality_only != country:
        blocking.append(f"vatandaşlık şartı: yalnızca {job.nationality_only} vatandaşları")
    missing = [lang for lang in job.required_languages if lang not in languages]
    if missing:
        blocking.append("dil şartı: " + ", ".join(missing))
    if wants_remote and job.work_mode != "remote":
        blocking.append(f"çalışma biçimi {job.work_mode or 'belirtilmemiş'}, uzaktan değil")
    if job.work_mode is None:
        notes.append("çalışma biçimi ilanda belirtilmemiş")
    if not job.tech_stack:
        notes.append("ilanda teknoloji bilgisi yok")
    return FitReport(id=job.id, company=job.company, role=job.role, location=job.location, country=job.country,
                     work_mode=job.work_mode, matched_skills=matched, eligible=not blocking,
                     reasons=blocking + notes, source_url=job.source_url)
