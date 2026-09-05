import { useState, type FormEvent } from "react";
import { HeartPulse } from "lucide-react";
import { useAuth } from "@/context/auth";
import { Button, Card, Field } from "@/components/exports";
import { ApiError } from "@/lib/api";

const DEMO = [
  { label: "Clinician", email: "dr.chowdhury@example.com" },
  { label: "Patient", email: "rina@example.com" },
];
const DEMO_PASSWORD = "demo-password-123";

export function Login() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, fullName);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function demo(demoEmail: string) {
    setError(null);
    setBusy(true);
    try {
      await login(demoEmail, DEMO_PASSWORD);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Demo sign-in failed.");
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center px-4 py-12">
      <div className="w-full max-w-[380px]">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-[14px] bg-accent-500 text-white shadow-[0_2px_10px_rgba(31,99,87,.30)]">
            <HeartPulse size={24} strokeWidth={2.2} />
          </div>
          <h1 className="font-serif text-[26px] leading-tight tracking-[-0.015em] text-ink">
            Cardiac Rehab
          </h1>
          <p className="mt-2 text-[14px] leading-relaxed text-ink-muted">
            Remote monitoring and support through phase&nbsp;II recovery
          </p>
        </div>

        <Card className="p-6">
          <form onSubmit={submit} className="space-y-4">
            {mode === "register" && (
              <Field label="Full name" value={fullName} required
                onChange={(e) => setFullName(e.target.value)} placeholder="Your name" />
            )}
            <Field label="Email" type="email" value={email} required autoComplete="email"
              onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
            <Field label="Password" type="password" value={password} required
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              onChange={(e) => setPassword(e.target.value)}
              hint={mode === "register" ? "At least 8 characters" : undefined} />

            {error && (
              <p role="alert" className="rounded-[10px] bg-severe-bg px-3 py-2.5 text-[13px] text-severe-fg">
                {error}
              </p>
            )}

            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>

          <button type="button"
            onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}
            className="mt-4 w-full text-center text-[13px] text-ink-muted transition-colors hover:text-ink">
            {mode === "login" ? "New patient? Create an account" : "Already registered? Sign in"}
          </button>
        </Card>

        {mode === "login" && (
          <div className="mt-6">
            <p className="mb-2.5 text-center text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-faint">
              Explore the demo
            </p>
            <div className="flex gap-2">
              {DEMO.map((d) => (
                <Button key={d.email} variant="secondary" size="sm" className="flex-1"
                  disabled={busy} onClick={() => void demo(d.email)}>
                  {d.label}
                </Button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
