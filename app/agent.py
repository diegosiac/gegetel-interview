"""Benefits agent, grounded by construction.

The matcher only *selects* among the benefits the line is eligible for, and the answer text is
rendered from database rows. Even if the matcher were swapped for an LLM, its output would be
filtered against the eligible ids, so it cannot surface a benefit or code that does not apply.
"""

import re
import sqlite3
import unicodedata
from collections.abc import Sequence

from fastapi import APIRouter

from app.benefits import eligible_benefits, local_today, to_benefit_out
from app.deps import CurrentLine, Db, Now
from app.schemas import AgentAnswer, AgentQuestion

router = APIRouter(prefix="/me/agent", tags=["agent"])

NO_MATCH_MESSAGE = "No encontré beneficios de tu plan que coincidan con tu pregunta."

CATEGORY_KEYWORDS = {
    "Restaurantes": {"restaurante", "restaurantes", "comer", "comida", "cenar", "desayunar"},
    "Cine": {"cine", "pelicula", "peliculas"},
    "Gimnasio": {"gimnasio", "gym", "ejercicio", "entrenar"},
}

# Short words inside merchant names that must not trigger a match on their own.
STOPWORDS = {"la", "el", "los", "las", "de", "go"}


def normalize_words(text: str) -> set[str]:
    without_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()

    return set(re.findall(r"[a-z0-9]+", without_accents.lower()))


def select_benefits(question: str, eligible: Sequence[sqlite3.Row]) -> list[sqlite3.Row]:
    """Simulated LLM: merchant mention first, then category keywords."""
    words = normalize_words(question)

    by_merchant = [b for b in eligible if (normalize_words(b["merchant"]) - STOPWORDS) & words]
    if by_merchant:
        return by_merchant

    categories = {category for category, keywords in CATEGORY_KEYWORDS.items() if keywords & words}

    return [b for b in eligible if b["category"] in categories]


def ground(selected: Sequence[sqlite3.Row], eligible: Sequence[sqlite3.Row]) -> list[sqlite3.Row]:
    """Guardrail: whatever the matcher returns, keep only benefits the line is eligible for."""
    eligible_ids = {b["id"] for b in eligible}

    return [b for b in selected if b["id"] in eligible_ids]


def render_answer(benefits: Sequence[sqlite3.Row]) -> str:
    if not benefits:
        return NO_MATCH_MESSAGE
    items = "; ".join(f"{b['merchant']} ({b['category']}): {b['description']}" for b in benefits)

    return f"Con tu plan tienes: {items}. Canjéalos desde la sección de beneficios para obtener tu código."


@router.post("")
def ask_agent(payload: AgentQuestion, line: CurrentLine, db: Db, now: Now) -> AgentAnswer:
    eligible = eligible_benefits(db, line["plan"], local_today(now))
    benefits = ground(select_benefits(payload.question, eligible), eligible)

    return AgentAnswer(answer=render_answer(benefits), benefits=[to_benefit_out(b) for b in benefits])
