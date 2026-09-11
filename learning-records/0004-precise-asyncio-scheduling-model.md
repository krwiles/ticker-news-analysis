# Demonstrated precise understanding of coroutine creation vs. event-loop scheduling

After lesson 8, the user correctly worked through, unprompted, a distinction the lesson itself didn't spell out
explicitly: that *creating* a coroutine (calling an `async def` function) is something application code does
constantly and implicitly, but *scheduling* a coroutine onto the event loop — the machinery that actually
drives it to completion — is owned entirely by the framework underneath (Uvicorn for HTTP routes, ARQ for
worker jobs), never called directly in this codebase. They asked the sharp, precise version of this ("are we
not explicitly creating and running coroutines here?") rather than a vaguer "how does async work" question,
and had already correctly reasoned through sequential-vs-`gather`'d await ordering and pseudocode execution
order beforehand in the same conversation, unprompted and correctly, before asking it.

**Implication for future teaching**: async/asyncio fundamentals don't need to be revisited from scratch in
later lessons — this sets a real, demonstrated floor above lesson 8's own content. Future ARQ/FastAPI work can
assume fluency with coroutine semantics, the event-loop-ownership question, and the difference between
"creating" and "scheduling" without re-explaining it, and can go straight to framework-specific mechanics
(e.g., how Uvicorn's worker model or Gunicorn process management actually schedules requests) if that ever
comes up.
