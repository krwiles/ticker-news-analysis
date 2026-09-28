# ticker-news-analysis Stack Resources

## Knowledge

- [FastAPI docs](https://fastapi.tiangolo.com/)
  Official docs for the API/UI/worker framework. Use for: path operations, routers, dependency injection, `StaticFiles`.
- [FastAPI `app.frontend()`](https://fastapi.tiangolo.com/tutorial/static-files/) (shipped v0.138, June 2026)
  First-class SPA-serving helper — what `ui` mode uses instead of a hand-rolled `StaticFiles(html=True)` mount. New enough that some tutorial pages online still show the old pattern; the installed package's own docstring (`app.frontend.__doc__`) is the most current source if the site lags. Use for: how `ui` mode serves the React build.
- [SQLAlchemy 2.0 async ORM docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
  Official docs for the async engine/session pattern the health check and future data model use. Use for: models, sessions, migrations-adjacent patterns.
- [ARQ docs](https://arq-docs.helpmanual.io/) / [ARQ source](https://github.com/python-arq/arq)
  Official docs for the worker/job-queue library. Use for: `cron`, `WorkerSettings`, `ctx["redis"]`, job functions.
- [pydantic-settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
  Official docs for `config.py`'s `Settings` class. Use for: env-var-driven config, `.env` loading.
- [structlog docs](https://www.structlog.org/)
  Official docs for the structured logging setup in `logging.py`.
- [React docs](https://react.dev/) — especially [Thinking in React](https://react.dev/learn/thinking-in-react) and the [hooks reference](https://react.dev/reference/react)
  Official, current (function components + hooks, no class components). Use for: everything React.
- [React Router docs](https://reactrouter.com/) (v7, declarative mode)
  Official docs for the router used in `App.tsx`. Use for: routes, navigation, data loading (later).
- [Angular signals guide](https://angular.dev/guide/signals) and [Angular standalone components](https://angular.dev/guide/components/importing)
  Kept here as the *reference point*, not the target — used to translate Angular 21 concepts (signals, standalone components, `@if`/`@for`) into their nearest React equivalents.
- [Docker Compose docs](https://docs.docker.com/compose/)
  Official docs for `docker-compose.yml` — services, healthchecks, networking, the YAML anchor (`x-app`) trick used there.
- [Tailwind CSS v4 docs](https://tailwindcss.com/docs)
  Official docs, v4-specific (CSS-first config, no `tailwind.config.js` by default, the `@tailwindcss/webpack` loader).
- [Google Identity Services — Sign In With Google, HTML reference](https://developers.google.com/identity/gsi/web/reference/html-reference)
  Official docs for the frontend button/credential flow `auth.ts`/`AuthControls.tsx` are built against (Arc 7).
- [google-auth Python — verifying ID tokens](https://google-auth.readthedocs.io/en/master/reference/google.oauth2.id_token.html)
  Official docs for `verify_oauth2_token`, used in `auth.py`'s `_verify_google_credential` (ADR 0016). The
  installed package's own docstring was the source that caught both real exception types it can raise —
  worth checking directly rather than trusting a tutorial's simplified try/except.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
  The primary source for lessons 38-39: lifecycle (create/rotate/revoke/expire), least privilege, container injection, CI/CD hardening, and the revoke-rotate-clean-investigate incident order. Use for: the "why" behind every secrets decision in ADR 0017.
- [Docker Compose — use secrets](https://docs.docker.com/compose/how-tos/use-secrets/)
  Official docs for the top-level `secrets:` block and per-service grants; states the env-var exposure rationale directly. Use for: `docker-compose.yml`'s secrets wiring.
- [pydantic-settings — settings sources and secrets](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/)
  Source-priority order (env and dotenv outrank `secrets_dir`) and file-name-to-field mapping. The old `docs.pydantic.dev` URL 301-redirects here. Use for: `config.py`'s `secrets_dir`.
- [The Twelve-Factor App — Config](https://12factor.net/config)
  The "could you open-source it today?" litmus test for separating config from code. Use for: deciding secret vs. plain config.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
  Documents that Secrets are stored unencrypted in etcd by default. Use for: Phase 4 (Kubernetes) planning.
- [HashiCorp Vault — what is Vault](https://developer.hashicorp.com/vault/docs/what-is-vault) and [dynamic database credentials](https://developer.hashicorp.com/vault/docs/secrets/databases)
  Official docs for the deferred Phase 4 item. Use for: rungs 3-4 of lesson 38's ladder.

## Wisdom (Communities)

- [r/FastAPI](https://reddit.com/r/FastAPI)
  Use for: real-world FastAPI patterns and troubleshooting once past the basics.
- [r/reactjs](https://reddit.com/r/reactjs)
  Use for: React patterns/troubleshooting, well-moderated against low-effort content.
- No community preference stated yet — revisit once the learner has opinions on this.

## Gaps

- No single high-trust "React for Angular developers" resource was found — search results were mostly SEO comparison-farm content, not authoritative. The React-from-Angular translation in these lessons is built directly from the official React and Angular docs above rather than a secondary source. If a genuinely good primary comparison resource turns up later, add it here.
