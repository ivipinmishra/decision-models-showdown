"""Verify your API keys with one tiny live call per provider.

    python check_keys.py

Each call asks a single yes/no question about a one-line input (a fraction of a cent).
Providers without a key are reported as MOCK and not called.
"""
import asyncio

import common.runner  # noqa: F401  (importing it loads .env)
from common.providers import default_providers
from common.schemas import Question

QUESTION = [Question("is_greeting", "predicate", "The text is a greeting.")]


async def main() -> int:
    failures = 0
    for p in default_providers():
        if p.mock:
            print(f"  {p.name:<9} MOCK   no {p.api_key_env} found in environment or .env")
            continue
        r = await p.decide("Hello there!", QUESTION)
        if r.error or "is_greeting" not in r.answers:
            failures += 1
            print(f"  {p.name:<9} FAIL   {r.error or 'no answer returned'}")
        else:
            a = r.answers["is_greeting"]
            print(f"  {p.name:<9} OK     model={r.model}  P(greeting)={a.value:.2f}  {r.latency_ms:.0f} ms")
    return failures


if __name__ == "__main__":
    print("Checking API keys...")
    raise SystemExit(asyncio.run(main()))
