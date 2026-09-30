import { useEffect, useRef } from "react";
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

interface AuthControlsProps {
  // Lifted up to Layout (ADR 0019) -- the watchlist sidebar needs this same state, so this
  // component no longer fetches or stores it itself.
  user: AuthUser | null;
  onSignedIn: (user: AuthUser) => void;
  onSignedOut: () => void;
}

export function AuthControls({ user, onSignedIn, onSignedOut }: AuthControlsProps) {
  const buttonRef = useRef<HTMLDivElement>(null);

  // Renders GIS's own button whenever signed out -- its script tag (index.html) loads
  // independently of React, so it simply doesn't render if not ready yet.
  useEffect(() => {
    if (user === null && buttonRef.current && window.google) {
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: async (response) => {
          // GIS hands back a signed credential directly (ADR 0016) -- POST it, then re-fetch
          // /api/auth/me as the one source of truth rather than trusting this response.
          await signInWithGoogle(response.credential);
          const me = await fetchMe();
          if (me.user) {
            onSignedIn(me.user);
          }
        },
      });
      window.google.accounts.id.renderButton(buttonRef.current, { theme: "outline", size: "medium" });
    }
  }, [user, onSignedIn]);

  async function handleSignOut() {
    await signOut();
    onSignedOut();
  }

  if (user) {
    // key differs from the signed-out div below -- without it, React patches this same-type
    // div in place instead of unmounting it, leaving GIS's own injected button behind.
    return (
      <div key="profile" className="flex items-center gap-3">
        {user.picture_url && (
          <img src={user.picture_url} alt="" referrerPolicy="no-referrer" className="h-8 w-8 rounded-full" />
        )}
        <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{user.name}</span>
        <button
          onClick={handleSignOut}
          className="rounded border border-slate-300 px-2 py-1 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Sign out
        </button>
      </div>
    );
  }

  return <div key="google-button" ref={buttonRef} />;
}
