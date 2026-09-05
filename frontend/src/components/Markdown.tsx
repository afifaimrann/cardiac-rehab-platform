/**
 * Assistant answers rendered as markdown.
 *
 * The model emits headings, bold, and numbered lists. Rendering that as
 * preformatted text showed the asterisks literally, which made correct answers
 * look broken. Styles are set here rather than by a typography plugin so the
 * chat's rhythm matches the rest of the app.
 */
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("space-y-3 text-[14.5px] leading-[1.75]", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="[&:not(:first-child)]:mt-3">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          ol: ({ children }) => (
            <ol className="mt-3 space-y-2 [counter-reset:step]">{children}</ol>
          ),
          ul: ({ children }) => <ul className="mt-3 space-y-1.5">{children}</ul>,
          li: ({ children }) => (
            <li className="relative ps-5 before:absolute before:start-0 before:top-[0.62em] before:h-1.5 before:w-1.5 before:rounded-full before:bg-current before:opacity-30">
              {children}
            </li>
          ),
          h1: ({ children }) => <h3 className="mt-4 text-[15px] font-semibold">{children}</h3>,
          h2: ({ children }) => <h3 className="mt-4 text-[15px] font-semibold">{children}</h3>,
          h3: ({ children }) => <h3 className="mt-4 text-[14.5px] font-semibold">{children}</h3>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer"
               className="underline decoration-current/30 underline-offset-2 hover:decoration-current">
              {children}
            </a>
          ),
          code: ({ children }) => (
            <code className="rounded bg-surface-sunk px-1.5 py-0.5 text-[13px]">{children}</code>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-s-2 border-line-strong ps-3 text-ink-muted">{children}</blockquote>
          ),
          hr: () => <hr className="my-4 border-line" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
