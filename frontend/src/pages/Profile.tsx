import { useEffect, useRef, useState } from "react";
import { Camera, Check, Trash2, UserRound } from "lucide-react";
import { CONTENT, PageHeader } from "@/components/AppShell";
import { Avatar, Button, Card, CardHeader, Field, Spinner } from "@/components/exports";
import { useAuth } from "@/context/auth";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

const SEXES = [
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
  { value: "unspecified", label: "Prefer not to say" },
];

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "bn", label: "বাংলা" },
];

/**
 * Your own details.
 *
 * The two anthropometric fields are here rather than buried in the walk test
 * because they are stable facts about a person, not measurements taken on the
 * day. Asked once here, they make every future test produce a percent-predicted
 * without asking again — which is the whole reason the form explains what each
 * field is for.
 */
export function ProfilePage() {
  const { user, profile, refresh } = useAuth();
  const [form, setForm] = useState({
    full_name: "", date_of_birth: "", height_cm: "",
    sex_at_birth: "", language: "en", primary_condition: "",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const filePicker = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!user) return;
    setForm({
      full_name: user.full_name,
      date_of_birth: profile?.date_of_birth ?? "",
      height_cm: profile?.height_cm != null ? String(profile.height_cm) : "",
      sex_at_birth: profile?.sex_at_birth ?? "",
      language: profile?.language ?? "en",
      primary_condition: profile?.primary_condition ?? "",
    });
  }, [user, profile]);

  async function save() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      // Only what the person filled in. Sending "" for a date would be a
      // validation error, and sending unchanged values back would overwrite a
      // field a clinician had corrected in the meantime.
      const body: Record<string, unknown> = { full_name: form.full_name };
      if (profile) {
        if (form.date_of_birth) body.date_of_birth = form.date_of_birth;
        if (form.height_cm) body.height_cm = Number(form.height_cm);
        if (form.sex_at_birth) body.sex_at_birth = form.sex_at_birth;
        if (form.language) body.language = form.language;
        if (form.primary_condition) body.primary_condition = form.primary_condition;
      }
      await api.profile.update(body);
      await refresh();
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2400);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save your details.");
    } finally {
      setSaving(false);
    }
  }

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      await api.profile.uploadAvatar(file);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not upload that image.");
    } finally {
      setUploading(false);
      if (filePicker.current) filePicker.current.value = "";
    }
  }

  async function removePhoto() {
    setUploading(true);
    try {
      await api.profile.removeAvatar();
      await refresh();
    } finally {
      setUploading(false);
    }
  }

  if (!user) return <Spinner />;

  const missing = profile
    ? [
        !profile.date_of_birth && "date of birth",
        profile.height_cm == null && "height",
        !profile.sex_at_birth && "sex at birth",
      ].filter(Boolean) as string[]
    : [];

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageHeader title="Your profile" subtitle="What the platform knows about you" />

      <div className="flex-1 overflow-y-auto py-6">
        <div className={`${CONTENT} max-w-[720px] space-y-5`}>
          {error && (
            <p role="alert" className="rounded-[10px] bg-severe-bg px-4 py-3 text-[13px] text-severe-fg">
              {error}
            </p>
          )}

          <Card>
            <div className="flex flex-wrap items-center gap-5 px-5 py-5">
              <div className="relative">
                <Avatar name={user.full_name} src={user.avatar_url} size={84} />
                {uploading && (
                  <span className="absolute inset-0 flex items-center justify-center rounded-full bg-surface/70">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" />
                  </span>
                )}
              </div>
              <div className="min-w-0">
                <p className="text-[16px] font-semibold tracking-[-0.01em] text-ink">
                  {user.full_name}
                </p>
                <p className="mt-0.5 text-[13px] text-ink-muted">{user.email}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button variant="secondary" size="sm" disabled={uploading}
                    onClick={() => filePicker.current?.click()}>
                    <Camera size={14} /> {user.avatar_url ? "Change photo" : "Add a photo"}
                  </Button>
                  {user.avatar_url && (
                    <Button variant="ghost" size="sm" disabled={uploading}
                      onClick={() => void removePhoto()}>
                      <Trash2 size={14} /> Remove
                    </Button>
                  )}
                </div>
                <input
                  ref={filePicker}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void upload(file);
                  }}
                />
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Details"
              subtitle={profile
                ? "Height and sex at birth are used only to work out your predicted walking distance."
                : undefined}
            />
            <div className="space-y-4 px-5 py-5">
              <Field label="Full name" value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })} />

              {profile && (
                <>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Date of birth" type="date" value={form.date_of_birth}
                      onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} />
                    <Field label="Height (cm)" inputMode="decimal" value={form.height_cm}
                      placeholder="162"
                      onChange={(e) => setForm({ ...form, height_cm: e.target.value })} />
                  </div>

                  <Choice
                    label="Sex at birth"
                    hint="The predicted-distance equations are different for each, which is the only reason this is asked."
                    options={SEXES}
                    value={form.sex_at_birth}
                    onChange={(v) => setForm({ ...form, sex_at_birth: v })}
                  />

                  <Choice
                    label="Language"
                    hint="The assistant answers in the language you choose here."
                    options={LANGUAGES}
                    value={form.language}
                    onChange={(v) => setForm({ ...form, language: v })}
                  />

                  <Field label="Primary condition" value={form.primary_condition}
                    placeholder="e.g. after a heart attack"
                    onChange={(e) => setForm({ ...form, primary_condition: e.target.value })} />
                </>
              )}

              {missing.length > 0 && (
                <p className="flex items-start gap-2 rounded-[10px] bg-mild-bg px-4 py-3 text-[12.5px] leading-relaxed text-ink-soft">
                  <UserRound size={14} className="mt-0.5 shrink-0" />
                  Adding your {missing.join(", ")} lets every walk test show how your
                  distance compares with the expected distance for someone of your age
                  and build.
                </p>
              )}

              <div className="flex items-center gap-3 pt-1">
                <Button onClick={() => void save()} disabled={saving}>
                  {saving ? "Saving…" : "Save changes"}
                </Button>
                {saved && (
                  <span className="flex items-center gap-1.5 text-[13px] text-good-fg">
                    <Check size={15} /> Saved
                  </span>
                )}
              </div>
            </div>
          </Card>

          <div className="h-2" />
        </div>
      </div>
    </div>
  );
}

function Choice({ label, hint, options, value, onChange }: {
  label: string; hint?: string;
  options: { value: string; label: string }[];
  value: string; onChange: (v: string) => void;
}) {
  return (
    <div>
      <span className="mb-1.5 block text-[13px] font-medium text-ink-soft">{label}</span>
      <div className="flex flex-wrap gap-2">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            aria-pressed={value === o.value}
            className={cn(
              "h-9 rounded-[9px] border px-3.5 text-[13px] font-medium transition-colors duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/40",
              value === o.value
                ? "border-teal-400 bg-teal-50 text-teal-500"
                : "border-line-strong bg-surface text-ink-soft hover:border-ink-faint",
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
      {hint && <p className="mt-1.5 text-[12px] leading-relaxed text-ink-faint">{hint}</p>}
    </div>
  );
}
