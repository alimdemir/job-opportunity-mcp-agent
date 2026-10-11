"""İş fırsatı ajanı için MCP sunucusu (Türk şirketlerinin kariyer sayfalarındaki ilanlar)."""
import json
import logging
import re
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from jobs import DATA, FitReport, JobPosting, assess_fit, full_text, load_posts, normalize

# stdio taşımasında stdout protokole ayrılmış; loglar stderr'e yazılıyor
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("tr-jobs")

mcp = FastMCP("tr-jobs")


def _find(posting_id: int) -> dict:
    for post in load_posts():
        if post["id"] == posting_id:
            return post
    raise ToolError(f"{posting_id} numaralı ilan bulunamadı")


# İlanların çoğu İngilizce; Türkçe aramalar yaygın İngilizce karşılıklarıyla birlikte aranır
SYNONYMS = {
    "veri bilimi": ["data science", "data scientist"], "veri bilimci": ["data science", "data scientist"],
    "yapay zeka": ["ai", "machine learning", "llm"], "makine öğrenmesi": ["machine learning"],
    "yazılım mühendisi": ["software engineer"], "yazılım": ["software"], "güvenlik": ["security"],
    "ürün yöneticisi": ["product manager"], "veri analizi": ["analytics"], "analitik": ["analytics"],
    "uzaktan": ["remote"],
}


def _terms(keyword: str) -> list[str]:
    """'veri bilimi veya yapay zekâ' gibi bir aramayı ayrı ifadelere ve karşılıklarına böler."""
    text = keyword.lower().replace("â", "a").replace("î", "i").replace("û", "u")
    parts = [p.strip() for p in re.split(r",|/|\bveya\b|\bya da\b|\bor\b", text) if p.strip()]
    terms = []
    for part in parts:
        terms.append(part)
        terms += SYNONYMS.get(part, [])
    return terms


def _matches(term: str, text: str) -> bool:
    if len(term) <= 3:  # "ai" gibi kısa ifadeler kelime içinde (ör. "maintain") eşleşmesin
        return re.search(rf"\b{re.escape(term)}\b", text, re.I) is not None
    return term in text.lower()


@mcp.tool()
def search_postings(keyword: str, remote_only: bool = False, limit: int = 5) -> list[dict]:
    """Trendyol, Insider One, Midas ve Dream Games ilanlarında anahtar kelime arar.

    Başlık ve açıklama metninde arar. İlanların çoğu İngilizcedir; Türkçe ifadeler yaygın
    İngilizce karşılıklarıyla birlikte aranır (ör. "veri bilimi" -> "data scientist").
    Birden fazla ifade "veya" ya da virgülle ayrılabilir; herhangi biri eşleşirse ilan döner.
    Sonuçlar, ifadenin başlıkta geçtiği ilanlar önde olacak şekilde sıralanır.
    Dönüş: eşleşen ilanların id, şirket, rol, konum ve çalışma biçimi.
    """
    terms = _terms(keyword)
    log.info("arama: %s -> %s (remote_only=%s)", keyword, terms, remote_only)
    scored = []
    for post in load_posts():
        text = full_text(post)
        job = normalize(post)
        # başlıkta geçen ifade açıklamada geçenden daha güçlü bir işarettir
        score = sum(3 if _matches(t, job.role) else 1 for t in terms if _matches(t, text))
        if score == 0 or (remote_only and job.work_mode != "remote"):
            continue
        scored.append((score, {"id": job.id, "company": job.company, "role": job.role,
                               "location": job.location, "work_mode": job.work_mode}))
    scored.sort(key=lambda x: -x[0])   # sıralama kararlı: eşit puanda veri setindeki sıra korunur
    return [row for _, row in scored[:limit]]


@mcp.tool()
def get_posting(posting_id: int) -> JobPosting:
    """Tek bir ilanı ortak şablona dönüştürülmüş hâliyle döndürür."""
    return normalize(_find(posting_id))


@mcp.tool()
def check_fit(posting_id: int, skills: list[str], country: str = "Türkiye",
              languages: list[str] = ["Türkçe", "İngilizce"], wants_remote: bool = False) -> FitReport:
    """İlanı kullanıcı profiline göre kural tabanlı ön kontrolden geçirir.

    İlanın ülkesini, vatandaşlık şartını ('Saudi Nationals Only' gibi), istenen dilleri,
    çalışma biçimini ve ilanda açıkça geçen becerilerle eşleşmeyi raporlar.
    Bir ilanı önermeden önce çağırın.
    """
    log.info("ön kontrol: %s (%s, %s)", posting_id, country, languages)
    return assess_fit(normalize(_find(posting_id)), skills, country, tuple(languages), wants_remote)


@mcp.resource("tr-jobs://sources")
def sources() -> str:
    """Kullanılan ilan kaynakları (şirket, işe alım sistemi, ilan adresi)."""
    return json.dumps(json.loads(DATA.read_text(encoding="utf-8"))["sources"], ensure_ascii=False, indent=1)


if __name__ == "__main__":
    mcp.run()
