from playwright.sync_api import sync_playwright

URL = "https://bashcraftclub.vercel.app/"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(URL, wait_until="load", timeout=30000)
    page.wait_for_timeout(3000)   # JS ko 3 second do

    html = page.content()
    print("Rendered HTML length:", len(html))
    print("<a> tags:", page.locator("a").count())
    print("<a href> tags:", page.locator("a[href]").count())
    print("buttons:", page.locator("button").count())
    print("onclick elements:", page.locator("[onclick]").count())

    print("\nFirst 15 hrefs:")
    for h in page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")[:15]:
        print("  ", h)

    print("\nFirst 500 chars of body text:")
    print(page.inner_text("body")[:500])

    browser.close()
    