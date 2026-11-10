#!/usr/bin/env python3
"""Inventory and archive links from Miagao's official transparency pages.

The WordPress API is used to enumerate the full Transparency category tree,
all posts in those categories, and Full Disclosure Policy pages. Every link or
embedded source in each post is retained. Direct media under wp-content/uploads
is downloaded once into data_sources/miagao_transparency_archive/files/.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "https://www.miagao.gov.ph"
API = f"{BASE}/wp-json/wp/v2/"
OUT_DIR = ROOT / "data_sources/miagao_transparency_archive"
FILE_DIR = OUT_DIR / "files"
OUT_JSON = ROOT / "analysis_output/miagao-transparency-source-inventory.json"
USER_AGENT = "BetterMiagao public-source inventory (research; contact: research@bettergov.ph)"
MAX_RETRIES = 3


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for field in ("href", "src", "data", "srcset"):
            value = attrs.get(field)
            if not value:
                continue
            if field == "srcset":
                values = [part.strip().split()[0] for part in value.split(",") if part.strip()]
            else:
                values = [value.strip()]
            for url in values:
                if url:
                    self.links.append({"url": html.unescape(url), "element": tag, "attribute": field})


def get(url: str, timeout=45):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(), dict(response.headers), response.geturl()
        except Exception as exc:  # network/source errors are recorded, then retried
            last_error = exc
            if attempt + 1 < MAX_RETRIES:
                time.sleep(1.5 * (attempt + 1))
    raise last_error


def api_pages(endpoint: str):
    page = 1
    rows = []
    while True:
        body, headers, _ = get(f"{API}{endpoint}&page={page}")
        batch = json.loads(body)
        if not isinstance(batch, list):
            break
        rows.extend(batch)
        total_pages = int(headers.get("X-WP-TotalPages", "1"))
        if page >= total_pages:
            break
        page += 1
    return rows


def category_tree():
    categories = api_pages("categories?per_page=100")
    roots = [category for category in categories if category.get("slug") == "transparency" and category.get("parent") == 0]
    if not roots:
        raise RuntimeError("Could not find the official Transparency category")
    root = roots[0]
    ids = {root["id"]}
    changed = True
    while changed:
        old = len(ids)
        ids.update(category["id"] for category in categories if category.get("parent") in ids)
        changed = old != len(ids)
    return categories, root, ids


def absolute(url: str, page_url: str) -> str | None:
    url = html.unescape(url.strip())
    if not url or url.startswith(("#", "javascript:", "mailto:", "tel:")):
        return None
    return urllib.parse.urljoin(page_url, url)


def clean_text(markup: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", markup))).strip()


def file_candidate(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    return "/wp-content/uploads/" in path


def download_one(url: str):
    FILE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(urllib.parse.urlparse(url).path).suffix[:12]
    name = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16] + suffix
    destination = FILE_DIR / name
    if destination.exists() and destination.stat().st_size:
        data = destination.read_bytes()
        return {"status": "already_archived", "localPath": str(destination.relative_to(ROOT)), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    try:
        data, headers, final_url = get(url, timeout=90)
        if not data:
            return {"status": "empty_response", "finalUrl": final_url}
        destination.write_bytes(data)
        return {
            "status": "downloaded",
            "localPath": str(destination.relative_to(ROOT)),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "contentType": headers.get("Content-Type"),
            "finalUrl": final_url,
        }
    except Exception as exc:
        return {"status": "download_error", "error": f"{type(exc).__name__}: {exc}"}


def main():
    categories, root, category_ids = category_tree()
    category_by_id = {category["id"]: category for category in categories}
    query = urllib.parse.urlencode({"categories": ",".join(map(str, sorted(category_ids))), "per_page": 100})
    posts = api_pages(f"posts?{query}")
    pages = api_pages("pages?per_page=100")
    disclosure_pages = [
        page for page in pages
        if "full-disclosure" in page.get("slug", "").lower()
        or "full disclosure" in clean_text(page.get("title", {}).get("rendered", "")).lower()
    ]

    records = []
    discovered_urls: dict[str, list[dict]] = {}
    for post in posts:
        post_url = post.get("link", "")
        content = post.get("content", {}).get("rendered", "")
        parser = LinkParser()
        parser.feed(content)
        links = []
        for raw_link in parser.links:
            url = absolute(raw_link["url"], post_url)
            if not url:
                continue
            link = {**raw_link, "url": url}
            links.append(link)
            discovered_urls.setdefault(url, []).append({"sourceUrl": post_url, "sourceTitle": clean_text(post.get("title", {}).get("rendered", "")), "sourceDate": post.get("date"), "element": link["element"], "attribute": link["attribute"]})
        cat_rows = [category_by_id[category_id] for category_id in post.get("categories", []) if category_id in category_by_id]
        records.append({
            "id": post.get("id"),
            "date": post.get("date"),
            "modified": post.get("modified"),
            "title": clean_text(post.get("title", {}).get("rendered", "")),
            "url": post_url,
            "categories": [{"id": category["id"], "name": category["name"], "url": category["link"]} for category in cat_rows],
            "contentText": clean_text(content),
            "links": links,
        })

    for page in disclosure_pages:
        page_url = page.get("link", "")
        content = page.get("content", {}).get("rendered", "")
        parser = LinkParser()
        parser.feed(content)
        links = []
        for raw_link in parser.links:
            url = absolute(raw_link["url"], page_url)
            if not url:
                continue
            link = {**raw_link, "url": url}
            links.append(link)
            discovered_urls.setdefault(url, []).append({"sourceUrl": page_url, "sourceTitle": clean_text(page.get("title", {}).get("rendered", "")), "sourceDate": page.get("date"), "element": link["element"], "attribute": link["attribute"]})
        records.append({
            "id": page.get("id"), "date": page.get("date"), "modified": page.get("modified"),
            "title": clean_text(page.get("title", {}).get("rendered", "")), "url": page_url,
            "categories": [], "contentText": clean_text(content), "links": links, "recordType": "disclosure_page",
        })

    uploads = sorted(url for url in discovered_urls if file_candidate(url))
    downloads = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(download_one, url): url for url in uploads}
        for future in as_completed(futures):
            downloads[futures[future]] = future.result()

    for post in records:
        for link in post["links"]:
            if link["url"] in downloads:
                link["archive"] = downloads[link["url"]]

    output = {
        "title": "Municipality of Miagao · official transparency source inventory",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "All WordPress posts in the official Transparency category and descendants, all Full Disclosure Policy pages, and every href/src/data/srcset link found in their published content. Every wp-content/uploads file is downloaded into the local source archive.",
        "site": BASE,
        "api": API,
        "categoryRoot": {"id": root["id"], "name": root["name"], "url": root["link"]},
        "categories": [{"id": category["id"], "parent": category["parent"], "name": category["name"], "slug": category["slug"], "postCount": category["count"], "url": category["link"]} for category in categories if category["id"] in category_ids],
        "summary": {
            "transparencyCategoryCount": len(category_ids),
            "transparencyPosts": len([record for record in records if record.get("recordType") != "disclosure_page"]),
            "fullDisclosurePages": len(disclosure_pages),
            "uniqueLinkedUrls": len(discovered_urls),
            "uploadsFilesLinked": len(uploads),
            "downloadedOrPresent": sum(result["status"] in ("downloaded", "already_archived") for result in downloads.values()),
            "downloadErrors": sum(result["status"] == "download_error" for result in downloads.values()),
            "downloadBytes": sum(result.get("bytes", 0) for result in downloads.values()),
        },
        "linkedUrls": [{"url": url, "sources": sources, "archive": downloads.get(url)} for url, sources in sorted(discovered_urls.items())],
        "records": records,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], indent=2))
    print(f"Wrote {OUT_JSON}")
    print(f"Archived linked uploads under {FILE_DIR}")


if __name__ == "__main__":
    main()
