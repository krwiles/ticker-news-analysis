// The api container's origin. Hardcoded because this project only ever runs
// against docker-compose's fixed port mapping (see docker-compose.yml) or the
// webpack dev server on the same host — both put the api at localhost:8000.
// Revisit this (env-driven, e.g. via webpack DefinePlugin) if this project
// ever targets a real deployment beyond local dev.
export const API_BASE_URL = "http://localhost:8000";
