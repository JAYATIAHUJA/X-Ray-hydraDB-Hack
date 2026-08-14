from __future__ import annotations

import os
from pathlib import Path

import boto3


def _read_secret(path_env: str) -> str:
    path = os.environ[path_env]
    return Path(path).read_text(encoding="utf-8").strip()


def main() -> None:
    bucket = os.environ["XRAY_BUCKET_NAME"]
    client = boto3.client(
        "s3",
        endpoint_url=os.environ["AWS_ENDPOINT_URL"],
        aws_access_key_id=_read_secret("AWS_ACCESS_KEY_ID_FILE"),
        aws_secret_access_key=_read_secret("AWS_SECRET_ACCESS_KEY_FILE"),
        region_name="us-east-1",
    )
    existing = {item["Name"] for item in client.list_buckets()["Buckets"]}
    if bucket not in existing:
        client.create_bucket(Bucket=bucket)
    client.head_bucket(Bucket=bucket)


if __name__ == "__main__":
    main()
