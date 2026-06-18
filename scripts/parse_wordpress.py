#!/usr/bin/env python3
"""Parse WordPress HTML from Wayback Machine archives."""

import gzip
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import html2text
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://marinelife2030.org"
ARCHIVE_TS = "20260325212054"
ARCHIVE_PREFIX = f"https://web.archive.org/web/{ARCHIVE_TS}id_/"
SCRAPE_DIR = Path(__file__).resolve().parent.parent / "_scrape"
PAGES_DIR = SCRAPE_DIR / "pages"
MEDIA_DIR = SCRAPE_DIR / "media"
DATA_FILE = SCRAPE_DIR / "site_data.json"

STATIC_PAGES = {
    "/": "home",
    "/about/": "about",
    "/affiliated-projects/": "affiliated-projects",
    "/news/": "news",
    "/newsletters/": "newsletters",
    "/join-us/": "join-us",
    "/style-guide/": "style-guide",
    "/upcoming-events/": "upcoming-events",
}

SKIP_PATTERNS = [
    "/wp-json/", "/wp-admin/", "/feed/", "/author/", "/category/", "/tag/",
    "/cdn-cgi/", "#", ".css", ".js", ".xml",
]

h2t = html2text.HTML2Text()
h2t.body_width = 0
h2t.ignore_links = False
h2t.ignore_images = False


def read_html(path: Path) -> str:
    data = path.read_bytes()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data.decode("utf-8", errors="replace")


def clean_wayback_url(url: str) -> str:
    url = re.sub(r"https?://web\.archive\.org/web/\d+im?_/", "", url)
    url = re.sub(r"https?://web\.archive\.org/web/\d+/", "", url)
    return url


def slug_from_path(path: str) -> str:
    return path.strip("/").replace("/", "_") or "home"


def should_skip(url: str) -> bool:
    if any(p in url for p in SKIP_PATTERNS):
        return True
    parsed = urlparse(url)
    if parsed.netloc and "marinelife2030.org" not in parsed.netloc:
        return True
    if parsed.path.endswith((".jpg", ".png", ".gif", ".pdf", ".svg", ".webp", ".zip")):
        return True
    return False


def fetch_archive(path: str) -> str | None:
    slug = slug_from_path(path)
    local = SCRAPE_DIR / f"{slug}.html"
    if local.exists() and local.stat().st_size > 1000:
        return read_html(local)

    url = f"{ARCHIVE_PREFIX}{BASE_URL}{path}"
    print(f"  Fetching {path}...")
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        if resp.status_code == 200 and len(resp.content) > 1000:
            local.write_bytes(resp.content)
            time.sleep(1)
            return read_html(local)
    except Exception as e:
        print(f"  Error fetching {path}: {e}")
    return None


def extract_content(soup: BeautifulSoup) -> dict:
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True).replace(" - Marine Life 2030", "").strip()

    content = None
    for selector in [
        "article.fusion-post",
        ".fusion-portfolio-post",
        "article",
        ".post-content",
        ".entry-content",
        "#content",
        "main",
    ]:
        content = soup.select_one(selector)
        if content and len(content.get_text(strip=True)) > 50:
            break

    if not content:
        content = soup.find("body")

    for tag in content.select(
        "nav, header, footer, script, style, noscript, "
        ".fusion-footer, .fusion-tb-header, .fusion-tb-footer, "
        ".fusion-sharing-box, .related-posts"
    ):
        tag.decompose()

    # Fix wayback image URLs
    for img in content.find_all("img"):
        for attr in ("src", "data-src", "data-lazy-src"):
            if img.get(attr):
                img[attr] = clean_wayback_url(img[attr])
    for a in content.find_all("a", href=True):
        a["href"] = clean_wayback_url(a["href"])

    html = str(content)
    markdown = h2t.handle(html).strip()

    images = []
    for img in content.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src and not src.startswith("data:"):
            images.append(urljoin(BASE_URL, src))

    meta_desc = ""
    desc_tag = soup.find("meta", attrs={"name": "description"})
    if desc_tag:
        meta_desc = desc_tag.get("content", "")

    date = ""
    time_tag = soup.find("time")
    if time_tag:
        date = time_tag.get("datetime", time_tag.get_text(strip=True))
    else:
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", soup.get_text())
        if date_match:
            date = date_match.group(1)

    author = ""
    author_tag = soup.select_one(".fusion-meta-info a, .author a, .entry-author a")
    if author_tag:
        author = author_tag.get_text(strip=True)

    return {
        "title": title,
        "description": meta_desc,
        "html": html,
        "markdown": markdown,
        "images": list(dict.fromkeys(images)),
        "date": date,
        "author": author,
    }


def discover_urls() -> set[str]:
    urls = set(STATIC_PAGES.keys())
    for html_file in SCRAPE_DIR.glob("*.html"):
        if html_file.name == "live_home.html":
            continue
        soup = BeautifulSoup(read_html(html_file), "html.parser")
        for a in soup.find_all("a", href=True):
            href = clean_wayback_url(a["href"])
            if href.startswith("/"):
                href = urljoin(BASE_URL, href)
            if "marinelife2030.org" in href and not should_skip(href):
                urls.add(urlparse(href).path if urlparse(href).path.endswith("/") else urlparse(href).path + "/")
                urls.add(urlparse(href).path.rstrip("/") + "/" if not urlparse(href).path.endswith("/") else urlparse(href).path)
    return {u if u.endswith("/") or u == "/" else u + "/" for u in urls if u}


def is_post(path: str) -> bool:
    static = set(STATIC_PAGES.keys())
    if path in static:
        return False
    # News posts have long slugs
    slug = path.strip("/")
    if slug in ("join-us", "style-guide", "upcoming-events", "newsletters", "affiliated-projects", "about", "news"):
        return False
    return bool(slug)


def download_images(images: list[str]) -> dict[str, str]:
    mapping = {}
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    for url in images:
        parsed = urlparse(url)
        filename = Path(parsed.path).name
        if not filename or filename == "/":
            continue
        dest = MEDIA_DIR / filename
        local_path = f"/images/{filename}"
        if dest.exists():
            mapping[url] = local_path
            continue
        try:
            resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                dest.write_bytes(resp.content)
                mapping[url] = local_path
        except Exception:
            pass
    return mapping


def parse():
    SCRAPE_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    print("Discovering URLs...")
    urls = discover_urls()
    print(f"Found {len(urls)} URLs")

    site_data = {"pages": [], "posts": [], "navigation": []}

    for path in sorted(urls):
        if should_skip(path):
            continue

        slug = slug_from_path(path)
        print(f"Parsing {path} ({slug})")

        html = fetch_archive(path)
        if not html:
            print(f"  SKIP - no content")
            continue

        soup = BeautifulSoup(html, "html.parser")
        data = extract_content(soup)
        data.update({"url": urljoin(BASE_URL, path), "path": path, "slug": slug})

        img_map = download_images(data["images"])
        for orig, local in img_map.items():
            data["markdown"] = data["markdown"].replace(orig, local)
            data["html"] = data["html"].replace(orig, local)
        data["local_images"] = list(img_map.values())

        (PAGES_DIR / f"{slug}.json").write_text(json.dumps(data, indent=2))

        if is_post(path):
            site_data["posts"].append(data)
        else:
            site_data["pages"].append(data)

    # Navigation from home page
    home_html = fetch_archive("/")
    if home_html:
        soup = BeautifulSoup(home_html, "html.parser")
        nav_items = []
        for a in soup.select(".fusion-main-menu > ul > li > a"):
            text = a.get_text(strip=True)
            href = clean_wayback_url(a.get("href", ""))
            if text and href and "marinelife2030.org" in urljoin(BASE_URL, href):
                nav_items.append({"text": text, "url": urljoin(BASE_URL, href)})
        site_data["navigation"] = list({v["url"]: v for v in nav_items}.values())

    DATA_FILE.write_text(json.dumps(site_data, indent=2))
    print(f"\nDone: {len(site_data['pages'])} pages, {len(site_data['posts'])} posts")
    for p in site_data["pages"]:
        print(f"  PAGE: {p['title']}")
    for p in site_data["posts"]:
        print(f"  POST: {p['title']}")


if __name__ == "__main__":
    parse()
