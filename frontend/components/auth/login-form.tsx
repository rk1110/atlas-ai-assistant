"use client";

import { Compass, Loader2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

const DEMO_ACCOUNTS = [
  { email: "sam@acme.example", who: "Sam Okoye · engineer" },
  { email: "grace@acme.example", who: "Grace Liu · HR (sees salary bands)" },
  { email: "elena@acme.example", who: "Elena Petrova · Finance (sees the 2027 budget)" },
];

/**
 * The login form. On success the backend sets an httpOnly cookie; the refresh makes Server
 * Components render again, now with the session.
 */
export function LoginForm() {
  const next = safeNext(useSearchParams().get("next"));
  const [email, setEmail] = useState(DEMO_ACCOUNTS[0].email);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(email, password);
      router.replace(next);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't log in.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-4 rounded-2xl border bg-card p-6 shadow-sm">
      <div className="flex items-center gap-2">
        <span className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Compass className="size-5" aria-hidden />
        </span>
        <div>
          <h1 className="font-semibold">Log in to Atlas</h1>
          <p className="text-xs text-muted-foreground">Demo accounts for the fictional Acme Corp</p>
        </div>
      </div>
      <label className="flex flex-col gap-1.5 text-sm">
        Email
        <Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </label>
      <label className="flex flex-col gap-1.5 text-sm">
        Password
        <Input
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoFocus
        />
      </label>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" disabled={busy}>
        {busy && <Loader2 className="animate-spin" />} Log in
      </Button>
      <div className="flex flex-col gap-1 border-t pt-3 text-xs text-muted-foreground">
        <span>Accounts (the shared password is DEMO_PASSWORD in .env):</span>
        {DEMO_ACCOUNTS.map((a) => (
          <button
            key={a.email}
            type="button"
            onClick={() => setEmail(a.email)}
            className="cursor-pointer text-left hover:text-foreground"
          >
            <span className="font-medium">{a.email}</span> · {a.who}
          </button>
        ))}
      </div>
    </form>
  );
}

/** Only same-site paths: "?next=https://evil.example" must not become an open redirect. */
function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}
