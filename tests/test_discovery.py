import pytest

from src import discovery
from tests.conftest import add_company


def test_load_queries_skips_comments_blanks_and_duplicates(tmp_path):
    f = tmp_path / "queries.txt"
    f.write_text("# comment\n\nDevOps startup Lyon\n  DevOps startup Lyon \nAI startup Berlin\n", encoding="utf-8")
    assert discovery.load_queries(f) == ["DevOps startup Lyon", "AI startup Berlin"]


def test_load_queries_falls_back_to_builtin(tmp_path):
    assert discovery.load_queries(tmp_path / "missing.txt") == discovery.QUERIES


def test_repo_queries_file_is_valid():
    queries = discovery.load_queries()
    assert len(queries) >= 40
    assert all(len(q) < 100 for q in queries)


@pytest.mark.parametrize("query,expected", [
    ("stage PFE 2027 Sousse informatique", "Sousse, Tunisia"),
    ("stage PFE 2027 ingénieur logiciel Tunis", "Tunis, Tunisia"),
    ("startup SaaS tunisienne", "Tunisia"),
    ("software company Tunisia", "Tunisia"),  # "tunisia" must not match "tunis "
    ("stage ingénieur cloud 2027 Paris", "Paris, France"),
    ("startup IA Montréal stage", "Montreal, Canada"),
    ("Kubernetes consulting company Europe", "Europe"),
    ("AI agents startup", None),
])
def test_infer_location(query, expected):
    assert discovery.infer_location(query) == expected


def test_known_domains(temp_db):
    add_company("Acme", "acme.com", "Acme builds software.")
    assert discovery.known_domains() == {"acme.com"}
