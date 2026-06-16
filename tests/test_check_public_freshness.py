import pytest

from tools import check_public_freshness as cpf


def test_extract_build_date_reads_ssg_meta() -> None:
    html = '<script type="application/json" id="ssg-meta">{"build":"2026-06-17"}</script>'

    assert cpf.extract_build_date(html) == "2026-06-17"


def test_check_html_fails_when_public_build_date_is_stale() -> None:
    html = '<script type="application/json" id="ssg-meta">{"build":"2026-06-16"}</script>'

    with pytest.raises(cpf.FreshnessError, match="public build date mismatch"):
        cpf.check_html(html, expected_date="2026-06-17")
