import csv
import io
import json

from flask import Flask, Response, jsonify, render_template, request

from crawler import SiteCrawler
from utils import validate_url

app = Flask(__name__)
LAST_RESULT = {}   # last crawl ka result yahan rakhte hain, export ke liye


def clamp(value, low, high, default):
    """Number ko [low, high] ke beech rakhta hai. Galat input ho to default."""
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True) or {}

    ok, result = validate_url(data.get("url", ""))
    if not ok:
        return jsonify({"error": result}), 400

    max_pages = clamp(data.get("max_pages"), 1, 100, 30)
    max_depth = clamp(data.get("max_depth"), 0, 5, 2)
    render_js = bool(data.get("render_js", True))

    try:
        crawl = SiteCrawler(result, max_pages=max_pages, max_depth=max_depth,
                            render_js=render_js).crawl()
    except Exception as e:
        return jsonify({"error": f"Crawl failed: {e}"}), 500

    # Homepage hi na khule to clear error do
    first = crawl["pages"][0] if crawl["pages"] else None
    if first is None or first["status"] is None:
        reason = first["error"] if first else "Unknown error"
        return jsonify({"error": f"Website cannot be reached ({reason})."}), 502

    LAST_RESULT.clear()
    LAST_RESULT.update(crawl)
    return jsonify(crawl)


def download(content, filename, mimetype):
    return Response(content, mimetype=mimetype,
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/export/json")
def export_json():
    if not LAST_RESULT:
        return "Please analyze a website first.", 404
    return download(json.dumps(LAST_RESULT, indent=2), "sitemap.json", "application/json")


@app.route("/export/csv")
def export_csv():
    if not LAST_RESULT:
        return "Please analyze a website first.", 404
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["url", "title", "status", "depth", "internal_links", "external_links"])
    for p in LAST_RESULT["pages"]:
        writer.writerow([p["url"], p["title"], p["status"] or p["error"],
                         p["depth"], p["internal_count"], p["external_count"]])
    return download(out.getvalue(), "sitemap.csv", "text/csv")


@app.route("/export/broken")
def export_broken():
    if not LAST_RESULT:
        return "Please analyze a website first.", 404
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["url", "type", "status_or_reason", "found_on"])
    for b in LAST_RESULT["broken_links"]:
        writer.writerow([b["url"], b["type"], b["status"] or b["reason"], b["found_on"]])
    return download(out.getvalue(), "broken_links.csv", "text/csv")


if __name__ == "__main__":
    # Mac pe port 5000 AirPlay use karta hai, isliye 5001
    app.run(port=5001, debug=True, use_reloader=False)

