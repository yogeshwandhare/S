import { type FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useCurrentUser, useLogin } from "@/hooks/useAuth";
import { ApiError } from "@/lib/api";

export function LoginPage() {
  const { data: user, isLoading: userLoading } = useCurrentUser();
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!userLoading && user) {
    return <Navigate to="/" replace />;
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    login.mutate(
      { email, password },
      {
        onError: (err) => {
          setError(err instanceof ApiError ? err.message : "Login failed");
        },
      },
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-2 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg border border-border bg-surface text-teal">
            <ShieldAlert className="h-5 w-5" />
          </div>
          <h1 className="text-lg font-semibold text-text">SmartVision</h1>
          <p className="text-sm text-text-muted">Public-safety operations console</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="glass-panel space-y-4 rounded-lg p-6"
        >
          <div className="space-y-1.5">
            <label htmlFor="email" className="text-xs font-medium text-text-muted">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-border-strong bg-surface-raised px-3 py-2 text-sm text-text outline-none focus-visible:border-cyan"
              placeholder="you@example.com"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="password" className="text-xs font-medium text-text-muted">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-border-strong bg-surface-raised px-3 py-2 text-sm text-text outline-none focus-visible:border-cyan"
              placeholder="••••••••••"
            />
          </div>

          {error && (
            <p role="alert" className="text-sm text-severity-critical">
              {error}
            </p>
          )}

          <Button type="submit" className="w-full" disabled={login.isPending}>
            {login.isPending ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="mt-4 text-center text-xs text-text-faint">
          This is a decision-support prototype, not a certified emergency-response
          system.
        </p>
      </div>
    </div>
  );
}
