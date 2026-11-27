"""Read normal public council search pages; do not use private APIs or submit forms."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "sources"
SOURCE.mkdir(parents=True, exist_ok=True)


class PublicSearch(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []
        self.current = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self.skip += 1
        if tag == "a" and attrs.get("href"):
            self.current = {"url": attrs["href"], "class": attrs.get("class", ""), "text": ""}

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag == "a" and self.current is not None:
            self.links.append(self.current)
            self.current = None

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())
            if self.current is not None:
                self.current["text"] += data


def fetch(term):
    url = "https://we.snu.ac.kr/?" + urllib.parse.urlencode({"s": term})
    name = "we_" + re.sub(r'[<>:"/\\|?*\s]+', "_", term)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25) as r:
            data = r.read()
            status = r.status
        (SOURCE / f"{name}.html").write_bytes(data)
        parser = PublicSearch()
        parser.feed(data.decode("utf-8", "replace"))
        text = "\n".join(parser.parts)
        (SOURCE / f"{name}.txt").write_text(text, encoding="utf-8")
        posts = []
        for entry in parser.links:
            if "subject" in entry["class"].split() and re.search(r"[?&]p=\d+", entry["url"]):
                pid = re.search(r"[?&]p=(\d+)", entry["url"]).group(1)
                contents = [x["text"].strip() for x in parser.links if x["url"] == entry["url"]]
                posts.append({"post_id": pid, "url": "https://we.snu.ac.kr/" + pid + "/", "title": entry["text"].strip(), "public_search_text": max(contents, key=len, default="")})
        return {"query": term, "url": url, "http_status": status, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "capture_at_utc": datetime.now(timezone.utc).isoformat(), "posts": posts, "result_count_text": re.findall(r".{0,15}총\s*[\d,]+건.{0,30}", text)}
    except Exception as e:
        return {"query": term, "url": url, "error": str(e)}


if __name__ == "__main__":
    terms = ["교통총조사", "교통 총조사", "교통 설문", "셔틀 설문", "하교셔틀", "교통 브리핑", "교통총조사 결과"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(fetch, terms))
    (ROOT / "council_search.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in results:
        print(json.dumps({k: row[k] for k in ("query", "error", "result_count_text") if k in row}, ensure_ascii=False))
        for p in row.get("posts", []):
            print(p["post_id"], p["title"])
