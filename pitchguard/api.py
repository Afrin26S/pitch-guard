"""Live-guard HTTP API.   uvicorn pitchguard.api:app --reload

POST /check  {"product_id":"term_shield","scenario":"term_sales","text":"...", "deep":false}
  -> {"decision":"ALLOW|REWRITE|BLOCK", "violations":[...], "fast_lane_ms":0.05, ...}

A voice bot would call this between "LLM wrote the sentence" and "TTS speaks it".
deep=false is the fast lane only (regex, sub-millisecond). deep=true adds the Groq claim check.
"""
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .guard import Guard, GuardDecision
from .kb import load_products, load_rulebook
from .llm import get_llm

app = FastAPI(title="Pitch Guard", version="0.1.0")
_guard = Guard(load_products(), load_rulebook(), get_llm())


class CheckRequest(BaseModel):
    product_id: str = "term_shield"
    scenario: str = "term_sales"
    text: str
    context: list[str] = []
    deep: bool = False


@app.get("/health")
def health():
    return {"ok": True, "deep_lane_available": _guard.llm is not None}


@app.post("/check", response_model=GuardDecision)
def check(req: CheckRequest):
    if req.product_id not in _guard.products:
        raise HTTPException(404, f"unknown product_id {req.product_id!r}")
    return _guard.check_utterance(req.product_id, req.scenario, req.text, req.context, req.deep)
