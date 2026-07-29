from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from pydantic import BaseModel

from .config import (DEFAULT_GEMINI_TEXT_MODEL, DEFAULT_LANGUAGE,
                     DEFAULT_TEXT_MODEL, REWRITE_USER_TEMPLATE,
                     build_rewrite_system_prompt)
from .models import Persona


class TextGenError(RuntimeError):
    pass


class StageRewrite(BaseModel):
    stage: int
    style: str
    rewrite: str


class RewriteSet(BaseModel):
    rewrites: list[StageRewrite]
    caption: str
    hashtags: list[str]


def _have_claude_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _have_google_key() -> bool:
    return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))


def resolve_text_backend(provider: str, model: str) -> tuple[str, str]:
    """Return (provider, model) actually used for text generation.

    provider: "auto" | "claude" | "gemini". In auto mode Claude is preferred
    when its key is present; otherwise Gemini. The model is swapped to the
    provider's default when it clearly belongs to the other provider.
    """
    if provider == "auto":
        if _have_claude_key():
            provider = "claude"
        elif _have_google_key():
            provider = "gemini"
        else:
            raise TextGenError(
                "No text API key found. Set at least one of:\n"
                "  ANTHROPIC_API_KEY   (Claude)\n"
                "  GOOGLE_API_KEY / GEMINI_API_KEY   (Gemini)\n"
                "in your environment or .env file.")
    if provider == "claude":
        if not _have_claude_key():
            raise TextGenError(
                "ANTHROPIC_API_KEY missing or invalid. Set it with:\n"
                "  $env:ANTHROPIC_API_KEY = 'sk-ant-...'\n"
                "or use --text-provider gemini to generate texts with the "
                "Google API instead.")
        if model.startswith("gemini"):
            model = DEFAULT_TEXT_MODEL
    elif provider == "gemini":
        if not _have_google_key():
            raise TextGenError(
                "GOOGLE_API_KEY / GEMINI_API_KEY not set (needed for Gemini "
                "text generation). Get a key at https://aistudio.google.com/apikey")
        if model.startswith("claude"):
            model = DEFAULT_GEMINI_TEXT_MODEL
    else:
        raise TextGenError(f"Unknown text provider '{provider}' "
                           "(expected auto, claude or gemini)")
    return provider, model


def _inputs_key(phrase: str, personas: list[Persona], model: str,
                language: str) -> str:
    payload = json.dumps(
        [phrase, model, language, build_rewrite_system_prompt(language)]
        + [[p.name, p.register] for p in personas],
        ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_user_prompt(phrase: str, personas: list[Persona]) -> str:
    stage_lines = "\n".join(
        f"{i + 1}. {p.name} — {p.register}" for i, p in enumerate(personas))
    return REWRITE_USER_TEMPLATE.format(phrase=phrase, stage_lines=stage_lines)


def _rewrites_via_claude(phrase: str, personas: list[Persona],
                         model: str, language: str) -> RewriteSet:
    import anthropic

    try:
        client = anthropic.Anthropic()
        response = client.messages.parse(
            model=model,
            max_tokens=2000,
            system=build_rewrite_system_prompt(language),
            messages=[{"role": "user",
                       "content": _build_user_prompt(phrase, personas)}],
            output_format=RewriteSet,
        )
    except anthropic.AuthenticationError as e:
        raise TextGenError(
            "ANTHROPIC_API_KEY missing or invalid. Set it with:\n"
            "  $env:ANTHROPIC_API_KEY = 'sk-ant-...'") from e
    except anthropic.APIStatusError as e:
        raise TextGenError(f"Claude API error ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise TextGenError("Could not reach the Claude API; check connectivity.") from e

    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise TextGenError("The model declined to generate rewrites for this phrase.")
    return response.parsed_output


def _rewrites_via_gemini(phrase: str, personas: list[Persona],
                         model: str, language: str) -> RewriteSet:
    from google import genai
    from google.genai import types

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model=model,
            contents=_build_user_prompt(phrase, personas),
            config=types.GenerateContentConfig(
                system_instruction=build_rewrite_system_prompt(language),
                response_mime_type="application/json",
                response_schema=RewriteSet,
            ),
        )
    except Exception as e:
        raise TextGenError(f"Gemini text API error: {e}") from e

    parsed = response.parsed
    if parsed is None:
        try:
            parsed = RewriteSet.model_validate_json(response.text or "")
        except Exception as e:
            raise TextGenError(
                "Gemini returned no parseable rewrites for this phrase.") from e
    return parsed


def _format_social(caption: str, hashtags: list[str]) -> str:
    tags = " ".join("#" + t.lstrip("#").replace(" ", "") for t in hashtags if t)
    return f"{caption.strip()}\n\n{tags}".strip()


def generate_rewrites(phrase: str, personas: list[Persona], model: str,
                      cache_dir: Path, provider: str = "auto",
                      language: str = DEFAULT_LANGUAGE) -> tuple[list[str], str]:
    """Return (one rewrite per persona, social caption+hashtags text).

    Cached in cache_dir/rewrites.json; a single API call produces both.
    """
    provider, model = resolve_text_backend(provider, model)

    cache_file = cache_dir / "rewrites.json"
    key = _inputs_key(phrase, personas, model, language)
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if cached.get("key") == key:
                return cached["rewrites"], cached.get("social", "")
        except (json.JSONDecodeError, KeyError):
            pass

    if provider == "claude":
        result = _rewrites_via_claude(phrase, personas, model, language)
    else:
        result = _rewrites_via_gemini(phrase, personas, model, language)

    by_stage = {r.stage: r.rewrite for r in result.rewrites}
    if sorted(by_stage) != list(range(1, len(personas) + 1)):
        raise TextGenError(
            f"Expected rewrites for stages 1..{len(personas)}, got {sorted(by_stage)}")
    rewrites = [by_stage[i] for i in range(1, len(personas) + 1)]
    if personas[0].level <= 1:
        # Level 1 is reality: the exact original phrase, never a rewrite.
        rewrites[0] = phrase.strip()
    social = _format_social(result.caption, result.hashtags)

    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(
        {"key": key, "phrase": phrase,
         "personas": [p.name for p in personas],
         "provider": provider, "model": model, "language": language,
         "rewrites": rewrites, "social": social},
        ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(cache_file)
    return rewrites, social
