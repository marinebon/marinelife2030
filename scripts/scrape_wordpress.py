#!/usr/bin/env python3
"""Scrape marinelife2030.org WordPress content via Playwright."""

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import html2text
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://marinelife2030.org"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "_scrape"
PAGES_DIR = OUTPUT_DIR / "pages"
MEDIA_DIR = OUTPUT_DIR / "media"
DATA_FILE = OUTPUT_DIR / "site_data.json"

KNOWN_PATHS = [
    "/",
    "/about/",
    "/affiliated-projects/",
    "/news/",
    "/newsletters/",
    "/join-us/",
    "/contact/",
    "/resources/",
    "/events/",
    "/team/",
    "/leadership/",
    "/governance/",
    "/publications/",
]

h2t = html2text.HTML2Text()
h2t.body_width = 0
h2t.ignore_links = False
h2t.ignore_images = False


def slugify(url_path: str) -> str:
    path = url_path.strip("/")
    return path.replace("/", "_") or "home"


def extract_content(soup: BeautifulSoup) -> dict:
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    if " - Marine Life 2030" in title:
        title = title.replace(" - Marine Life 2030", "").strip()

    # Try common WordPress content containers
    content = None
    for selector in [
        "article",
        ".post-content",
        ".entry-content",
        "#content",
        "main",
        ".fusion-post-content",
        ".avada-page-content",
    ]:
        content = soup.select_one(selector)
        if content:
            break

    if not content:
        content = soup.find("body")

    # Remove nav, footer, scripts
    for tag in content.select("nav, header, footer, script, style, noscript, .fusion-footer"):
        tag.decompose()

    html = str(content)
    markdown = h2t.handle(html)

    images = []
    for img in content.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src:
            images.append(urljoin(BASE_URL, src))

    links = []
    for a in content.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/") or BASE_URL in href:
            links.append(urljoin(BASE_URL, href))

    meta_desc = ""
    desc_tag = soup.find("meta", attrs={"name": "description"})
    if desc_tag:
        meta_desc = desc_tag.get("content", "")

    return {
        "title": title,
        "description": meta_desc,
        "html": html,
        "markdown": markdown.strip(),
        "images": list(dict.fromkeys(images)),
        "links": list(dict.fromkeys(links)),
    }


def discover_urls(page) -> set[str]:
    urls = set()
    for path in KNOWN_PATHS:
        urls.add(urljoin(BASE_URL, path))

    # Try sitemap
    try:
        page.goto(f"{BASE_URL}/sitemap.xml", wait_until="domcontentloaded", timeout=30000)
        body = page.content()
        urls.update(re.findall(r"<loc>(https?://marinelife2030\.org[^<]+)</loc>", body))
    except Exception:
        pass

    # Try WP REST API
    for endpoint in ["pages", "posts"]:
        page_num = 1
        while True:
            api_url = f"{BASE_URL}/wp-json/wp/v2/{endpoint}?per_page=100&page={page_num}"
            try:
                page.goto(api_url, wait_until="domcontentloaded", timeout=30000)
                text = page.inner_text("body")
                items = json.loads(text)
                if not items:
                    break
                for item in items:
                    urls.add(item["link"])
                page_num += 1
            except Exception:
                break

    return urls


def download_image(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        filename = Path(parsed.path).name
        if not filename:
            return None
        dest = MEDIA_DIR / filename
        if dest.exists():
            return f"/images/{filename}"
        resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            dest.write_bytes(resp.content)
            return f"/images/{filename}"
    except Exception:
        pass
    return None


def scrape():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    site_data = {"pages": [], "posts": [], "navigation": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("Discovering URLs...")
        urls = discover_urls(page)
        print(f"Found {len(urls)} URLs")

        # Scrape navigation from homepage
        page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        time.sleep(3)
        soup = BeautifulSoup(page.content(), "html.parser")
        nav_links = []
        for nav in soup.select("nav a, .fusion-main-menu a, #menu a"):
            href = nav.get("href", "")
            text = nav.get_text(strip=True)
            if text and href and "marinelife2030.org" in urljoin(BASE_URL, href):
                nav_links.append({"text": text, "url": urljoin(BASE_URL, href)})
        site_data["navigation"] = list({v["url"]: v for v in nav_links}.values())
        print(f"Navigation: {[n['text'] for n in site_data['navigation']]}")

        # Add nav URLs to scrape list
        for link in site_data["navigation"]:
            urls.add(link["url"])

        scraped = set()
        for url in sorted(urls):
            if url in scraped:
                continue
            parsed = urlparse(url)
            if parsed.netloc and "marinelife2030.org" not in parsed.netloc:
                continue
            if any(x in url for x in ["/wp-json/", "/wp-admin/", "/feed/", ".xml", ".css", ".js"]):
                continue

            print(f"Scraping: {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(2)
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                content = extract_content(soup)

                path = parsed.path or "/"
                slug = slugify(path)
                is_post = "/20" in path or path.count("/") > 2

                # Download images
                local_images = {}
                for img_url in content["images"]:
                    local = download_image(img_url)
                    if local:
                        local_images[img_url] = local

                for orig, local in local_images.items():
                    content["markdown"] = content["markdown"].replace(orig, local)
                    content["html"] = content["html"].replace(orig, local)

                entry = {
                    "url": url,
                    "path": path,
                    "slug": slug,
                    "title": content["title"],
                    "description": content["description"],
                    "markdown": content["markdown"],
                    "html": content["html"],
                    "images": list(local_images.values()),
                    "date": "",
                }

                # Try to extract date from post
                date_el = soup.find("time")
                if date_el:
                    entry["date"] = date_el.get("datetime", date_el.get_text(strip=True))

                (PAGES_DIR / f"{slug}.json").write_text(json.dumps(entry, indent=2))

                if is_post:
                    site_data["posts"].append(entry)
                else:
                    site_data["pages"].append(entry)

                scraped.add(url)

                # Discover more links
                for link in content["links"]:
                    if link not in scraped:
                        urls.add(link)

            except Exception as e:
                print(f"  Error: {e}")

        browser.close()

    DATA_FILE.write_text(json.dumps(site_data, indent=2))
    print(f"\nDone! {len(site_data['pages'])} pages, {len(site_data['posts'])} posts")
    print(f"Data saved to {DATA_FILE}")


if __name__ == "__main__":
    scrape()
