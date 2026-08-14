from __future__ import annotations

import argparse
import time
import urllib.error
import urllib.request


def _wait_url(url: str, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if 200 <= response.status < 300:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(1)
    raise SystemExit(f"timed out waiting for {url}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-url", required=True)
    parser.add_argument("--indexer-admin-url", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()
    _wait_url(f"{args.admin_url.rstrip('/')}/readyz", args.timeout_seconds)
    _wait_url(f"{args.indexer_admin_url.rstrip('/')}/readyz", args.timeout_seconds)


if __name__ == "__main__":
    main()
