import { useState, type FormEvent } from "react";
import { HeartPulse } from "lucide-react";
import { useAuth } from "@/context/auth";
import { Button, Card, Field } from "@/components/ui";
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

  return (
    <div className="flex min-h-full items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-7 flex flex-col items-center text-center">
          <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-accent-600 text-white">
            <HeartPulse size={22} strokeWidth={2.2} />
          </div>
          <h1 className="text-lg font-semibold tracking-tight text-ink-900">Cardiac Rehab Platform</h1>
          <p className="mt-1 text-[13px] text-ink-500">Remote monitoring for phase II recovery</p>
        </div>

        <Card className="p-5">
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
              <p role="alert" className="rounded-lg bg-severe-bg px-3 py-2 text-[13px] text-severe-fg">
                {error}
              </p>
            )}

            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>

          <button
            type="button"
            onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}
            className="mt-4 w-full text-center text-[13px] text-ink-500 hover:text-ink-800"
          >
            {mode === "login" ? "New patient? Create an account" : "Already registered? Sign in"}
          </button>
        </Card>

        {mode === "login" && (
          <div className="mt-5 rounded-xl border border-dashed border-ink-200 p-4">
            <p className="mb-2 text-[12px] font-medium uppercase tracking-wide text-ink-400">Demo accounts</p>
            <div className="flex gap-2">
              {DEMO.map((d) => (
                <Button key={d.email} variant="secondary" size="sm" className="flex-1"
                  onClick={() => { setEmail(d.email); setPassword(DEMO_PASSWORD); }}>
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
