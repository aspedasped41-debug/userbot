from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    bot_token: str
    api_id: int
    api_hash: str
    admin_phone: str
    sessions_dir: Path


def _get_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""

    digits = "".join(ch for ch in phone if ch.isdigit())
    if not digits:
        return ""
    return f"+{digits}"


def load_settings() -> Settings:
    load_dotenv(BASE_DIR / ".env")

    sessions_dir = BASE_DIR / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    try:
        os.chmod(sessions_dir, 0o700)
    except OSError:
        pass

    return Settings(
        bot_token=_get_required("BOT_TOKEN"),
        api_id=int(_get_required("API_ID")),
        api_hash=_get_required("API_HASH"),
        admin_phone=normalize_phone(os.getenv("ADMIN_PHONE", "+998904058793")),
        sessions_dir=sessions_dir,
    )
