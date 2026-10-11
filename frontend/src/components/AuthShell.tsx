import type { ReactNode } from "react";

// Feature 010: the centred card used by the sign-in, accept-invitation, reset-password and
// forbidden pages, in the app's dark-gold theme (FR-011). Pages put their own <form> inside.
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background text-foreground p-4">
      <div className="w-full max-w-sm rounded-2xl border border-border bg-card p-6 shadow-xl">
        {children}
      </div>
    </div>
  );
}
