"""Hacker News 'Who is hiring?' ilanlarını ortak bir şablona dönüştürür.

Kural: ilanda açıkça yazmayan bilgi tahmin edilmez, None olarak bırakılır.
"""
import json
import re
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

DATA = Path(__file__).parent / "data" / "hn_whoishiring_2026_08.json"

TECH_VOCAB = ["Python", "TypeScript", "JavaScript", "React", "Next.js", "Node.js", "PostgreSQL",
              "Postgres", "Redis", "GraphQL", "AWS", "Kubernetes", "Docker", "Terraform", "Scala",
              "Rust", "Tailwind", "PyTorch", "Jax", "TensorFlow", "Spark", "Snowflake", "Iceberg"]


class JobPosting(BaseModel):
    id: int
    company: str
    roles: list[str] = Field(default_factory=list)
    location: Optional[str] = None
    work_mode: Optional[Literal["remote", "hybrid", "onsite"]] = None
    employment_type: Optional[str] = None
    salary: Optional[str] = None
    tech_stack: list[str] = Field(default_factory=list)
    source_url: str


def load_posts() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))["posts"]


ROLE_RE = re.compile(r"engineer|developer|scientist|manager|roles?|CSMs?", re.I)
SENTENCE_STARTS = re.compile(r"\s(?:We|We're|Join|At|Our|Looking)\b")


def _trim(part: str, company: str) -> str:
    """Başlık bölümüne karışan ilk açıklama cümlesini kırpar."""
    cut = len(part)
    m = SENTENCE_STARTS.search(part)
    if m:
        cut = m.start()
    first_word = company.split()[0]
    idx = part.find(" " + first_word, 1)
    if idx > 0:
        cut = min(cut, idx)
    return part[:cut].strip()


def _header_parts(text: str) -> list[str]:
    parts = [p.strip() for p in text.split("|") if p.strip()][:6]
    company = re.sub(r"\s*\(.*?\)", "", parts[0]).strip()
    return [_trim(p, company) if i else p for i, p in enumerate(parts)]


def normalize(post: dict) -> JobPosting:
    text = post["text"]
    head = _header_parts(text)
    company = re.sub(r"\s*\(.*?\)", "", head[0]).strip()
    company = _trim(company, "~")
    head[0] = company
    head_text = " | ".join(head)

    lower = head_text.lower()
    work_mode = None
    if "hybrid" in lower:
        work_mode = "hybrid"
    elif "remote" in lower:
        work_mode = "remote"
    elif "onsite" in lower or "on-site" in lower:
        work_mode = "onsite"

    emp = re.search(r"full[- ]?time|part[- ]?time|contract", head_text, re.I)
    salary = re.search(r"\$?\d{2,3}\s*-\s*\d{2,3}k\+?", head_text, re.I)

    location = next((p for p in head[1:] if re.search(r"^[A-Z][\w .]+, [A-Z]", p)
                     and not ROLE_RE.search(p)), None)
    if location is None:
        location = next((p for p in head[1:] if re.search(r"remote|onsite|hybrid", p, re.I)), None)

    roles = [p for p in head[1:] if ROLE_RE.search(p)
             and len(p) < 120]
    stack = [t for t in TECH_VOCAB if re.search(rf"(?<![\w.]){re.escape(t)}(?![\w])", text, re.I)]
    if "Postgres" in stack and "PostgreSQL" in stack:
        stack.remove("Postgres")

    return JobPosting(
        id=post["id"], company=company, roles=roles, location=location, work_mode=work_mode,
        employment_type=emp.group(0).title() if emp else None,
        salary=salary.group(0) if salary else None, tech_stack=stack,
        source_url=f"https://news.ycombinator.com/item?id={post['id']}",
    )
