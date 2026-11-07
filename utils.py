from urllib.parse import urlparse, urlunparse, urljoin


def validate_url(raw_url):
    """User ka URL check karta hai.
    Sahi ho to (True, clean_url) deta hai, galat ho to (False, error_message)."""
    if not raw_url or not raw_url.strip():
        return False, "URL is empty. please enter a URL."

    url = raw_url.strip()

    # Agar user ne http/https nahi likha, add https
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)

    # Domain hona zaroori hai, aur usme dot (.) hona chahiye (except local host)
    if not parsed.netloc:
        return False, "Invalid URL."
    if "." not in parsed.netloc and "localhost" not in parsed.netloc:
        return False, "Invalid domain (e.g. example.com)."
    if " " in url:
        return False, "URL cannot contain spaces."
    return True, url


def normalize_url(url):
    """Same page ke alag URLs ko ek jaisa banata hai.

    Example: HTTPS://Site.com/about/#team  ->  https://site.com/about
    """
    parsed = urlparse(url)

    scheme = parsed.scheme.lower()      # HTTP -> http
    netloc = parsed.netloc.lower()      # SITE.com -> site.com

    # Default port hata do (:80 aur :443 ki zarurat nahi)
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    # Path ke end se "/" hatao (lekin sirf "/" ho to rehne do)
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # fragment (#team) hamesha hata do, kyunki wo same page hi hai
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def is_internal(url, base_url):
    """Check karta hai ki url usi website ka hai ya nahi."""
    host = urlparse(url).netloc.lower()
    base_host = urlparse(base_url).netloc.lower()
    # www.site.com aur site.com ko same maano
    return host.removeprefix("www.") == base_host.removeprefix("www.")


def make_absolute(href, current_page_url):
    """Relative link (/about) ko poora URL banata hai.
    Mailto, tel, javascript: jaise links ko None return karta hai."""
    href = href.strip()
    if not href or href.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
        return None
    full = urljoin(current_page_url, href)
    if not full.startswith(("http://", "https://")):
        return None
    return full