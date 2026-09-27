import { API_BASE_URL } from "./config";

// Mirrors auth.py's _user_to_dict field-for-field -- kept in sync by hand, no shared schema.
export interface AuthUser {
  email: string | null;
  name: string | null;
  picture_url: string | null;
}

export interface MeResponse {
  user: AuthUser | null;
}

// credentials: "include" on every call here -- ui/api are different origins (ADR 0002/0016),
// so the session cookie never travels on a fetch that doesn't opt in explicitly.
export async function fetchMe(): Promise<MeResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/me`, { credentials: "include" });
  if (!res.ok) {
    throw new Error(`/api/auth/me responded ${res.status}`);
  }
  return res.json();
}

// credential is the signed ID token (JWT) GIS's own button callback hands the frontend --
// see auth.py for what happens to it server-side.
export async function signInWithGoogle(credential: string): Promise<AuthUser> {
  const res = await fetch(`${API_BASE_URL}/api/auth/google`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credential }),
  });
  if (!res.ok) {
    throw new Error(`/api/auth/google responded ${res.status}`);
  }
  return res.json();
}

export async function signOut(): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/auth/logout`, { method: "POST", credentials: "include" });
  if (!res.ok) {
    throw new Error(`/api/auth/logout responded ${res.status}`);
  }
}
