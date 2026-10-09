"""Run every provider in parallel on the same input and log each call."""
from __future__ import annotations

import asyncio

from dotenv import load_dotenv

from .calllog import log_call
from .providers import DecisionProvider, default_providers
from .schemas import ProviderResult, Question

load_dotenv()


async def run_all(app: str, state, questions: list[Question],
                  providers: list[DecisionProvider] | None = None) -> list[ProviderResult]:
    providers = providers or default_providers()
    results = await asyncio.gather(*(p.decide(state, questions) for p in providers))
    for r in results:
        log_call(app, state, r)
    return list(results)
