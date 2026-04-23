"""
OpenAI-compatible LLM client for AI analytics.

Primary: OpenRouter (https://openrouter.ai) — set OPENROUTER_API_KEY and optional OPENROUTER_MODEL.
Fallback: OpenAI direct — set OPENAI_API_KEY when not using OpenRouter.
"""
from __future__ import annotations

import os
import random
import time
from pathlib import Path

import httpx
from django.conf import settings


def _reload_dotenv_into_os_environ() -> None:
    """
    Re-apply .env so keys are visible in os.environ even if Django was started with
    empty OPENROUTER_* in the system environment (load_dotenv override fixes that at import,
    this repeats the same rule at request time for extra safety).
    """
    try:
        from dotenv import load_dotenv

        base = Path(getattr(settings, "BASE_DIR", "") or ".")
        load_dotenv(base.parent / ".env", override=True)
        load_dotenv(base / ".env", override=True)
    except Exception:
        pass


def _openrouter_key() -> str:
    _reload_dotenv_into_os_environ()
    return (
        (os.environ.get("OPENROUTER_API_KEY") or getattr(settings, "OPENROUTER_API_KEY", "") or "")
        .strip()
    )


def _openai_key() -> str:
    _reload_dotenv_into_os_environ()
    return (os.environ.get("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", "") or "").strip()


def _is_rate_limit_error(exc: BaseException) -> bool:
    if getattr(exc, "status_code", None) == 429:
        return True
    if type(exc).__name__ == "RateLimitError":
        return True
    text = str(exc)
    if "Error code: 429" in text or " 429" in text:
        return True
    if "429" in text and ("rate" in text.lower() or "limit" in text.lower() or "upstream" in text.lower()):
        return True
    return False


def streaming_chat_create(client, *, model: str, max_tokens: int, messages: list):
    """
    Call chat.completions.create(stream=True) with retries on HTTP 429.
    OpenRouter :free models often hit shared upstream limits; backoff reduces noise.
    """
    attempts = int(getattr(settings, "OPENROUTER_STREAM_RETRIES", 4))
    base = float(getattr(settings, "OPENROUTER_429_BACKOFF", 2.5))
    for i in range(max(1, attempts)):
        try:
            return client.chat.completions.create(
                model=model,
                stream=True,
                max_tokens=max_tokens,
                messages=messages,
            )
        except Exception as e:
            if not _is_rate_limit_error(e) or i >= attempts - 1:
                raise
            time.sleep(base * (i + 1) + random.uniform(0.25, 1.25))


def get_llm_client_and_model():
    """
    Return (client, model_id) for chat.completions.create(stream=True).
    """
    from openai import OpenAI

    http_client = httpx.Client(trust_env=False, timeout=120.0)

    key = _openrouter_key()
    if key:
        base = getattr(
            settings,
            "OPENROUTER_BASE_URL",
            os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        ).rstrip("/")
        model = (
            os.environ.get("OPENROUTER_MODEL")
            or getattr(
                settings,
                "OPENROUTER_MODEL",
                "qwen/qwen3-next-80b-a3b-instruct:free",
            )
        )
        referer = (
            (os.environ.get("OPENROUTER_HTTP_REFERER") or "")
            or getattr(settings, "OPENROUTER_HTTP_REFERER", "")
            or "http://127.0.0.1:8000"
        )
        # Header values must be encodable for HTTP (httpx may use strict ASCII in some paths).
        title = "ERIS - Escape Room Intelligence"
        client = OpenAI(
            base_url=base,
            api_key=key,
            default_headers={
                "HTTP-Referer": referer.encode("ascii", "replace").decode("ascii"),
                "X-Title": title,
            },
            http_client=http_client,
        )
        return client, model

    openai_key = _openai_key()
    if openai_key:
        client = OpenAI(api_key=openai_key, http_client=http_client)
        model = os.environ.get("OPENAI_MODEL") or getattr(settings, "OPENAI_MODEL", "gpt-4o")
        return client, model

    raise ValueError(
        "Set OPENROUTER_API_KEY (recommended) or OPENAI_API_KEY in .env, then restart the server. "
        "The file can live in the project folder (next to manage.py) or the parent folder."
    )


def llm_configured() -> bool:
    return bool(_openrouter_key() or _openai_key())


def get_llm_display_info():
    """For templates: is AI configured, and which provider/model label to show."""
    if _openrouter_key():
        _reload_dotenv_into_os_environ()
        return {
            "llm_configured": True,
            "llm_backend": "OpenRouter",
            "llm_model": os.environ.get("OPENROUTER_MODEL")
            or getattr(
                settings,
                "OPENROUTER_MODEL",
                "qwen/qwen3-next-80b-a3b-instruct:free",
            ),
        }
    if _openai_key():
        return {
            "llm_configured": True,
            "llm_backend": "OpenAI",
            "llm_model": os.environ.get("OPENAI_MODEL")
            or getattr(settings, "OPENAI_MODEL", "gpt-4o"),
        }
    return {
        "llm_configured": False,
        "llm_backend": None,
        "llm_model": None,
    }
