# Prior knowledge: real dependency-injection experience from Java and Angular

The user pushed back precisely on `db.py`'s module-level `engine`/`async_session_factory` pattern, asking
whether it should instead be "injected" the way DI containers (Java/Spring-style, and Angular's `inject()`)
would do it — correctly distinguishing "shared singleton via language import mechanics" from "framework-managed
dependency injection" as two different things, not the same thing under different names.

**Implication for future teaching**: DI as a *concept* doesn't need to be taught from scratch — only how it
maps onto Python/FastAPI idioms. This has already started (FastAPI's `Depends()` for request-scoped
dependencies; manual injection-via-default-parameter for non-FastAPI contexts like ARQ jobs, applied to
`fetch_and_persist_headlines`'s `session_factory` parameter in the lesson 7 plan). Future lessons touching
DI-adjacent topics should lead with "here's the Python/FastAPI equivalent of what you already know," the same
translation-table approach already used for Angular→React, rather than re-deriving DI motivation from zero.
