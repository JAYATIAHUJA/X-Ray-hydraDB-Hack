from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
LOCK_PATH = Path("infra/runtime-images.lock")
OFFICIAL_IMAGES = {"golang", "python"}


def verify(lock_path: Path = LOCK_PATH) -> None:
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    images = payload.get("images")
    if not isinstance(images, dict) or not images:
        raise SystemExit("runtime image lock has no images")
    for name, image in images.items():
        if not isinstance(image, dict):
            raise SystemExit(f"{name} image lock entry is malformed")
        repository = image.get("repository")
        digest = image.get("digest")
        if not isinstance(repository, str) or (
            "/" not in repository and repository not in OFFICIAL_IMAGES
        ):
            raise SystemExit(f"{name} repository is not explicit")
        if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
            raise SystemExit(f"{name} digest must be sha256:<64 lowercase hex>")
        if digest == "sha256:" + "0" * 64:
            raise SystemExit(f"{name} digest is unresolved")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--lock", default=str(LOCK_PATH))
    args = parser.parse_args()
    if args.verify:
        verify(Path(args.lock))


if __name__ == "__main__":
    main()
