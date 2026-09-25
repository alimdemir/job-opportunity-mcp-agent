"""İş fırsatı ajanı için MCP sunucusu (Hacker News 'Who is hiring?')."""
import logging
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from jobs import FitReport, JobPosting, assess_fit, load_posts, normalize

# stdio taşımasında stdout protokole ayrılmış; loglar stderr'e yazılıyor
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("hn-jobs")

mcp = FastMCP("hn-jobs")


@mcp.tool()
def search_postings(keyword: str, remote_only: bool = False, limit: int = 5) -> list[dict]:
    """Ağustos 2026 'Who is hiring?' ilanlarında anahtar kelime arar.

    Dönüş: eşleşen ilanların id, şirket ve çalışma biçimi bilgisi.
    """
    log.info("arama: %s (remote_only=%s)", keyword, remote_only)
    results = []
    for post in load_posts():
        if keyword.lower() not in post["text"].lower():
            continue
        job = normalize(post)
        if remote_only and job.work_mode != "remote":
            continue
        results.append({"id": job.id, "company": job.company, "work_mode": job.work_mode})
    return results[:limit]


@mcp.tool()
def get_posting(posting_id: int) -> JobPosting:
    """Tek bir ilanı ortak şablona dönüştürülmüş hâliyle döndürür."""
    for post in load_posts():
        if post["id"] == posting_id:
            return normalize(post)
    raise ToolError(f"{posting_id} numaralı ilan bulunamadı")


@mcp.tool()
def check_fit(posting_id: int, skills: list[str], country: str = "Türkiye", wants_remote: bool = True) -> FitReport:
    """İlanı kullanıcı profiline göre kural tabanlı ön kontrolden geçirir.

    Uzaktan ilanlardaki bölge kısıtını (ör. 'Remote US'), çalışma biçimini ve ilanda
    açıkça geçen becerilerle eşleşmeyi raporlar. Bir ilanı önermeden önce çağırın.
    """
    log.info("ön kontrol: %s (%s)", posting_id, country)
    for post in load_posts():
        if post["id"] == posting_id:
            return assess_fit(normalize(post), skills, country, wants_remote)
    raise ToolError(f"{posting_id} numaralı ilan bulunamadı")


@mcp.resource("hn://threads/2026-08")
def thread_info() -> str:
    """Kullanılan kaynak başlığın bilgisi."""
    return "Ask HN: Who is hiring? (August 2026) - https://news.ycombinator.com/item?id=49156683"


if __name__ == "__main__":
    mcp.run()
