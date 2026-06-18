#!/usr/bin/env python3
"""Download static assets referenced in Hugo content."""

import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
DEST = ROOT / "static" / "images"
ARCHIVE = "https://web.archive.org/web/20260325212054im_/https://marinelife2030.org"
LIVE = "https://marinelife2030.org"

# Known wp-content paths for files not under /images/
KNOWN_PATHS = {
    "ML2030_LogoColor300ppi.png": "/wp-content/uploads/2021/11/ML2030_LogoColor300ppi.png",
    "TriColorWave.png": "/wp-content/uploads/2022/05/TriColorWave.png",
    "BlueBottomWave.png": "/wp-content/uploads/2022/05/BlueBottomWave.png",
    "ML2030_CritterBackground.jpg": "/wp-content/uploads/2021/11/ML2030_CritterBackground.jpg",
    "UNDecadeLogo_White_300w.png": "/wp-content/uploads/2022/06/UNDecadeLogo_White_300w.png",
    "NewsPageTitle.png": "/wp-content/uploads/2022/05/NewsPageTitle.png",
    "ML2030_WebLogoWhite_500PXH-300x250.png": "/wp-content/uploads/2022/05/ML2030_WebLogoWhite_500PXH-300x250.png",
    "final_MarineLife_2030_v2-1-e1671565154817.png": "/wp-content/uploads/2023/01/final_MarineLife_2030_v2-1-e1671565154817.png",
    "3.-socmed-letters-to-the-sea-invitation-v3-300x300.png": "/wp-content/uploads/2024/08/3.-socmed-letters-to-the-sea-invitation-v3-300x300.png",
}


def collect_refs() -> set[str]:
    refs = set()
    for md in CONTENT.rglob("*.md"):
        refs.update(re.findall(r"/images/([^)\s\"']+)", md.read_text()))
    return refs


def guess_path(filename: str) -> list[str]:
    candidates = []
    if filename in KNOWN_PATHS:
        candidates.append(KNOWN_PATHS[filename])
    if filename.startswith("PartnerLogos_"):
        candidates.append(f"/wp-content/uploads/2022/05/{filename}")
    candidates.append(f"/wp-content/uploads/2022/05/{filename}")
    candidates.append(f"/wp-content/uploads/2021/11/{filename}")
    candidates.append(f"/wp-content/uploads/2023/01/{filename}")
    candidates.append(f"/wp-content/uploads/2024/08/{filename}")
    candidates.append(f"/wp-content/uploads/2022/08/{filename}")
    candidates.append(f"/wp-content/uploads/2022/06/{filename}")
    candidates.append(f"/images/{filename}")
  # PDFs and docs
    candidates.append(f"/wp-content/uploads/2022/08/{filename}")
    candidates.append(f"/wp-content/uploads/2023/03/{filename}")
    candidates.append(f"/wp-content/uploads/2024/01/{filename}")
    candidates.append(f"/wp-content/uploads/2024/11/{filename}")
    return list(dict.fromkeys(candidates))


def download(filename: str) -> bool:
    dest = DEST / filename
    if dest.exists() and dest.stat().st_size > 500:
        print(f"  skip {filename}")
        return True

    headers = {"User-Agent": "Mozilla/5.0"}
    for base, path in [(ARCHIVE, p) for p in guess_path(filename)] + [(LIVE, p) for p in guess_path(filename)]:
        url = f"{base}{path}"
        try:
            resp = requests.get(url, headers=headers, timeout=45)
            if resp.status_code == 200 and len(resp.content) > 500:
                # Reject wayback HTML pages
                if resp.content[:15].lower().startswith(b"<!doctype") or b"<html" in resp.content[:200].lower():
                    continue
                dest.write_bytes(resp.content)
                print(f"  ok {filename} ({len(resp.content)} bytes) from {base[:30]}...")
                return True
        except Exception:
            pass
        time.sleep(0.3)
    print(f"  FAIL {filename}")
    return False


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    refs = sorted(collect_refs())
    print(f"Downloading {len(refs)} assets...")
    ok = sum(download(f) for f in refs)
    print(f"Done: {ok}/{len(refs)} files")


if __name__ == "__main__":
    main()
