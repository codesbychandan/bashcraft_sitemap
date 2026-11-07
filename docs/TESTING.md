# Testing Documentation

## 1. Automated Tests

Run with:

```bash
python -m pytest -v
```

**Result: 56 passed.** All network calls are mocked, so the suite is fast and works offline.

| File | Tests | What it covers |
|---|---|---|
| `tests/test_utils.py` | URL normalization, validation, internal/external detection, relative link resolution | Core URL logic |
| `tests/test_crawler.py` | Status checks, HTML parsing, title edge cases, crawl graph behaviour | Crawler logic |
| `tests/test_app.py` | Home page, invalid input, unreachable site, export before analysis | Flask routes |

### Selected test cases

| Test | Input | Expected | Result |
|---|---|---|---|
| URL variations become one | `/about`, `/about/`, `/about#team`, uppercase host, `:443` | All normalize to one URL | Pass |
| Normalization is idempotent | Normalize twice | Same output | Pass |
| Validation adds https | `bashcraftclub.vercel.app` | `https://bashcraftclub.vercel.app` | Pass |
| Invalid URLs rejected | empty, spaces, `abc`, `https://`, `exa mple.com`, `None` | Error message returned | Pass |
| `www` treated as same site | `www.site.com` vs `site.com` | Internal | Pass |
| Subdomain treated as external | `blog.site.com` vs `site.com` | External | Pass |
| Non-page links skipped | `mailto:`, `tel:`, `javascript:`, `#top`, empty | Ignored | Pass |
| Duplicate links merged | `/about` repeated 3 ways | One internal link | Pass |
| Missing title | Page without `<title>` | `(No title)` | Pass |
| Very long title | 300-character title | Cut to 100 plus `...` | Pass |
| Non-HTML page | `application/pdf` | Not parsed, no links | Pass |
| Timeout | Request raises Timeout | Status `None`, reason `Timeout` | Pass |
| Connection error | Request raises ConnectionError | Reason `Cannot connect` | Pass |
| HEAD rejected (405) | HEAD 405, GET 200 | Falls back to GET, status 200 | Pass |
| **Crawl loop** | A → B → C → A | Each page crawled once, terminates | Pass |
| Max pages | Limit 2, three pages available | 2 pages crawled | Pass |
| Max depth | Depth 1, chain A → B → C | C not crawled | Pass |
| Broken internal page | Page returns 404 | Reported as broken | Pass |
| Bot-blocked link | Status 999 | Restricted, not broken | Pass |
| Same broken link on 2 pages | Dead link found twice | Reported once, `occurrences = 2` | Pass |
| Invalid URL via API | `""`, `abc`, `https://` | HTTP 400 with error | Pass |
| Unreachable site via API | Homepage cannot connect | HTTP 502 | Pass |
| Export before analysis | `/export/json`, `/export/csv`, `/export/broken` | HTTP 404 | Pass |

## 2. Manual Tests on the BashCraft Website

Tested on **https://bashcraftclub.vercel.app/** through the web UI (max pages 30, max depth 2, JS rendering on).

| # | Test | Expected | Actual |
|---|---|---|---|
| 1 | Full crawl of BashCraft | Home, about, contact, events, team and their sub-pages discovered | 15 pages: `/`, `/about`, `/contact`, `/events` (4 event pages), `/team` (6 team pages) |
| 2 | Broken links on BashCraft | No broken internal links | 0 broken links |
| 3 | Link counts | Internal and external links counted separately | 15 internal, 43 external |
| 4 | LinkedIn links | Not reported as broken | 35 listed as restricted (status 999/429) |
| 5 | JS-rendered links | Links found despite JS generation | With JS off: 0 links found. With JS on: 28 anchors on the homepage, 15 pages total |
| 6 | Same title on all pages | Shown without errors | All pages show the same title (single-page app). Paths in the tree tell pages apart |
| 7 | Export JSON / CSV / Broken CSV | Files download with correct data | _fill in after checking_ |
| 8 | Search and sort in Pages tab | Rows filter and reorder | _fill in after checking_ |

## 3. Manual Edge Case Tests

Run these in the UI and write the real result in the last column.

| # | Input / Action | Expected | Actual |
|---|---|---|---|
| 9 | Empty URL box, click Analyze | Error: URL is empty | _fill in_ |
| 10 | URL `abc` | Error: Invalid domain | _fill in_ |
| 11 | URL `bashcraftclub.vercel.app` (no https) | Works, https added automatically | _fill in_ |
| 12 | URL `https://this-site-does-not-exist-12345.com` | Error: Website cannot be reached | _fill in_ |
| 13 | Max depth = 0 | Only the homepage is crawled | _fill in_ |
| 14 | Max pages = 3 | Exactly 3 pages | _fill in_ |
| 15 | JS rendering unticked on BashCraft | Fewer or no links found (documented limitation) | _fill in_ |
| 16 | A different site, e.g. `https://example.com` | 1 page, external link(s), no crash | _fill in_ |

## 4. Bugs Found During Testing

| Bug | Cause | Fix |
|---|---|---|
| 0 links found on BashCraft | Links are created by JavaScript, invisible to `requests` | Added Playwright rendering |
| 65 "broken" links reported | Same link counted on every page; LinkedIn blocks bots (999/429) | De-duplicated broken links; added restricted category |
| `KeyError: 'pages'` | Result dictionary was edited incorrectly | Restored `pages` and `start_url` keys in the result |
| "Failed to fetch" in browser | Flask server had been stopped | Keep the server running while using the UI |

## 5. Not Tested

- Very large websites (hundreds of pages)
- Sites requiring login or cookies
- Concurrent users
- Pages that load content only after scrolling or clicking