"""Loading the product sheets, the rulebook and the sample calls from disk."""
from __future__ import annotations

from pathlib import Path

import yaml

from .models import Call, Fact, Label, Product, Turn

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_products(path: Path | None = None) -> dict[str, Product]:
    raw = yaml.safe_load((path or DATA / "products.yaml").read_text(encoding="utf-8"))["products"]
    return {pid: Product(id=pid, name=p["name"], facts=[Fact(**f) for f in p["facts"]]) for pid, p in raw.items()}


def load_rulebook(path: Path | None = None) -> dict:
    return yaml.safe_load((path or DATA / "rulebook.yaml").read_text(encoding="utf-8"))


def parse_turns(lines: list[str]) -> list[Turn]:
    out = []
    for ln in lines:
        tag, _, text = ln.partition(":")
        out.append(Turn(speaker="bot" if tag.strip().upper() == "B" else "customer", text=text.strip()))
    return out


def parse_labels(items: list[str]) -> list[Label]:
    out = []
    for it in items or []:
        t, _, cat = it.partition(":")
        out.append(Label(turn=None if t.strip() == "*" else int(t), category=cat.strip()))
    return out


def load_calls(path: Path | None = None) -> list[Call]:
    raw = yaml.safe_load((path or DATA / "calls.yaml").read_text(encoding="utf-8"))
    calls = []
    for c in raw:
        calls.append(Call(
            id=c["id"], title=c["title"], scenario=c["scenario"], product=c["product"], time=c.get("time"),
            turns=parse_turns(c["turns"]), labels=parse_labels(c.get("labels", [])),
            account_facts=[Fact(**f) for f in c.get("account_facts", [])],
        ))
    return calls
