// The api container's origin -- hardcoded since this only ever runs via docker-compose
// or the local dev server, both fixed at localhost:8000. Revisit if this ever deploys for real.
export const API_BASE_URL = "http://localhost:8000";

// Not a secret -- designed to be embedded in shipped frontend code (ADR 0016), same
// hardcoding reasoning as API_BASE_URL above (no build-time env-var injection exists here).
export const GOOGLE_CLIENT_ID = "1041012467949-khp62q6loovp6a0paorbmgupqu75hd4t.apps.googleusercontent.com";
