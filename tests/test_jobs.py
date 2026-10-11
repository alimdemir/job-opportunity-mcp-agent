import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs import JobPosting, assess_fit, load_posts, normalize  # noqa: E402


def job(posting_id):
    return next(normalize(p) for p in load_posts() if p["id"] == posting_id)


def test_all_posts_normalize_to_schema():
    jobs = [normalize(p) for p in load_posts()]
    assert len(jobs) == 14
    assert all(isinstance(j, JobPosting) for j in jobs)
    assert {j.source for j in jobs} == {"lever", "greenhouse"}
    assert {j.company for j in jobs} == {"Trendyol", "Insider One", "Midas", "Dream Games"}


def test_two_sources_map_to_same_fields():
    midas, dream = job(1), job(14)   # Lever ve Greenhouse
    assert (midas.country, midas.work_mode, midas.employment_type) == ("Türkiye", "remote", "Tam zamanlı")
    assert midas.source_url.startswith("https://jobs.lever.co/")
    assert dream.country == "Türkiye" and "greenhouse.io/dreamgames/jobs/" in dream.source_url


def test_missing_information_is_not_guessed():
    dream = job(14)                  # Greenhouse ilanında çalışma biçimi ve türü alanı yok
    assert dream.work_mode is None and dream.employment_type is None
    assert all(j.salary is None for j in map(normalize, load_posts()))   # hiçbir ilanda ücret yazmıyor


def test_remote_in_commitment_text_is_recognized():
    assert job(5).work_mode == "remote"   # "Full-Time (Remote)"


def test_requirements_are_extracted():
    assert job(8).required_languages == ["Almanca", "İngilizce"]      # (German Speaker)
    assert "Arapça" in job(9).required_languages                     # proficiency in Arabic
    assert job(12).nationality_only == "Suudi Arabistan"             # Saudi Nationals Only
    assert job(12).country == "Suudi Arabistan" and job(13).country == "Romanya"


def test_tech_stack_is_case_aware():
    assert {"Python", "PyTorch", "NLP", "SQL"} <= set(job(9).tech_stack)
    assert "Go" in job(5).tech_stack
    assert job(13).tech_stack == []


def test_dataset_has_no_email_addresses():
    from jobs import full_text
    assert not any(re.search(r"[\w.+-]+@[\w-]+\.\w+", full_text(p)) for p in load_posts())


def test_assess_fit_language_requirement():
    fit = assess_fit(job(9), ["python", "SQL", "Docker"])
    assert not fit.eligible and "dil şartı: Arapça" in fit.reasons
    assert fit.matched_skills == ["Python", "SQL"]   # büyük/küçük harf duyarsız, ilandaki yazımla


def test_assess_fit_country_and_nationality():
    fit = assess_fit(job(12), ["Excel"])
    assert not fit.eligible
    assert any(r.startswith("konum:") for r in fit.reasons)
    assert any(r.startswith("vatandaşlık şartı") for r in fit.reasons)


def test_assess_fit_remote_job_in_turkey_is_eligible():
    fit = assess_fit(job(3), ["Python"])
    assert fit.eligible and fit.matched_skills == ["Python"]


def test_assess_fit_unspecified_work_mode_is_reported_not_guessed():
    fit = assess_fit(job(14), ["Python"])
    assert fit.eligible and "çalışma biçimi ilanda belirtilmemiş" in fit.reasons
    assert not assess_fit(job(14), ["Python"], wants_remote=True).eligible
