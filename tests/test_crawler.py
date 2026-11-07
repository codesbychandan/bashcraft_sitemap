import pytest
import requests

import crawler
from crawler import SiteCrawler, check_link, is_broken


class FakeResp:
    """requests ke response ki nakal."""
    def __init__(self, text="", status=200, url="https://site.com/", content_type="text/html"):
        self.text = text
        self.status_code = status
        self.url = url
        self.reason = "OK" if status < 400 else "Error"
        self.headers = {"Content-Type": content_type}

    def close(self):
        pass


def raise_exc(exc):
    def _raiser(*args, **kwargs):
        raise exc
    return _raiser


# ---------- is_broken ----------
@pytest.mark.parametrize("status,expected", [(200, False), (301, False), (399, False),
                                             (404, True), (500, True), (None, True)])
def test_is_broken(status, expected):
    assert is_broken(status) is expected


# ---------- check_link ----------
def test_check_link_timeout(monkeypatch):
    monkeypatch.setattr("crawler.requests.head", raise_exc(requests.exceptions.Timeout()))
    assert check_link("https://x.com") == (None, "Timeout")


def test_check_link_cannot_connect(monkeypatch):
    monkeypatch.setattr("crawler.requests.head", raise_exc(requests.exceptions.ConnectionError()))
    assert check_link("https://x.com") == (None, "Cannot connect")


def test_check_link_404(monkeypatch):
    monkeypatch.setattr("crawler.requests.head", lambda *a, **k: FakeResp(status=404))
    monkeypatch.setattr("crawler.requests.get", lambda *a, **k: FakeResp(status=404))
    status, _ = check_link("https://x.com/missing")
    assert status == 404


def test_check_link_head_not_allowed_falls_back_to_get(monkeypatch):
    monkeypatch.setattr("crawler.requests.head", lambda *a, **k: FakeResp(status=405))
    monkeypatch.setattr("crawler.requests.get", lambda *a, **k: FakeResp(status=200))
    assert check_link("https://x.com")[0] == 200


# ---------- _fetch_page (HTML parsing) ----------
HTML = """
<html><head><title>Home</title></head><body>
  <a href="/about">A</a>
  <a href="/about/">A with slash</a>
  <a href="/about#team">A with fragment</a>
  <a href="https://site.com/contact">Contact</a>
  <a href="https://other.com/x">X</a>
  <a href="https://other.com/x">X again</a>
  <a href="mailto:a@b.com">mail</a>
  <a href="javascript:void(0)">js</a>
  <a href="/">self link</a>
</body></html>
"""


def make_crawler():
    return SiteCrawler("https://site.com/", render_js=False)


def test_fetch_page_splits_and_dedupes_links(monkeypatch):
    monkeypatch.setattr("crawler.requests.get", lambda *a, **k: FakeResp(HTML))
    page = make_crawler()._fetch_page("https://site.com/", 0)
    assert page["title"] == "Home"
    assert page["internal_links"] == ["https://site.com/about", "https://site.com/contact"]
    assert page["external_links"] == ["https://other.com/x"]


def test_fetch_page_missing_title(monkeypatch):
    monkeypatch.setattr("crawler.requests.get",
                        lambda *a, **k: FakeResp("<html><body>hi</body></html>"))
    assert make_crawler()._fetch_page("https://site.com/", 0)["title"] == "(No title)"


def test_fetch_page_long_title_is_cut(monkeypatch):
    html = f"<html><head><title>{'x' * 300}</title></head></html>"
    monkeypatch.setattr("crawler.requests.get", lambda *a, **k: FakeResp(html))
    title = make_crawler()._fetch_page("https://site.com/", 0)["title"]
    assert len(title) <= 103 and title.endswith("...")


def test_fetch_page_non_html(monkeypatch):
    monkeypatch.setattr("crawler.requests.get",
                        lambda *a, **k: FakeResp("%PDF", content_type="application/pdf"))
    page = make_crawler()._fetch_page("https://site.com/file", 0)
    assert page["title"] == "(not an HTML page)"
    assert page["internal_links"] == []


def test_fetch_page_404(monkeypatch):
    monkeypatch.setattr("crawler.requests.get", lambda *a, **k: FakeResp(status=404))
    page = make_crawler()._fetch_page("https://site.com/nope", 1)
    assert page["status"] == 404 and page["error"]


def test_fetch_page_timeout(monkeypatch):
    monkeypatch.setattr("crawler.requests.get", raise_exc(requests.exceptions.Timeout()))
    page = make_crawler()._fetch_page("https://site.com/", 0)
    assert page["status"] is None and page["error"] == "Timeout"


# ---------- Full crawl (graph logic) ----------
A, B, C = "https://site.com/", "https://site.com/b", "https://site.com/c"


def fake_page(url, depth, internal=(), external=(), status=200):
    return {"url": url, "title": "t", "status": status,
            "error": "" if status < 400 else "Error", "depth": depth,
            "internal_links": list(internal), "external_links": list(external)}


@pytest.fixture
def patched(monkeypatch):
    """Crawl tests ke liye network band: robots aur link check fake."""
    monkeypatch.setattr(SiteCrawler, "_load_robots", lambda self: None, raising=False)
    monkeypatch.setattr("crawler.check_link", lambda url, timeout=8: (200, "OK"))
    return monkeypatch


def run_crawl(monkeypatch, graph, **kwargs):
    def fake_fetch(self, url, depth):
        return graph[url](depth)
    monkeypatch.setattr(SiteCrawler, "_fetch_page", fake_fetch)
    return SiteCrawler(A, delay=0, render_js=False, **kwargs).crawl()


def test_crawl_loop_terminates(patched):
    graph = {A: lambda d: fake_page(A, d, [B]),
             B: lambda d: fake_page(B, d, [C]),
             C: lambda d: fake_page(C, d, [A])}      # C -> A wapas (loop)
    result = run_crawl(patched, graph)
    urls = [p["url"] for p in result["pages"]]
    assert sorted(urls) == sorted([A, B, C])         # har page sirf ek baar


def test_crawl_respects_max_pages(patched):
    graph = {A: lambda d: fake_page(A, d, [B, C]),
             B: lambda d: fake_page(B, d),
             C: lambda d: fake_page(C, d)}
    assert len(run_crawl(patched, graph, max_pages=2)["pages"]) == 2


def test_crawl_respects_max_depth(patched):
    graph = {A: lambda d: fake_page(A, d, [B]),
             B: lambda d: fake_page(B, d, [C]),
             C: lambda d: fake_page(C, d)}
    urls = [p["url"] for p in run_crawl(patched, graph, max_depth=1)["pages"]]
    assert C not in urls


def test_crawl_reports_broken_internal_page(patched):
    graph = {A: lambda d: fake_page(A, d, [B]),
             B: lambda d: fake_page(B, d, status=404)}
    result = run_crawl(patched, graph)
    assert [b["url"] for b in result["broken_links"]] == [B]
    assert result["stats"]["broken_links"] == 1


def test_bot_blocked_links_go_to_restricted(patched):
    linkedin = "https://www.linkedin.com/in/someone"
    patched.setattr("crawler.check_link", lambda url, timeout=8: (999, ""))
    graph = {A: lambda d: fake_page(A, d, external=[linkedin])}
    result = run_crawl(patched, graph)
    assert result["stats"]["broken_links"] == 0
    assert result["stats"]["restricted_links"] == 1


def test_same_broken_link_on_many_pages_counted_once(patched):
    dead = "https://other.com/dead"
    patched.setattr("crawler.check_link", lambda url, timeout=8: (404, "Not Found"))
    graph = {A: lambda d: fake_page(A, d, [B], [dead]),
             B: lambda d: fake_page(B, d, external=[dead])}
    result = run_crawl(patched, graph)
    assert len(result["broken_links"]) == 1
    assert result["broken_links"][0]["occurrences"] == 2