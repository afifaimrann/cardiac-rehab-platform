import { useCallback, useEffect, useRef, useState } from "react";
import { Database, Send, Sparkles, Trash2 } from "lucide-react";
import { Button, EmptyState, Markdown, Spinner, TypingDots } from "@/components/exports";
import { api, ApiError } from "@/lib/api";
import type { AssistantTurn } from "@/lib/types";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "What has changed for this patient in the last two weeks?",
  "Is their walking distance improving?",
  "Summarise everything I should know before this consultation.",
  "Are they keeping to the exercise plan?",
];

/** Tool names as a clinician would say them. */
const TOOL_LABELS: Record<string, string> = {
  get_profile: "profile",
  get_vitals: "vitals",
  get_symptoms: "symptoms",
  get_risk_flags: "risk flags",
  get_walk_tests: "walk tests",
  get_exercise_adherence: "exercise log",
  get_appointments: "appointments",
};

/**
 * The clinician's assistant, scoped to one patient.
 *
 * It shows which parts of the record each answer came from. That line is not
 * decoration: an assistant that summarises a record is only useful if the
 * reader can tell whether it looked at the thing they care about, and
 * "answered without reading the walk tests" is exactly the failure that would
 * otherwise be invisible.
 */
export function AssistantPanel({ patientId, patientName }: {
  patientId: string; patientName: string;
}) {
  const [turns, setTurns] = useState<AssistantTurn[] | null>(null);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setTurns(await api.assistant.thread(patientId));
  }, [patientId]);

  useEffect(() => { setTurns(null); void load(); }, [load]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns?.length, thinking]);

  async function ask(question: string) {
    const text = question.trim();
    if (!text || thinking) return;
    setDraft("");
    setThinking(true);
    setError(null);
    try {
      await api.assistant.ask(patientId, text);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The assistant could not answer.");
    } finally {
      setThinking(false);
    }
  }

  async function clear() {
    await api.assistant.clear(patientId);
    await load();
  }

  return (
    <div className="flex h-[min(72vh,720px)] flex-col overflow-hidden rounded-[14px] border border-line bg-surface">
      <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-[14px] font-semibold text-ink">
            <Sparkles size={15} className="text-teal-500" /> Ask about {patientName}
          </p>
          <p className="mt-0.5 text-[12px] text-ink-muted">
            Reads this patient's record only. Not a second opinion — check anything you act on.
          </p>
        </div>
        {turns && turns.length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => void clear()}>
            <Trash2 size={14} /> Clear
          </Button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-5">
        {turns === null ? <Spinner /> : turns.length === 0 ? (
          <div className="mx-auto max-w-[440px]">
            <EmptyState
              icon={<Sparkles size={22} />}
              title="Ask a question about this record"
              hint="The assistant reads the vitals, symptoms, flags, walk tests, exercise log and appointments for this patient."
            />
            <div className="mt-4 space-y-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void ask(s)}
                  className="w-full rounded-[10px] border border-line bg-surface-sunk/40 px-3.5 py-2.5 text-start text-[13px] text-ink-soft transition-colors duration-150 hover:border-teal-400 hover:bg-teal-50 hover:text-teal-500"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <ul className="space-y-5">
            {turns.map((t) => (
              <li key={t.id} className={cn(t.role === "user" && "flex justify-end")}>
                {t.role === "user" ? (
                  <p className="max-w-[80%] rounded-[14px] bg-teal-500 px-4 py-2.5 text-[14px] leading-relaxed text-white">
                    {t.content}
                  </p>
                ) : (
                  <div className="max-w-[92%]">
                    <div className="prose-sm text-[14px] leading-relaxed text-ink">
                      <Markdown>{t.content}</Markdown>
                    </div>
                    {t.tools_used && (
                      <p className="mt-2 flex flex-wrap items-center gap-1.5 text-[11.5px] text-ink-faint">
                        <Database size={11} />
                        Read:
                        {t.tools_used.split(", ").map((tool) => (
                          <span key={tool} className="rounded bg-surface-sunk px-1.5 py-0.5">
                            {TOOL_LABELS[tool] ?? tool}
                          </span>
                        ))}
                      </p>
                    )}
                  </div>
                )}
              </li>
            ))}
            {thinking && <li><TypingDots /></li>}
          </ul>
        )}
        <div ref={bottom} />
      </div>

      <div className="border-t border-line px-5 py-3.5">
        {error && <p role="alert" className="mb-2 text-[12.5px] text-severe-fg">{error}</p>}
        <div className="flex items-end gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void ask(draft); }
            }}
            rows={1}
            maxLength={2000}
            placeholder="Ask about this patient's record…"
            className="max-h-32 min-h-[44px] flex-1 resize-y rounded-[11px] border border-line-strong bg-surface px-3.5 py-2.5 text-sm leading-relaxed text-ink placeholder:text-ink-faint focus:border-teal-400 focus:outline-none focus:ring-4 focus:ring-teal-400/12"
          />
          <Button onClick={() => void ask(draft)} disabled={thinking || !draft.trim()} className="h-[44px]">
            <Send size={15} />
          </Button>
        </div>
      </div>
    </div>
  );
}
