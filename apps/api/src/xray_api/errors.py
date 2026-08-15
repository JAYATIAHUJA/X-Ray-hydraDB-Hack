from __future__ import annotations

from fastapi import HTTPException


def not_found(detail: str, *, code: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "type": "about:blank",
            "title": "Not Found",
            "status": 404,
            "detail": detail,
            "code": code,
            "retryable": False,
        },
    )


__all__ = ["not_found"]
