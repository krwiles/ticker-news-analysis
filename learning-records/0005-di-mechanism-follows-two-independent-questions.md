# Generalized DI mechanism choice into two independent questions, not one class-vs-function axis

Building on `0002-prior-dependency-injection-background.md`: when asked why this codebase injects
dependencies as plain function parameters instead of Java/Spring-style constructor injection, the user's
first-pass generalization was "does this workflow need state and a long lifespan (→ class, constructor
injection) or is it simple enough to be a function (→ parameter injection)." Correct instinct, but it
bundled two separate decisions into one axis. Walked through with a counter-example already in the repo
(`db.py`'s module-level `engine`/`async_session_factory` — genuinely stateful and long-lived, but a plain
singleton created at import time, never wrapped in a class or constructor-injected anywhere) to split it
into the two questions that actually govern this codebase's choices independently:

1. Does the *dependency itself* need to be created once and persist, or manufactured fresh per use? —
   decides singleton-via-module-import (`engine`) vs. factory-called-per-use (`async_session_factory()`
   producing a new `AsyncSession`). Orthogonal to class-vs-function.
2. Who controls the *call site* of the thing consuming the dependency — a framework (FastAPI dispatching a
   route, which can introspect the signature and supports `Depends()` + `dependency_overrides` for tests),
   or your own code calling your own function directly (`providers.py`, called straight from `worker.py`
   and from tests, where a default parameter is the only "injection" available since there's no framework
   in the loop to introspect anything)?

**Implication for future teaching**: this user reliably reasons in generalizable heuristics rather than
memorizing examples (see also `0004`'s async-scheduling synthesis) — the productive move is to let a
first-pass generalization stand, then hand back one real counter-example from the actual codebase rather
than a hypothetical, and let them re-derive the refinement themselves. Future DI/architecture questions can
build on "singleton-vs-per-use" and "framework-controlled-vs-your-own call site" as the two settled axes
without re-deriving them — including why `providers.py` stays framework-agnostic by design (its own module
docstring already says so) rather than adopting FastAPI's `Depends()` even though it could.
