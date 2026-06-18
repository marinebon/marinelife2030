#!/usr/bin/env python3
"""Generate Hugo site content from parsed WordPress data."""

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRAPE_DIR = ROOT / "_scrape"
DATA_FILE = SCRAPE_DIR / "site_data.json"
MEDIA_DIR = SCRAPE_DIR / "media"
SITE_DIR = ROOT

STATIC_PAGES = {
    "/": "content/_index.md",
    "/about/": "content/about/_index.md",
    "/affiliated-projects/": "content/affiliated-projects/_index.md",
    "/news/": "content/news/_index.md",
    "/newsletters/": "content/newsletters/_index.md",
    "/join-us/": "content/join-us/_index.md",
    "/style-guide/": "content/style-guide/_index.md",
    "/upcoming-events/": "content/upcoming-events/_index.md",
}


def yaml_str(value: str) -> str:
    value = value.replace("\n", " ").replace("\r", "").strip()
    if not value:
        return '""'
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def clean_markdown(md: str) -> str:
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = md.replace("[email protected]", "marinelife2030@gmail.com")
    md = md.replace("[email\u00a0protected]", "marinelife2030@gmail.com")
    md = re.sub(r"^ __\n", "", md, flags=re.MULTILINE)
    md = re.sub(r"\n__\n", "\n", md)
    # Normalize remote image URLs to local paths where filename is known
    md = re.sub(
        r"https://marinelife2030\.org/wp-content/uploads/[^)]+/([^/)]+)",
        r"/images/\1",
        md,
    )
    return md.strip()


def write_content_file(dest: Path, entry: dict, draft: bool = False):
    dest.parent.mkdir(parents=True, exist_ok=True)

    front_matter = ["---"]
    front_matter.append(f"title: {yaml_str(entry['title'])}")
    if entry.get("description"):
        front_matter.append(f"description: {yaml_str(entry['description'])}")
    if entry.get("date"):
        front_matter.append(f"date: {entry['date']}")
    if entry.get("author"):
        front_matter.append(f"author: {yaml_str(entry['author'])}")
    if draft:
        front_matter.append("draft: false")
    front_matter.append("---")

    content = "\n".join(front_matter) + "\n\n" + clean_markdown(entry["markdown"])
    dest.write_text(content)
    print(f"  Wrote {dest.relative_to(SITE_DIR)}")


def copy_images():
    static_images = SITE_DIR / "static" / "images"
    static_images.mkdir(parents=True, exist_ok=True)
    if MEDIA_DIR.exists():
        for img in MEDIA_DIR.iterdir():
            if img.is_file():
                shutil.copy2(img, static_images / img.name)


def generate():
    if not DATA_FILE.exists():
        print("Run parse_wordpress.py first")
        return

    data = json.loads(DATA_FILE.read_text())
    print(f"Generating Hugo content from {len(data['pages'])} pages, {len(data['posts'])} posts")

    copy_images()

    for path, dest_rel in STATIC_PAGES.items():
        entry = next((p for p in data["pages"] if p["path"] == path), None)
        if entry:
            write_content_file(SITE_DIR / dest_rel, entry)

    for post in data["posts"]:
        slug = post["path"].strip("/")
        dest = SITE_DIR / "content" / "news" / f"{slug}.md"
        write_content_file(dest, post)

    nav_file = SITE_DIR / "data" / "navigation.json"
    nav_file.parent.mkdir(parents=True, exist_ok=True)
    nav = []
    for item in data.get("navigation", []):
        path = item["url"].replace("https://marinelife2030.org", "").rstrip("/") or "/"
        if path.endswith(".pdf"):
            nav.append({"name": item["text"], "url": item["url"], "external": True})
        else:
            nav.append({"name": item["text"], "url": path, "external": False})
    nav_file.write_text(json.dumps(nav, indent=2))
    print(f"  Wrote {nav_file.relative_to(SITE_DIR)}")

    print(f"\nHugo content generation complete!")


if __name__ == "__main__":
    generate()
