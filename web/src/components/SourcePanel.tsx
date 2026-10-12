import { ArrowSquareOut, FileText, X } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { api, isExternalUrl, type Citation, type DocumentResponse } from "../lib/api";
import { ui } from "../lib/site";
import { ICON_WEIGHT } from "./Layout";
import { RichText } from "./RichText";

interface Props {
  dataset: string;
  citation: Citation | null;
  onClose: () => void;
  /** Bottom sheet on small screens */
  sheet?: boolean;
}

function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function SourcePanel({ dataset, citation, onClose, sheet = false }: Props) {
  const [doc, setDoc] = useState<DocumentResponse | null>(null);
  const [docState, setDocState] = useState<"idle" | "loading" | "error">("idle");
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    setDoc(null);
    setDocState("idle");
    if (citation) headingRef.current?.focus();
  }, [citation]);

  if (!citation) {
    return (
      <section aria-label="Source" className="rounded-md border border-accent/30 bg-accent-soft/70 p-5 text-sm text-fg-muted">
        <div className="flex items-center gap-2 font-medium text-fg">
          <FileText size={18} weight={ICON_WEIGHT} className="text-accent-text" aria-hidden />
          Sources
        </div>
        <p className="mt-2">Select a citation number in an answer to see the passage it comes from.</p>
      </section>
    );
  }

  const external = isExternalUrl(citation.source);
  const path = citation.section_path.split(" > ");

  const loadDocument = async () => {
    setDocState("loading");
    try {
      setDoc(await api.document(dataset, citation.doc_id));
      setDocState("idle");
    } catch {
      setDocState("error");
    }
  };

  return (
    <section
      aria-labelledby="source-title"
      className={`${ui.panel} flex flex-col ${sheet ? "max-h-[75dvh] rounded-b-none border-b-0" : "max-h-[calc(100dvh-7rem)]"}`}
      onKeyDown={(e) => e.key === "Escape" && onClose()}
    >
      <div className="flex items-start justify-between gap-3 border-b border-line p-4">
        <div className="min-w-0">
          <p className="font-mono text-xs text-fg-subtle">Source [{citation.citation_id}]</p>
          <h2 id="source-title" ref={headingRef} tabIndex={-1} className="mt-1 text-base font-semibold text-fg">
            {citation.doc_title}
          </h2>
          <p className="mt-1 text-sm text-fg-muted">{path.slice(1).join(" > ") || path[0]}</p>
        </div>
        <button type="button" onClick={onClose} className={ui.buttonGhost} aria-label="Close source panel">
          <X size={18} weight={ICON_WEIGHT} aria-hidden />
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 text-sm">
        <div>
          <p className={`${ui.micro} mb-2`}>Supporting passage</p>
          <div className="rounded-md border-l-2 border-accent bg-mark p-3 text-fg">
            <RichText text={citation.excerpt} />
          </div>
        </div>

        {external ? (
          <a href={citation.source} target="_blank" rel="noreferrer" className={`${ui.buttonSecondary} w-full no-underline`}>
            Open on {hostOf(citation.source)}
            <ArrowSquareOut size={16} weight={ICON_WEIGHT} aria-hidden />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        ) : (
          <div>
            {!doc && (
              <button type="button" onClick={loadDocument} disabled={docState === "loading"} className={`${ui.buttonSecondary} w-full`}>
                {docState === "loading" ? "Loading document" : "Show full document"}
              </button>
            )}
            {docState === "error" && (
              <p role="alert" className="mt-2 text-fg-muted">
                The document could not be loaded. Try again.
              </p>
            )}
            {doc && (
              <article aria-label={`Full document: ${doc.title}`} className="rounded-md border border-line p-3">
                <p className="mb-3 font-mono text-xs text-fg-subtle">
                  {doc.source}
                  {doc.last_updated ? `, last updated ${doc.last_updated}` : ""}
                </p>
                <RichText text={doc.content.replace(/^#\s.*\n/, "")} className="text-fg-muted" />
              </article>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
