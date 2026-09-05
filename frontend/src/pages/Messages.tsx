import { useCallback, useEffect, useRef, useState } from "react";
import { Info, Send } from "lucide-react";
import { CONTENT, PageHeader } from "@/components/AppShell";
import { Avatar, Button, EmptyState, Spinner } from "@/components/exports";
import { useAuth } from "@/context/auth";
import { api, ApiError } from "@/lib/api";
import type { DirectMessage, MessageThread } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

/**
 * The thread between a patient and their care team.
 *
 * Kept visually distinct from the AI assistant on purpose. A patient who
 * cannot tell which of the two they are writing to will either wait days for
 * an answer a model could have given instantly, or send something urgent to
 * software. The banner, the avatars and the reply latency notice all exist to
 * make the difference obvious.
 */
export function MessagesPage({ patientId, embedded }: {
  patientId?: string;
  /** Rendered inside the patient record's tab strip, which already shows who
   *  this is. A second page header under the first reads as two pages stacked. */
  embedded?: boolean;
}) {
  const { user } = useAuth();
  const [thread, setThread] = useState<MessageThread | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    const data = patientId
      ? await api.messages.patientThread(patientId)
      : await api.messages.thread();
    setThread(data);
  }, [patientId]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [thread?.messages.length]);

  async function send() {
    const body = draft.trim();
    if (!body) return;
    setSending(true);
    setError(null);
    try {
      if (patientId) await api.messages.replyTo(patientId, body);
      else await api.messages.send(body);
      setDraft("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send that message.");
    } finally {
      setSending(false);
    }
  }

  const asClinician = Boolean(patientId);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {!embedded && (
        <PageHeader
          title={asClinician ? "Messages" : "Your care team"}
          subtitle={thread?.counterparty_name ? `With ${thread.counterparty_name}` : undefined}
        />
      )}

      {!asClinician && (
        <div className="border-b border-line bg-mild-bg/40">
          <p className={`${CONTENT} flex items-start gap-2 py-2.5 text-[12.5px] leading-relaxed text-ink-soft`}>
            <Info size={14} className="mt-0.5 shrink-0 text-ink-muted" />
            A person reads these, so a reply can take a day or two. For something
            urgent, call your rehabilitation team. For a quick question about
            your recovery, the assistant answers straight away.
          </p>
        </div>
      )}

      <div className="flex-1 overflow-y-auto py-6">
        <div className={`${CONTENT} max-w-[760px]`}>
          {thread === null ? <Spinner /> : thread.messages.length === 0 ? (
            <EmptyState
              icon={<Send size={22} />}
              title={asClinician ? "No messages yet" : "No messages yet"}
              hint={asClinician
                ? "Nothing from this patient so far. You can start the thread."
                : "Write to your nurse or physiotherapist about anything that does not need an appointment — a change you have noticed, a question about your plan."}
            />
          ) : (
            <ul className="space-y-4">
              {thread.messages.map((m) => (
                <Bubble key={m.id} message={m} mine={m.sender_id === user?.id} />
              ))}
            </ul>
          )}
          <div ref={bottom} />
        </div>
      </div>

      <div className="border-t border-line bg-surface/60">
        <div className={`${CONTENT} max-w-[760px] py-4`}>
          {error && (
            <p role="alert" className="mb-2 text-[12.5px] text-severe-fg">{error}</p>
          )}
          <div className="flex items-end gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void send(); }
              }}
              rows={2}
              maxLength={4000}
              placeholder={asClinician ? "Reply to your patient…" : "Write to your care team…"}
              className="max-h-40 min-h-[52px] flex-1 resize-y rounded-[12px] border border-line-strong bg-surface px-3.5 py-2.5 text-sm leading-relaxed text-ink placeholder:text-ink-faint focus:border-accent-400 focus:outline-none focus:ring-4 focus:ring-accent-400/12"
            />
            <Button onClick={() => void send()} disabled={sending || !draft.trim()} className="h-[52px]">
              <Send size={16} /> Send
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Bubble({ message, mine }: { message: DirectMessage; mine: boolean }) {
  return (
    <li className={cn("flex items-end gap-2.5", mine && "flex-row-reverse")}>
      <Avatar name={message.sender_name} size={30} className="mb-0.5" />
      <div className={cn("max-w-[76%]", mine && "text-end")}>
        <div className={cn(
          "inline-block rounded-[14px] px-4 py-2.5 text-start text-[14px] leading-relaxed",
          mine
            ? "bg-accent-500 text-white"
            : "border border-line bg-surface text-ink",
        )}>
          {message.body}
        </div>
        <p className="mt-1 text-[11.5px] text-ink-faint">
          {mine ? "You" : message.sender_name}
          {" · "}
          {formatDateTime(message.sent_at)}
          {mine && message.read_at && " · read"}
        </p>
      </div>
    </li>
  );
}
