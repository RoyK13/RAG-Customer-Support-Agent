import { Check, Copy } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import { Fragment, useState, type ReactNode } from "react";

/**
 * Minimal Markdown rendering for answers and source excerpts: paragraphs, bullet and
 * numbered lists, fenced code blocks, inline code, and bold. Citation markers like [1]
 * are passed to `renderCitation` so the caller can turn them into buttons.
 */

type Block = { kind: "code"; lang: string; text: string } | { kind: "list"; ordered: boolean; items: string[] } | { kind: "para"; text: string };

const FENCE = /^\s*(```|~~~)(.*)$/;
const LIST_ITEM = /^\s*(?:([-*+])|(\d+)[.)])\s+(.*)$/;
// Source documents (the FastAPI docs) use emoji as decoration. The UI shows none, so they are dropped at render time.
const PICTOGRAPH = /[\p{Extended_Pictographic}\u{FE0F}\u{200D}]\s?/gu;

export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  const lines = text.replace(/\r\n/g, "\n").replace(PICTOGRAPH, "").split("\n");
  let para: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  const flush = () => {
    if (para.length) blocks.push({ kind: "para", text: para.join("\n") });
    if (list) blocks.push({ kind: "list", ...list });
    para = [];
    list = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const fence = lines[i].match(FENCE);
    if (fence) {
      flush();
      const code: string[] = [];
      i++;
      while (i < lines.length && !FENCE.test(lines[i])) code.push(lines[i++]);
      blocks.push({ kind: "code", lang: fence[2].trim(), text: code.join("\n") });
      continue;
    }
    const line = lines[i];
    if (!line.trim()) {
      flush();
      continue;
    }
    const item = line.match(LIST_ITEM);
    if (item) {
      const ordered = Boolean(item[2]);
      if (para.length || (list && list.ordered !== ordered)) flush();
      list = list ?? { ordered, items: [] };
      list.items.push(item[3]);
    } else if (list && /^\s{2,}\S/.test(line)) {
      list.items[list.items.length - 1] += " " + line.trim();
    } else {
      if (list) flush();
      para.push(line);
    }
  }
  flush();
  return blocks;
}

function renderInline(text: string, renderCitation?: (id: number, key: string) => ReactNode, keyPrefix = ""): ReactNode[] {
  const out: ReactNode[] = [];
  const pattern = /(\[\d+\])|(`[^`]+`)|(\*\*[^*]+\*\*)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let n = 0;
  while ((match = pattern.exec(text))) {
    if (match.index > last) out.push(text.slice(last, match.index));
    const key = `${keyPrefix}-${n++}`;
    if (match[1]) {
      const id = Number(match[1].slice(1, -1));
      out.push(renderCitation ? renderCitation(id, key) : <Fragment key={key}>{match[1]}</Fragment>);
    } else if (match[2]) {
      out.push(
        <code key={key} className="rounded-md border border-line bg-surface-2 px-1 py-px font-mono text-[0.85em]">
          {match[2].slice(1, -1)}
        </code>,
      );
    } else {
      out.push(<strong key={key}>{match[3].slice(2, -2)}</strong>);
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function CodeBlock({ lang, text }: { lang: string; text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <div className="overflow-hidden rounded-md border border-line bg-surface-2">
      <div className="flex h-8 items-center justify-between border-b border-line px-3">
        <span className="font-mono text-xs text-fg-subtle">{lang.toLowerCase() || "text"}</span>
        <button type="button" onClick={copy} className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-fg-muted transition-colors hover:bg-surface hover:text-fg">
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={copied ? "done" : "copy"}
              className="inline-flex"
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.6 }}
              transition={{ duration: 0.15 }}
            >
              {copied ? <Check size={14} weight="regular" aria-hidden /> : <Copy size={14} weight="regular" aria-hidden />}
            </motion.span>
          </AnimatePresence>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 font-mono text-[13px] leading-normal">
        <code>{text}</code>
      </pre>
    </div>
  );
}

export function RichText({ text, renderCitation, className = "" }: { text: string; renderCitation?: (id: number, key: string) => ReactNode; className?: string }) {
  return (
    <div className={`space-y-3 leading-relaxed ${className}`}>
      {parseBlocks(text).map((block, i) => {
        if (block.kind === "code") {
          return <CodeBlock key={i} lang={block.lang} text={block.text} />;
        }
        if (block.kind === "list") {
          const Tag = block.ordered ? "ol" : "ul";
          return (
            <Tag key={i} className={`space-y-1.5 pl-5 ${block.ordered ? "list-decimal" : "list-disc"}`}>
              {block.items.map((item, j) => (
                <li key={j}>{renderInline(item, renderCitation, `${i}-${j}`)}</li>
              ))}
            </Tag>
          );
        }
        return (
          <p key={i} className="whitespace-pre-line">
            {renderInline(block.text, renderCitation, `${i}`)}
          </p>
        );
      })}
    </div>
  );
}
