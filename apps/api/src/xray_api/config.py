from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from os import PathLike


@dataclass(frozen=True, slots=True)
class XraySettings:
    hydra_uri: str | None = None
    hydra_user: str | None = None
    hydra_password: str | None = None
    hydra_database: str | None = None
    read_only: bool = False
    imports_enabled: bool = False
    write_token: str | None = None

    @property
    def hydra_configured(self) -> bool:
        return self.hydra_uri is not None


def settings_from_env(env: Mapping[str, str] | None = None) -> XraySettings:
    values = env if env is not None else os.environ
    return XraySettings(
        hydra_uri=_optional_env(values, "XRAY_HYDRA_URI"),
        hydra_user=_optional_env(values, "XRAY_HYDRA_USER"),
        hydra_password=_optional_env(values, "XRAY_HYDRA_PASSWORD"),
        hydra_database=_optional_env(values, "XRAY_HYDRA_DATABASE"),
        read_only=_boolean_env(values, "XRAY_READ_ONLY", default=False),
        imports_enabled=_boolean_env(values, "XRAY_ENABLE_IMPORTS", default=False),
        write_token=_optional_env(values, "XRAY_WRITE_TOKEN"),
    )


@lru_cache(maxsize=1)
def get_settings() -> XraySettings:
    return settings_from_env()


def _optional_env(values: Mapping[str, str | PathLike[str]], key: str) -> str | None:
    value = values.get(key)
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _boolean_env(values: Mapping[str, str | PathLike[str]], key: str, *, default: bool) -> bool:
    value = values.get(key)
    if value is None:
        return default
    rendered = str(value).strip().casefold()
    if rendered in {"1", "true", "yes", "on"}:
        return True
    if rendered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be a boolean value")


__all__ = ["XraySettings", "get_settings", "settings_from_env"]
