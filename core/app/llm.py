"""The ONLY module that talks to an LLM (core/CLAUDE.md). OpenAI SDK pointed at the configured gateway.
Every setting comes from .env; a missing key fails loudly, naming the key, never printing a value.
Failures (timeout, connection, HTTP error, 402 budget, empty or truncated response) raise LLMUnavailable:
callers fall back to cache or template. Token usage is logged without prompts or keys."""
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import openai
from dotenv import load_dotenv

log = logging.getLogger("adbrain.llm")

REPO = Path(__file__).resolve().parents[2]
ENV_FILE = REPO / ".env"
USAGE_LOG = REPO / "data" / "cache" / "llm_usage.jsonl"
HTTP_PAYMENT_REQUIRED = 402
MAX_RETRIES = 1
Purpose = Literal["extraction", "phrasing"]

_budget_logged = False


class ConfigError(Exception):
    """A required .env key is missing or malformed."""


class LLMUnavailable(Exception):
    """The LLM could not give a usable answer. The message says why (never contains a key)."""


@dataclass(frozen=True)
class Settings:
    provider: str
    base_url: str
    api_key: str
    connect_timeout: float
    model: dict[str, str]
    total_timeout: dict[str, float]
    max_tokens: dict[str, int]
    demo_mode: bool


def _req(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is missing or empty in .env (see .env.example)")
    return value


def _num(name: str, kind: type) -> float | int:
    raw = _req(name)
    try:
        value = kind(raw)
    except ValueError as e:
        raise ConfigError(f"{name} must be a number") from e
    if value <= 0:
        raise ConfigError(f"{name} must be > 0")
    return value


def settings() -> Settings:
    load_dotenv(ENV_FILE)
    provider = os.environ.get("LLM_PROVIDER", "kva").strip() or "kva"
    if provider == "kva":
        base_url, api_key = _req("LLM_BASE_URL"), _req("AI_GATEWAY_API_KEY")
    elif provider == "openrouter":
        base_url, api_key = _req("OPENROUTER_BASE_URL"), _req("OPENROUTER_API_KEY")
    else:
        raise ConfigError("LLM_PROVIDER must be kva or openrouter")
    return Settings(
        provider=provider, base_url=base_url, api_key=api_key,
        connect_timeout=_num("LLM_CONNECT_TIMEOUT_SECONDS", float),
        model={"extraction": _req("LLM_MODEL_EXTRACTION"), "phrasing": _req("LLM_MODEL_PHRASING")},
        total_timeout={"extraction": _num("LLM_EXTRACTION_TOTAL_TIMEOUT_SECONDS", float),
                       "phrasing": _num("LLM_TOTAL_TIMEOUT_SECONDS", float)},
        max_tokens={"extraction": _num("LLM_EXTRACTION_MAX_TOKENS", int),
                    "phrasing": _num("LLM_PHRASING_MAX_TOKENS", int)},
        demo_mode=os.environ.get("DEMO_MODE", "true").strip().lower() == "true")


def demo_mode() -> bool:
    """DEMO_MODE=true (default): never call the LLM on the demo path. Needs no key."""
    load_dotenv(ENV_FILE)
    return os.environ.get("DEMO_MODE", "true").strip().lower() == "true"


def _log_usage(purpose: Purpose, model: str, usage: object, latency_ms: int, outcome: str,
               ref: str | None = None) -> None:
    row = {"at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "purpose": purpose, "model": model, "ref": ref,
           "prompt_tokens": getattr(usage, "prompt_tokens", None),
           "completion_tokens": getattr(usage, "completion_tokens", None),
           "total_tokens": getattr(usage, "total_tokens", None), "latency_ms": latency_ms, "outcome": outcome}
    try:
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        log.exception("could not write %s", USAGE_LOG.name)


def complete(purpose: Purpose, messages: list[dict[str, str]], s: Settings | None = None,
             ref: str | None = None) -> str:
    """One chat completion. Returns non-empty text or raises LLMUnavailable. `ref` (e.g. the AD id) is logged."""
    global _budget_logged
    s = s or settings()
    model = s.model[purpose]
    # ponytail: the SDK timeout bounds connect and each read, not wall-clock total; enough for non-streaming calls.
    client = openai.OpenAI(api_key=s.api_key, base_url=s.base_url, max_retries=MAX_RETRIES,
                           timeout=openai.Timeout(s.total_timeout[purpose], connect=s.connect_timeout))
    started = time.monotonic()
    try:
        r = client.chat.completions.create(model=model, messages=messages,  # type: ignore[arg-type]
                                           max_tokens=s.max_tokens[purpose], temperature=0)
    except openai.APIStatusError as e:
        ms = int((time.monotonic() - started) * 1000)
        _log_usage(purpose, model, None, ms, f"http_{e.status_code}", ref)
        if e.status_code == HTTP_PAYMENT_REQUIRED:
            if not _budget_logged:
                log.error("LLM budget used up (HTTP 402): falling back to cache/template")
                _budget_logged = True
            raise LLMUnavailable("budget used up (HTTP 402)") from e
        raise LLMUnavailable(f"HTTP {e.status_code} from the LLM endpoint") from e
    except (openai.APITimeoutError, openai.APIConnectionError) as e:
        _log_usage(purpose, model, None, int((time.monotonic() - started) * 1000), type(e).__name__, ref)
        raise LLMUnavailable(f"{type(e).__name__} (connect {s.connect_timeout}s, total {s.total_timeout[purpose]}s)") from e
    ms = int((time.monotonic() - started) * 1000)
    choice = r.choices[0] if r.choices else None
    text = (choice.message.content or "") if choice else ""
    if choice is not None and choice.finish_reason == "length":
        _log_usage(purpose, model, r.usage, ms, "truncated", ref)
        raise LLMUnavailable(f"response truncated at max_tokens={s.max_tokens[purpose]}")
    if not text.strip():
        _log_usage(purpose, model, r.usage, ms, "empty", ref)
        raise LLMUnavailable("empty response")
    _log_usage(purpose, model, r.usage, ms, "ok", ref)
    return text
