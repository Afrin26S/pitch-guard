"""Thin Groq client (OpenAI-compatible endpoint) with retries and an on-disk cache.

Why a cache? Same prompt -> same answer, so re-running the evaluation is free and deterministic,
the demo never burns your quota twice, and a recruiter's click never needs your key.

IMPORTANT: Groq retires models. `llama-3.3-70b-versatile` was shut down on 16 Aug 2026. The model
name is therefore an environment variable (PITCHGUARD_MODEL), never hard-coded in logic.
Check https://console.groq.com/docs/models if you ever see a "model not found" error.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests

DEFAULT_MODEL = "openai/gpt-oss-120b"
URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(RuntimeError):
    pass


def loads_json(text: str) -> dict:
    """Parse a model reply as JSON, tolerating code fences and stray prose around the object."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise LLMError(f"Model did not return JSON: {text[:200]!r}")


class GroqLLM:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, cache_dir: str | Path = ".cache/llm", timeout: int = 60):
        self.api_key, self.model, self.timeout = api_key, model, timeout
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.calls = 0
        self.cache_hits = 0

    def complete_json(self, system: str, user: str, max_tokens: int = 1200) -> dict:
        key = hashlib.sha256(json.dumps([self.model, system, user, max_tokens], ensure_ascii=False).encode()).hexdigest()
        f = self.cache_dir / f"{key}.json"
        if f.exists():
            self.cache_hits += 1
            return json.loads(f.read_text(encoding="utf-8"))

        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_completion_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"        # we need speed, not long chains of thought
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        for attempt in range(7):
            try:
                r = requests.post(URL, headers=headers, json=body, timeout=self.timeout)
            except requests.RequestException as e:
                time.sleep(min(2 ** attempt, 30))
                if attempt == 6:
                    raise LLMError(f"Network error talking to Groq: {e}") from e
                continue
            if r.status_code == 200:
                self.calls += 1
                content = r.json()["choices"][0]["message"].get("content") or ""
                data = loads_json(content)
                f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return data
            if r.status_code == 401:
                raise LLMError("Groq rejected the API key (401). Check GROQ_API_KEY.")
            if r.status_code in (404,) or "model" in r.text.lower() and "not found" in r.text.lower():
                raise LLMError(f"Model {self.model!r} not available. See https://console.groq.com/docs/models and set PITCHGUARD_MODEL. ({r.text[:200]})")
            if r.status_code == 400:
                low = r.text.lower()
                if "reasoning" in low and "reasoning_effort" in body:
                    body.pop("reasoning_effort"); continue
                if "response_format" in low and "response_format" in body:
                    body.pop("response_format"); continue
                raise LLMError(f"Groq 400: {r.text[:300]}")
            if r.status_code == 429 or r.status_code >= 500:           # rate limit / transient error
                wait = float(r.headers.get("retry-after") or min(2 ** attempt, 30))
                time.sleep(min(wait, 60))
                continue
            raise LLMError(f"Groq error {r.status_code}: {r.text[:300]}")
        raise LLMError("Groq kept rate-limiting; try again in a minute (or lower the request rate).")


def get_llm():
    """Return a GroqLLM if GROQ_API_KEY is set (env var, or Streamlit secrets), else None."""
    key = os.getenv("GROQ_API_KEY")
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get("GROQ_API_KEY")
        except Exception:
            key = None
    if not key:
        return None
    return GroqLLM(key, os.getenv("PITCHGUARD_MODEL", DEFAULT_MODEL))
