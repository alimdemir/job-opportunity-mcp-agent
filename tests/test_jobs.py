import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs import JobPosting, load_posts, normalize  # noqa: E402


def by_company(name):
    return next(normalize(p) for p in load_posts() if normalize(p).company == name)


def test_all_posts_normalize_to_schema():
    jobs = [normalize(p) for p in load_posts()]
    assert len(jobs) == 10
    assert all(isinstance(j, JobPosting) for j in jobs)
    assert all(j.source_url.startswith("https://news.ycombinator.com/item?id=") for j in jobs)


def test_missing_information_is_not_guessed():
    # ilanda maaş yazmıyorsa alan boş kalmalı
    jobs = [normalize(p) for p in load_posts()]
    assert any(j.salary is None for j in jobs)
    assert all(j.work_mode in (None, "remote", "hybrid", "onsite") for j in jobs)


def test_snout_posting_fields():
    job = by_company("Snout")
    assert job.work_mode == "remote"
    assert job.employment_type == "Full Time"
    assert {"React", "PostgreSQL", "AWS", "Python"} <= set(job.tech_stack)
    assert "Postgres" not in job.tech_stack  # PostgreSQL ile tekrar etmesin


def test_dataset_has_no_email_addresses():
    import re
    assert not any(re.search(r"[\w.+-]+@[\w-]+\.\w+", p["text"]) for p in load_posts())
