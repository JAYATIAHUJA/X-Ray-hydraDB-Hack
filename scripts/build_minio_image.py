from __future__ import annotations

import argparse
import json
from pathlib import Path

LOCK_PATH = Path("infra/runtime-images.lock")
MINIO_COMMIT = "9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a"
MINIO_RELEASE = "RELEASE.2025-10-15T17-29-55Z"


def verify(lock_path: Path = LOCK_PATH) -> None:
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    images = payload["images"]
    for required in ("golang", "python"):
        if required not in images:
            raise SystemExit(f"{required} base image missing from runtime-images.lock")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--lock", default=str(LOCK_PATH))
    args = parser.parse_args()
    if args.verify:
        verify(Path(args.lock))
        return
    raise SystemExit(
        "MinIO source build requires Docker/network access; run after resolving real base digests."
    )


if __name__ == "__main__":
    main()
