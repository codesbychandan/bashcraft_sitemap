import pytest

from utils import is_internal, make_absolute, normalize_url, validate_url


# ---------- normalize_url ----------
def test_url_variations_become_one():
    variants = [
        "https://site.com/about",
        "https://site.com/about/",
        "https://SITE.com/about",
        "https://site.com/about#team",
        "HTTPS://site.com:443/about/#x",
    ]
    assert len({normalize_url(v) for v in variants}) == 1


def test_normalize_exact_output():
    assert normalize_url("HTTPS://BashCraftClub.vercel.app/about/#team") == \
        "https://bashcraftclub.vercel.app/about"


def test_normalize_root_gets_slash():
    assert normalize_url("https://site.com") == "https://site.com/"


def test_normalize_keeps_query():
    assert normalize_url("https://site.com/a?x=1#f") == "https://site.com/a?x=1"


def test_normalize_removes_default_port():
    assert normalize_url("http://site.com:80/a") == "http://site.com/a"


def test_normalize_is_idempotent():
    once = normalize_url("HTTPS://Site.com/a/#z")
    assert normalize_url(once) == once


# ---------- validate_url ----------
def test_validate_adds_https():
    assert validate_url("bashcraftclub.vercel.app") == (True, "https://bashcraftclub.vercel.app")


def test_validate_keeps_http():
    assert validate_url("http://example.com") == (True, "http://example.com")


@pytest.mark.parametrize("bad", ["", "   ", None, "abc", "https://", "exa mple.com"])
def test_validate_rejects_bad_input(bad):
    ok, message = validate_url(bad)
    assert ok is False
    assert message    # error message khali nahi hona chahiye


# ---------- is_internal ----------
def test_internal_same_domain():
    assert is_internal("https://site.com/a", "https://site.com/")


def test_internal_www_is_same_site():
    assert is_internal("https://www.site.com/a", "https://site.com/")


def test_external_other_domain():
    assert not is_internal("https://other.com/a", "https://site.com/")


def test_subdomain_is_external():
    # Known behaviour: subdomain ko alag site maante hain
    assert not is_internal("https://blog.site.com/", "https://site.com/")


# ---------- make_absolute ----------
def test_absolute_from_root_relative():
    assert make_absolute("/about", "https://site.com/x") == "https://site.com/about"


def test_absolute_from_relative():
    assert make_absolute("about", "https://site.com/team/") == "https://site.com/team/about"


def test_absolute_protocol_relative():
    assert make_absolute("//cdn.com/x", "https://site.com/") == "https://cdn.com/x"


@pytest.mark.parametrize("href", ["mailto:a@b.com", "tel:123", "javascript:void(0)", "#top", ""])
def test_non_http_links_skipped(href):
    assert make_absolute(href, "https://site.com/") is None