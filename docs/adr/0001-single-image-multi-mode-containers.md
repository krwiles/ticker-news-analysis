# Single image, multiple runtime modes

The walking-skeleton architecture needs a UI, an API, and a background worker. Rather than three separate images, all three run from one multi-stage Dockerfile — a Node stage builds the React app, a Python stage carries the FastAPI/ARQ code and copies the built static assets in — and a mode flag at container start picks which of `ui`, `api`, or `worker` that container becomes. This mirrors the pattern NVIDIA's team uses (a single deployable that can be initialized as UI, API, or CLI) and keeps the build/CI surface to one image instead of two or three.

## Considered options

- **Separate UI and API/worker images** (a Node/nginx image for the React build, a Python image for API + worker): cleaner separation of runtimes, smaller individual images, but two Dockerfiles/build pipelines/version tags to keep in sync instead of one.
- **Single image, mode-switched at startup** (chosen): one Dockerfile, one image tag, one CI build step. `ui` mode serves the prebuilt React static files through FastAPI (with an SPA catch-all route for React Router); `api` mode runs the JSON API via uvicorn; `worker` mode runs the ARQ worker entrypoint.

## Consequences

- The `ui` container carries a full Python runtime it doesn't strictly need, and the image is larger than a bare nginx-static image would be — accepted in exchange for one build pipeline and matching the target architecture pattern this project exists to learn.
- Every mode shares one dependency set and one version; there's no risk of the UI and API drifting to different image tags.
- A future split into separate images (if the shared-image trade-off stops paying for itself) means separating the Dockerfile into stages that produce distinct final images — a real but bounded refactor, not a rewrite.
