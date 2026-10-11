"""İş fırsatı ajanı için MCP sunucusu (Türk şirketlerinin kariyer sayfalarındaki ilanlar)."""
import json
import logging
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


@mcp.tool()
def search_postings(keyword: str, remote_only: bool = False, limit: int = 5) -> list[dict]:
    """Trendyol, Insider One, Midas ve Dream Games ilanlarında anahtar kelime arar.

    Başlık ve açıklama metninde arar. Dönüş: eşleşen ilanların id, şirket, rol, konum ve çalışma biçimi.
    """
    log.info("arama: %s (remote_only=%s)", keyword, remote_only)
    results = []
    for post in load_posts():
        if keyword.lower() not in full_text(post).lower():
            continue
        job = normalize(post)
        if remote_only and job.work_mode != "remote":
            continue
        results.append({"id": job.id, "company": job.company, "role": job.role,
                        "location": job.location, "work_mode": job.work_mode})
    return results[:limit]


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
