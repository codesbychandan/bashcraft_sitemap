import pytest

import app as app_module


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    app_module.LAST_RESULT.clear()
    return app_module.app.test_client()


def test_home_page_loads(client):
    assert client.get("/").status_code == 200


@pytest.mark.parametrize("bad", ["", "abc", "https://"])
def test_analyze_rejects_invalid_url(client, bad):
    res = client.post("/analyze", json={"url": bad})
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_analyze_unreachable_site(client, monkeypatch):
    class FakeCrawler:
        def __init__(self, *args, **kwargs):
            pass

        def crawl(self):
            return {"pages": [{"status": None, "error": "Cannot connect"}]}

    monkeypatch.setattr(app_module, "SiteCrawler", FakeCrawler)
    res = client.post("/analyze", json={"url": "https://nonexistent-site-xyz.com"})
    assert res.status_code == 502
    assert "cannot be reached" in res.get_json()["error"]


@pytest.mark.parametrize("path", ["/export/json", "/export/csv", "/export/broken"])
def test_export_before_analyze_returns_404(client, path):
    assert client.get(path).status_code == 404