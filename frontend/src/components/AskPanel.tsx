import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { AlertTriangle, BookOpen, Mic, Plus, Send, Square } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { ChatMessage, Conversation } from "@/lib/types";
import { Button, Markdown, Spinner, TypingDots } from "@/components/exports";
import { cn, relativeTime } from "@/lib/utils";

const SUGGESTIONS = [
  "আমি কি হাঁটতে পারব?",
  "ওষুধ খেতে ভুলে গেছি",
  "How hard should I be exercising?",
  "When can I go back to work?",
];

export function AskPanel() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [voiceDisabled, setVoiceDisabled] = useState(false);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const endRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    void (async () => {
      const existing = await api.chat.conversations();
      setConversations(existing);
      const current = existing[0] ?? (await api.chat.start());
      if (!existing.length) setConversations([current]);
      setConversationId(current.id);
      const history = await api.chat.messages(current.id);
      setMessages([...history.items].reverse());
    })();
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  const openConversation = useCallback(async (id: string) => {
    setConversationId(id);
    setMessages([]);
    const history = await api.chat.messages(id);
    setMessages([...history.items].reverse());
    inputRef.current?.focus();
  }, []);

  const startNew = useCallback(async () => {
    const created = await api.chat.start();
    setConversations((prev) => [created, ...prev]);
    setConversationId(created.id);
    setMessages([]);
    inputRef.current?.focus();
  }, []);

  const send = useCallback(async (text: string) => {
    if (!conversationId || !text.trim() || busy) return;
    setBusy(true);
    setError(null);
    setQuestion("");
    try {
      const res = await api.chat.ask(conversationId, text.trim());
      setMessages((prev) => [...prev, res.question, res.answer]);
      // The first question becomes the conversation's title server-side.
      setConversations(await api.chat.conversations());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send that question.");
    } finally {
      setBusy(false);
    }
  }, [conversationId, busy]);

  async function startRecording() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      recorder.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        if (!conversationId || blob.size === 0) return;
        setBusy(true);
        try {
          const res = await api.chat.askAudio(conversationId, blob);
          setMessages((prev) => [...prev, res.question, res.answer]);
        } catch (err) {
          if (err instanceof ApiError && err.status === 503) {
            setVoiceDisabled(true);
            setError("Voice questions aren't enabled on this server. Please type instead.");
          } else {
            setError(err instanceof ApiError ? err.message : "Could not send that recording.");
          }
        } finally {
          setBusy(false);
        }
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      setError("Microphone access was blocked. You can type your question instead.");
    }
  }

  function stopRecording() {
    recorderRef.current?.stop();
    recorderRef.current = null;
    setRecording(false);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void send(question);
  }

  if (!conversationId) {
    return <div className="flex h-full items-center justify-center"><Spinner label="Opening your conversation" /></div>;
  }

  return (
    <div className="flex h-full">
      {/* Conversation list */}
      <div className="hidden w-[264px] shrink-0 flex-col border-e border-line bg-surface/40 lg:flex">
        <div className="p-3">
          <Button variant="secondary" className="w-full justify-start" onClick={() => void startNew()}>
            <Plus size={16} /> New conversation
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {conversations.map((c) => (
            <button
              key={c.id}
              onClick={() => void openConversation(c.id)}
              className={cn(
                "mb-0.5 w-full rounded-[10px] px-3 py-2.5 text-start transition-colors duration-150",
                c.id === conversationId ? "bg-surface-sunk" : "hover:bg-surface-sunk/60",
              )}
            >
              <p className="truncate text-[13px] font-medium text-ink">{c.title ?? "New conversation"}</p>
              <p className="mt-0.5 text-[11px] text-ink-faint">{relativeTime(c.created_at)}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Thread */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[720px] px-6 py-8">
            {messages.length === 0 && !busy && (
              <div className="pt-10">
                <h2 className="font-serif text-[28px] leading-tight tracking-[-0.015em] text-ink">
                  How can I help with your recovery?
                </h2>
                <p className="mt-2 text-[14px] leading-relaxed text-ink-muted">
                  Ask in Bangla or English. Answers come from your programme handbook
                  and trusted health sources, and always show where they came from.
                </p>
                <div className="mt-6 grid gap-2 sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => void send(s)}
                      className="rounded-[12px] border border-line bg-surface px-4 py-3 text-start text-[13.5px] text-ink-soft transition-colors duration-150 hover:border-teal-400 hover:text-ink"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m) => <Bubble key={m.id} message={m} />)}

            {busy && (
              <div className="animate-rise flex items-center gap-2 py-3 text-[13px] text-ink-muted">
                <TypingDots /> <span className="ms-1">Looking that up</span>
              </div>
            )}
            <div ref={endRef} />
          </div>
        </div>

        {/* Composer */}
        <div className="border-t border-line bg-paper/80 backdrop-blur">
          <div className="mx-auto w-full max-w-[720px] px-6 py-4">
            {error && (
              <p role="alert" className="mb-2.5 rounded-[10px] bg-severe-bg px-3 py-2 text-[13px] text-severe-fg">
                {error}
              </p>
            )}
            <form onSubmit={submit}
              className="flex items-end gap-2 rounded-[14px] border border-line-strong bg-surface p-2 transition-[border-color,box-shadow] duration-150 focus-within:border-teal-400 focus-within:ring-4 focus-within:ring-teal-400/10">
              <textarea
                ref={inputRef}
                rows={1}
                value={question}
                onChange={(e) => {
                  setQuestion(e.target.value);
                  e.target.style.height = "auto";
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`;
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(question); }
                }}
                placeholder={recording ? "Recording… press stop when you're done" : "Ask anything about your recovery"}
                disabled={busy || recording}
                aria-label="Your question"
                className="max-h-[180px] min-h-[38px] flex-1 resize-none bg-transparent px-2 py-2 text-[14.5px] leading-relaxed text-ink outline-none placeholder:text-ink-faint disabled:opacity-60"
              />
              {!voiceDisabled && (
                <Button type="button" size="icon"
                  variant={recording ? "danger" : "ghost"}
                  onClick={recording ? stopRecording : startRecording}
                  disabled={busy}
                  aria-label={recording ? "Stop recording" : "Ask by voice"}>
                  {recording ? <Square size={16} /> : <Mic size={17} />}
                </Button>
              )}
              <Button type="submit" size="icon" disabled={busy || recording || !question.trim()} aria-label="Send">
                <Send size={16} />
              </Button>
            </form>
            <p className="mt-2 text-center text-[11.5px] text-ink-faint">
              This assistant supports your care — it does not replace your rehabilitation team.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const isEmergency = !isUser &&
    (message.content.includes("emergency number") || message.content.includes("জরুরি নম্বরে"));
  // Bangla needs its own font stack and looser leading.
  const bengali = /[ঀ-৿]/.test(message.content);

  if (isUser) {
    return (
      <div className="animate-rise mb-6 flex justify-end">
        <div className={cn(
          "max-w-[85%] rounded-[16px] rounded-ee-[6px] bg-teal-500 px-4 py-2.5 text-[14.5px] leading-relaxed text-white",
          bengali && "bn",
        )}>
          {message.transcribed_from_audio && (
            <span className="mb-1 flex items-center gap-1 text-[11px] uppercase tracking-wide opacity-75">
              <Mic size={11} /> voice
            </span>
          )}
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="animate-rise mb-7">
      {isEmergency ? (
        <div className="rounded-[14px] border border-severe-fg/20 bg-severe-bg px-5 py-4">
          <p className="mb-2 flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.05em] text-severe-fg">
            <AlertTriangle size={15} /> Seek help now
          </p>
          <Markdown className={cn("text-ink", bengali && "bn")}>{message.content}</Markdown>
        </div>
      ) : (
        <Markdown className={cn("text-ink-soft", bengali && "bn")}>{message.content}</Markdown>
      )}

      {message.citations && message.citations.length > 0 && (
        <details className="group mt-3.5">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-md text-[11.5px] font-semibold uppercase tracking-[0.05em] text-ink-faint transition-colors hover:text-ink-muted">
            <BookOpen size={12} />
            {message.citations.length} source{message.citations.length > 1 ? "s" : ""}
          </summary>
          <ul className="mt-2 space-y-1.5 border-s-2 border-line ps-3">
            {message.citations.map((c) => (
              <li key={c.id} className="text-[12.5px] leading-relaxed text-ink-muted">
                <span className="font-medium text-ink-soft">[{c.index}] {c.title}</span>
                <span className="text-ink-faint"> — {c.source}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
