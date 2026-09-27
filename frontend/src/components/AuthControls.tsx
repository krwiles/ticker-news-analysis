import { useEffect, useRef, useState } from "react";
import { fetchMe, signInWithGoogle, signOut, type AuthUser } from "../auth";
import { GOOGLE_CLIENT_ID } from "../config";

// The slice of GIS's global `window.google.accounts.id` API this component actually calls --
// GIS ships no official types, so this is hand-declared rather than pulling in a full package.
interface GoogleAccountsId {
  initialize(config: { client_id: string; callback: (response: { credential: string }) => void }): void;
  renderButton(parent: HTMLElement, options: { theme: string; size: string }): void;
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleAccountsId } };
  }
}

export function AuthControls() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loaded, setLoaded] = useState(false);
  const buttonRef = useRef<HTMLDivElement>(null);

  // Establishes initial signed-in/signed-out state -- the cookie is HttpOnly, so a real
  // request is the only way the frontend can know (spec 0006, ADR 0016).
  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((res) => {
        if (!cancelled) setUser(res.user);
      })
      .catch(() => {
        // A failed check is treated the same as signed-out, never a broken page (spec 0006).
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Renders GIS's own button once the initial check resolves signed-out -- its script tag
  // (index.html) loads independently of React, so it simply doesn't render if not ready yet.
  useEffect(() => {
    if (loaded && user === null && buttonRef.current && window.google) {
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: async (response) => {
          // GIS hands back a signed credential directly (ADR 0016) -- POST it, then re-fetch
          // /api/auth/me as the one source of truth rather than trusting this response.
          await signInWithGoogle(response.credential);
          const me = await fetchMe();
          setUser(me.user);
        },
      });
      window.google.accounts.id.renderButton(buttonRef.current, { theme: "outline", size: "medium" });
    }
  }, [loaded, user]);

  async function handleSignOut() {
    await signOut();
    setUser(null);
  }

  // Nothing renders until the initial check resolves -- avoids a signed-out flash for an
  // actually-signed-in user, since this shows on every page (spec 0006).
  if (!loaded) {
    return null;
  }

  if (user) {
    return (
      <div className="flex items-center gap-3">
        {user.picture_url && (
          <img src={user.picture_url} alt="" referrerPolicy="no-referrer" className="h-8 w-8 rounded-full" />
        )}
        <span className="text-sm font-medium text-slate-700">{user.name}</span>
        <button
          onClick={handleSignOut}
          className="rounded border border-slate-300 px-2 py-1 text-sm text-slate-600 hover:bg-slate-50"
        >
          Sign out
        </button>
      </div>
    );
  }

  return <div ref={buttonRef} />;
}
