#!/usr/bin/env python3
"""Fix post data and merge news listing excerpts for incomplete posts."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRAPE = ROOT / "_scrape"
PAGES_DIR = SCRAPE / "pages"
DATA_FILE = SCRAPE / "site_data.json"


def is_wayback_junk(entry: dict) -> bool:
    return (
        entry.get("title") == "Wayback Machine"
        or "Fight for the Future" in entry.get("markdown", "")
        or "Internet Archive" in entry.get("markdown", "")
    )


def parse_excerpt(excerpt: str) -> dict:
    date_match = re.search(r"(\d{4}-\d{2}-\d{2}T[\d:+]+)", excerpt)
    date = date_match.group(1) if date_match else ""
    author_match = re.search(r"^([A-Za-z ]+?)\d{4}-\d{2}-\d{2}", excerpt)
    author = author_match.group(1).strip() if author_match else ""
    parts = re.split(r"\d{4}\|", excerpt)
    body = parts[-1].strip() if len(parts) > 1 else excerpt
    body = re.sub(r"\[\.\.\.\]$", "", body).strip()
    return {"date": date, "author": author, "body": body}


def post_from_news(np: dict) -> dict:
    slug = np["slug"]
    meta = parse_excerpt(np.get("excerpt", ""))
    return {
        "title": np["title"],
        "slug": slug,
        "path": f"/{slug}/",
        "url": np.get("url", f"https://marinelife2030.org/{slug}/"),
        "date": meta["date"],
        "author": meta["author"],
        "description": meta["body"][:200],
        "markdown": meta["body"],
        "html": f"<p>{meta['body']}</p>",
        "images": [],
    }


def fix_posts():
    data = json.loads(DATA_FILE.read_text())
    news_posts = json.loads((SCRAPE / "news_posts.json").read_text())
    news_by_slug = {p["slug"]: p for p in news_posts if p.get("slug") and p["slug"] != "marinelife2030.org"}

    fixed_posts = []
    for post in data["posts"]:
        slug = post["slug"]
        if is_wayback_junk(post) and slug in news_by_slug:
            entry = post_from_news(news_by_slug[slug])
            fixed_posts.append(entry)
            (PAGES_DIR / f"{slug}.json").write_text(json.dumps(entry, indent=2))
            print(f"Replaced junk with excerpt: {entry['title']}")
        elif is_wayback_junk(post):
            print(f"Skipped junk post with no excerpt: {slug}")
        else:
            if slug in news_by_slug and post.get("title") == "Wayback Machine":
                post["title"] = news_by_slug[slug]["title"]
            fixed_posts.append(post)

    # Add any missing posts from news listing
    existing_slugs = {p["slug"] for p in fixed_posts}
    for slug, np in news_by_slug.items():
        if slug not in existing_slugs:
            entry = post_from_news(np)
            fixed_posts.append(entry)
            (PAGES_DIR / f"{slug}.json").write_text(json.dumps(entry, indent=2))
            print(f"Added post from excerpt: {entry['title']}")

    data["posts"] = sorted(fixed_posts, key=lambda p: p.get("date", ""), reverse=True)

    if not data.get("navigation"):
        data["navigation"] = [
            {"text": "Home", "url": "https://marinelife2030.org/"},
            {"text": "About", "url": "https://marinelife2030.org/about/"},
            {"text": "News", "url": "https://marinelife2030.org/news/"},
            {"text": "Upcoming Events", "url": "https://marinelife2030.org/upcoming-events/"},
            {"text": "Newsletters", "url": "https://marinelife2030.org/newsletters/"},
            {"text": "Affiliated Projects", "url": "https://marinelife2030.org/affiliated-projects/"},
            {"text": "Join Us", "url": "https://marinelife2030.org/join-us/"},
        ]

    DATA_FILE.write_text(json.dumps(data, indent=2))
    print(f"Final: {len(data['pages'])} pages, {len(data['posts'])} posts")


if __name__ == "__main__":
    fix_posts()
