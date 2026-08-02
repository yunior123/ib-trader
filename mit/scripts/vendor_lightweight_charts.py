from __future__ import annotations

from pathlib import Path

import httpx

VERSION = "5.2.0"
ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "backend" / "app" / "static" / "vendor"


def main() -> None:
    VENDOR.mkdir(parents=True, exist_ok=True)
    files = {
        "lightweight-charts.standalone.production.js": f"https://unpkg.com/lightweight-charts@{VERSION}/dist/lightweight-charts.standalone.production.js",
        "LIGHTWEIGHT_CHARTS_LICENSE.txt": f"https://unpkg.com/lightweight-charts@{VERSION}/LICENSE",
    }
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        for name, url in files.items():
            response = client.get(url)
            response.raise_for_status()
            (VENDOR / name).write_bytes(response.content)
            print(f"Saved {name}: {len(response.content):,} bytes")
    print("Change index.html to /static/vendor/lightweight-charts.standalone.production.js for fully local serving.")


if __name__ == "__main__":
    main()
