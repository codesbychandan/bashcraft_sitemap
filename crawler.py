import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup

from utils import normalize_url, is_internal, make_absolute
HEADERS = {"User-Agent": "BashCraftSitemapBot/1.0 (student project)"}
MAX_TITLE_LENGTH = 100

BOT_BLOCKED = {401, 403, 405, 429, 999}   # ye "broken" nahi, "restricted" hain

# In files ko crawl nahi karenge (HTML page nahi hain), bas status check karenge
SKIP_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
                   ".zip", ".mp4", ".mp3", ".css", ".js", ".ico", ".xml")


def check_link(url, timeout=8, retries=1):
    """Ek link ka status check karta hai.
    Timeout ya connection error par ek baar dobara try karta hai.
    Return: (status_code, reason). Site na khule to (None, 'Timeout' etc.)"""
    last = (None, "Request failed")
    for _ in range(retries + 1):
        try:
            resp = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            # Kuch servers HEAD allow nahi karte, to GET se dobara try karo
            if resp.status_code >= 400:
                resp = requests.get(url, headers=HEADERS, timeout=timeout,
                                    allow_redirects=True, stream=True)
                resp.close()
            return resp.status_code, resp.reason or ""
        except requests.exceptions.Timeout:
            last = (None, "Timeout")
        except requests.exceptions.SSLError:
            return None, "SSL error"
        except requests.exceptions.ConnectionError:
            last = (None, "Cannot connect")
        except requests.exceptions.RequestException:
            return None, "Request failed"
    return last


def is_broken(status):
    return status is None or status >= 400


class SiteCrawler:
    def __init__(self, start_url, max_pages=50, max_depth=3, delay=0.2, timeout=8,render_js = False):
        self.start_url = normalize_url(start_url)
        self.max_pages = max_pages    # kitne pages tak crawl karna hai
        self.max_depth = max_depth    # homepage se kitne click door tak jana hai
        self.delay = delay            # har request ke beech wait (website pe load na pade)
        self.timeout = timeout
        self.render_js = render_js    # True ho to JS chalake links nikalega
        self._browser = None
        self.robots = None     
           
    def _load_robots(self):
        """robots.txt padhta hai. Na mile ya error aaye to sab allowed maanta hai."""
        parsed = urlparse(self.start_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            resp = requests.get(robots_url, headers=HEADERS, timeout=self.timeout)
            if resp.status_code == 200:
                rp = RobotFileParser()
                rp.parse(resp.text.splitlines())
                return rp
        except requests.exceptions.RequestException:
            pass
        return None
    # ---------- Ek page fetch karke uski info nikalna ----------
    def _render(self, url):
        """Asli browser me page kholke JavaScript ke baad ka HTML deta hai."""
        page = self._browser.new_page()
        try:
            page.goto(url, wait_until="load", timeout=30000)
            page.wait_for_timeout(2000)    # JS ko links banane ka time do
            return page.content()
        except Exception as e:
            print(f"[render failed] {url}: {e}")   # error ab chupega nahi
            return None
        finally:
            page.close()

    def _fetch_page(self, url, depth):
        page = {"url": url, "title": "", "status": None, "error": "",
                "depth": depth, "internal_links": [], "external_links": []}
        try:
            resp = requests.get(url, headers=HEADERS, timeout=self.timeout)
        except requests.exceptions.Timeout:
            page["error"] = "Timeout"
            return page
        except requests.exceptions.RequestException:
            page["error"] = "Cannot connect"
            return page

        page["status"] = resp.status_code
        if resp.status_code >= 400:
            page["error"] = resp.reason or "HTTP error"
            return page

        # Sirf HTML pages parse karenge
        if "text/html" not in resp.headers.get("Content-Type", ""):
            page["title"] = "(not an HTML page)"
            return page

        html = resp.text
        if self.render_js:
            html = self._render(url) or html    # render fail ho to raw HTML chalega
        soup = BeautifulSoup(html, "html.parser")

        # Title: missing ho to default, bahut lamba ho to kaat do
        title = soup.title.get_text(strip=True) if soup.title else ""
        if not title:
            title = "(No title)"
        elif len(title) > MAX_TITLE_LENGTH:
            title = title[:MAX_TITLE_LENGTH] + "..."
        page["title"] = title

        # Links nikalo, normalize karo, internal/external me baanto
        internal, external = set(), set()
        for a in soup.find_all("a", href=True):
            full = make_absolute(a["href"], resp.url)
            if full is None:
                continue
            link = normalize_url(full)
            if link == url:          # page apne aap ko link kare to ignore
                continue
            if is_internal(link, self.start_url):
                internal.add(link)
            else:
                external.add(link)

        page["internal_links"] = sorted(internal)
        page["external_links"] = sorted(external)
        return page

    # ---------- Main crawling loop ----------
    def crawl(self):
        if self.render_js:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                self._browser = p.chromium.launch()
                try:
                    return self._crawl()
                finally:
                    self._browser.close()
        return self._crawl()
        
    def _crawl(self):
        self.robots = self._load_robots()        
        queue = deque([(self.start_url, 0)])   # (url, depth)
        queued = {self.start_url}              # jo queue me aa chuke hain (duplicate rokne ke liye)
        pages = {}

        while queue and len(pages) < self.max_pages:
            url, depth = queue.popleft()
            page = self._fetch_page(url, depth)
            pages[url] = page

            if depth < self.max_depth:
                for link in page["internal_links"]:
                    if link in queued or link.lower().endswith(SKIP_EXTENSIONS):
                        continue
                    if self.robots and not self.robots.can_fetch(HEADERS["User-Agent"], link):
                        continue    # robots.txt ne mana kiya hai                    
                    queued.add(link)
                    queue.append((link, depth + 1))

            time.sleep(self.delay)

        return self._build_result(pages)

    # ---------- Broken links check + final result ----------
    def _build_result(self, pages):
        # Jin links ka status pehle se pata hai (crawled pages)
        link_status = {u: (p["status"], p["error"]) for u, p in pages.items()}

        # Baaki sab links (external + uncrawled internal) ka status check karo
        to_check = set()
        for p in pages.values():
            for link in p["internal_links"] + p["external_links"]:
                if link not in link_status:
                    to_check.add(link)

        to_check = sorted(to_check)
        with ThreadPoolExecutor(max_workers=8) as pool:   # 8 links ek saath check
            results = pool.map(lambda u: check_link(u, self.timeout), to_check)
            for link, result in zip(to_check, results):
                link_status[link] = result

        # Broken aur restricted links, har URL sirf ek baar (duplicate nahi)
        broken, restricted = {}, {}
        for p in pages.values():
            for kind, links in (("internal", p["internal_links"]),
                                ("external", p["external_links"])):
                for link in links:
                    status, reason = link_status[link]
                    if not is_broken(status):
                        continue
                    bucket = restricted if status in BOT_BLOCKED else broken
                    if link not in bucket:
                        bucket[link] = {"url": link, "found_on": p["url"], "type": kind,
                                        "status": status, "reason": reason, "occurrences": 0}
                    bucket[link]["occurrences"] += 1

        broken = list(broken.values())
        restricted = list(restricted.values())


        # Har page ke link counts
        page_list = []
        for p in pages.values():
            p["internal_count"] = len(p["internal_links"])
            p["external_count"] = len(p["external_links"])
            page_list.append(p)

        all_internal = {l for p in page_list for l in p["internal_links"]}
        all_external = {l for p in page_list for l in p["external_links"]}

        return {
            "start_url": self.start_url,
            "pages": page_list,
            "broken_links": broken,
            "restricted_links": restricted,
            "stats": {
                "pages_discovered": len(page_list),
                "internal_links": len(all_internal),
                "external_links": len(all_external),
                "broken_links": len(broken),
                "restricted_links": len(restricted),
            },
        }

# Terminal se seedha test karne ke liye: python crawler.py
if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://bashcraftclub.vercel.app/"
    result = SiteCrawler(url, max_pages=20, max_depth=2, render_js=True).crawl()
    
    print("STATS:", result["stats"])
    print()
    for p in result["pages"]:
        print(f"[{p['status']}] depth={p['depth']} {p['url']}")
        print(f"      title: {p['title']}  | internal={p['internal_count']} external={p['external_count']}")
    print()
    print("BROKEN LINKS:", len(result["broken_links"]))
    for b in result["broken_links"]:
        print(f"  {b['url']} -> {b['status'] or b['reason']} (found on {b['found_on']})")
        print()
    print("RESTRICTED (bot-blocked, likely fine):", len(result["restricted_links"]))
    for r in result["restricted_links"][:5]:
        print(f"  {r['url']} -> {r['status']}")    