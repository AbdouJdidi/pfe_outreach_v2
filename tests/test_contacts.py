import pytest

from src.contacts import classify_email, confidence_for_email, extract_emails


@pytest.mark.parametrize("email,expected", [
    ("careers@acme.com", "careers"),
    ("jobs@acme.com", "jobs"),
    ("talent@acme.com", "recruiting"),
    ("hr@acme.com", "hr"),
    ("contact@acme.com", "contact"),
    ("info@acme.com", "info"),
    ("dmitry@acme.com", "other"),
])
def test_classify_email(email, expected):
    assert classify_email(email) == expected


def test_extract_emails_cleans_and_filters():
    text = "Write to Jobs@Acme.com. Or test@example.com, logo@2x.png and hr@acme.com)"
    assert extract_emails(text) == {"jobs@acme.com", "hr@acme.com"}


def test_extract_emails_empty():
    assert extract_emails("") == set()
    assert extract_emails(None) == set()


def test_career_page_increases_confidence():
    on_home = confidence_for_email("info@acme.com", "https://acme.com")
    on_careers = confidence_for_email("info@acme.com", "https://acme.com/careers")
    assert on_careers > on_home
    assert on_careers <= 100
