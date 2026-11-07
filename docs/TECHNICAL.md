# Technical Documentation

## 1. Architecture

```
Browser (index.html + script.js)
        │  POST /analyze {url, max_pages, max_depth, render_js}
        ▼
Flask app (app.py) ──► utils.validate_url()
        │
        ▼
SiteCrawler (crawler.py)
   ├─ robots.txt loader
   ├─ BFS crawl loop (queue + visited set)
   │     └─ _fetch_page(): requests (+ Playwright render) → BeautifulSoup
   │           └─ utils: make_absolute → normalize_url → is_internal
   └─ _build_result(): status checks (thread pool), broken/restricted split, stats
        │
        ▼  JSON
Browser renders stats, tree, tables.  /export/* downloads the last result.
```

| File | Responsibility |
|---|---|
| `utils.py` | URL validation, normalization, internal/external check, relative to absolute links |
| `crawler.py` | Crawling, page parsing, link status checks, result building |
| `app.py` | HTTP routes, input limits, export formats |
| `static/script.js` | Rendering tree/tables, search, sort |

## 2. Crawling Approach

The crawler uses **breadth-first search (BFS)**:

1. Put the start URL in a queue with depth 0.
2. Take a URL from the front of the queue and fetch the page.
3. Extract links, normalize them, and split into internal and external.
4. Add unseen internal links to the queue with `depth + 1`.
5. Repeat until the queue is empty, `max_pages` is reached, or `max_depth` is exceeded.

BFS was chosen because pages closest to the homepage are discovered first, so a page-count limit still produces a useful, shallow sitemap. A `delay` (0.2 s) between page requests avoids overloading the target server.

## 3. URL Normalization

`normalize_url()` converts different spellings of the same page into one string:

| Rule | Example |
|---|---|
| Lowercase scheme and host | `HTTPS://Site.com` → `https://site.com` |
| Remove fragment | `/about#team` → `/about` |
| Remove trailing slash (except root) | `/about/` → `/about` |
| Remove default ports | `:443` on https, `:80` on http |
| Empty path becomes `/` | `https://site.com` → `https://site.com/` |
| Query string is kept | `/a?x=1` stays different from `/a` |

The function is idempotent: normalizing an already-normalized URL returns the same value (covered by a test).

## 4. Duplicate Handling and Loop Prevention

A `queued` set stores every normalized URL that has ever entered the queue. A link is added to the queue only if it is not already in this set. Because the check happens **before** queueing, each page is fetched at most once, which also stops loops such as `A → B → C → A`. A page linking to itself is ignored. Links inside one page are stored in a set, so repeated links (for example, navbar and footer both linking to `/about`) are counted once.

## 5. Internal vs. External Links

`is_internal()` compares hostnames, treating `www.site.com` and `site.com` as the same site. Subdomains are considered external (documented limitation).

- **Internal** links are queued for crawling (within limits).
- **External** links are only status-checked. They are never crawled.
- `mailto:`, `tel:`, `javascript:` and `#anchor` links are ignored.
- Links to files such as images, PDFs, CSS and JS are not crawled, only status-checked.

## 6. Broken-Link Detection

Every discovered link gets a status:

- **Crawled pages** already have a status from the crawl, so they are not requested again.
- **All other links** (external and uncrawled internal) are checked with an HTTP `HEAD` request. If the server answers with 4xx/5xx, a `GET` is tried, because some servers reject `HEAD`.
- Checks run in parallel with a `ThreadPoolExecutor` (8 workers), which keeps pages with many external links fast.

A link is **broken** if the status is 400+ or the request failed. Failure reasons are reported separately: `Timeout`, `SSL error`, `Cannot connect`, `Request failed`.

**Restricted category:** statuses 401, 403, 405, 429 and 999 usually mean the server blocked automated requests (LinkedIn returns 999/429), not that the link is dead. These are listed under `restricted_links` and are not counted as broken. This was added after the first BashCraft run reported 65 false "broken" links.

**De-duplication:** each broken URL is reported once with an `occurrences` count and the first page it was found on.

## 7. JavaScript-Rendered Pages

The BashCraft site builds its links with JavaScript, so a plain `requests` download found 0 links. When **JS rendering** is enabled, Playwright opens the page in headless Chromium, waits for the page to load plus 2 seconds, and returns the rendered HTML. BeautifulSoup then parses this HTML. If rendering fails, the crawler prints an error and falls back to the raw HTML. Status checks still use `requests` because they are faster.

Trade-off: rendering is much slower (several seconds per page) and needs a Chromium download, so it is a checkbox rather than always on.

## 8. robots.txt

At the start of a crawl the crawler downloads `/robots.txt` and parses it with Python's `urllib.robotparser`. Internal links disallowed for the crawler's user agent are not queued. If `robots.txt` is missing or cannot be fetched, everything is treated as allowed.

## 9. Export

`app.py` keeps the latest result in memory (`LAST_RESULT`) and offers:

- `/export/json`: the full result (pages, links, broken, restricted, stats)
- `/export/csv`: one row per page (url, title, status, depth, link counts)
- `/export/broken`: broken-link report as CSV

Python's `csv` module is used so commas and quotes in titles are escaped correctly.

## 10. Edge Cases

| Edge case | Handling |
|---|---|
| Crawl loops | `queued` set (section 4) |
| URL variations | Normalization (section 3) |
| Many external links | Stored as a set per page, checked in parallel |
| Broken links, timeouts | Request timeout (8 s), error reasons reported |
| Missing title | Shown as `(No title)` |
| Very long title | Cut to 100 characters plus `...` |
| Invalid URL | Validation message returned with HTTP 400 |
| Unreachable website | Homepage fetch fails, HTTP 502 and a clear message |
| JS-generated links | Playwright rendering |
| Non-HTML resources | Not parsed, only status-checked |

## 11. Security and Robustness Decisions

- **No `innerHTML`:** page titles and URLs come from untrusted websites. The frontend uses `textContent`, which prevents cross-site scripting (XSS).
- **Input limits:** `clamp()` restricts `max_pages` (1-100) and `max_depth` (0-5), so a user cannot request an endless crawl.
- **No secrets:** the project needs no API keys or credentials.
- **Polite crawling:** custom User-Agent, delay between requests, robots.txt support.
- **Fetch size:** requests have timeouts to avoid hanging on slow servers.

## 12. Design Decisions and Trade-offs

| Decision | Reason | Trade-off |
|---|---|---|
| Python + Flask | Readable, few moving parts | Not as fast as async crawlers |
| BFS with queue + set | Simple, easy to reason about, shallow-first | Sequential page fetching (slower) |
| In-memory last result | Simple export | Single-user only |
| HEAD then GET | Faster, still accurate | Extra request for servers rejecting HEAD |
| Restricted category | Honest reporting for bot-blocking sites | Such links remain unverified |
| JS rendering as option | Correct on modern sites | Slow, needs Chromium |
| Mocked network in tests | Fast, offline, repeatable | Real-world behaviour checked manually |