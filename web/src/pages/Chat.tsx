import { ArrowClockwise, Headset, PaperPlaneRight, Warning } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { ICON_WEIGHT, Page } from "../components/Layout";
import { RichText } from "../components/RichText";
import { SourcePanel } from "../components/SourcePanel";
import { EASE, fadeRise, sheetSpring, ShinyText, staggerItem, staggerParent } from "../components/motion";
import { api, ApiError, type Citation, type Dataset } from "../lib/api";
import { Logo } from "../components/Logo";
import { ui } from "../lib/site";

const MAX_QUESTION_CHARS = 500;

type Item =
  | { id: string; kind: "question"; text: string }
  | { id: string; kind: "answer"; text: string; citations: Citation[]; escalated: boolean; traceId: string }
  | { id: string; kind: "error"; question: string; message: string }
  | { id: string; kind: "limit"; message: string };

const newId = () => crypto.randomUUID();

function useIsNarrow() {
  const query = "(max-width: 767px)";
  const [narrow, setNarrow] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setNarrow(e.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return narrow;
}

function AnswerSkeleton() {
  return (
    <motion.div {...fadeRise} aria-hidden className="space-y-2.5 py-1" data-testid="answer-skeleton">
      <ShinyText className="text-sm">Searching the documentation</ShinyText>
      <div className="skeleton h-3.5 w-11/12" />
      <div className="skeleton h-3.5 w-10/12" />
      <div className="skeleton h-3.5 w-7/12" />
      <div className="flex gap-2 pt-1">
        <div className="skeleton h-6 w-8" />
        <div className="skeleton h-6 w-8" />
      </div>
    </motion.div>
  );
}

function DatasetMeta({ dataset }: { dataset: Dataset }) {
  return (
    <div className="mt-2 space-y-1 text-sm text-fg-muted">
      {dataset.notice && (
        <p className="inline-flex items-center rounded-md border border-line bg-surface-2 px-2 py-0.5 text-xs font-medium text-fg">
          {dataset.notice}
        </p>
      )}
      <p>
        Source:{" "}
        {dataset.source_url ? (
          <a href={dataset.source_url} target="_blank" rel="noreferrer">
            {dataset.source}
          </a>
        ) : (
          dataset.source
        )}
        . License:{" "}
        {dataset.license_url ? (
          <a href={dataset.license_url} target="_blank" rel="noreferrer">
            {dataset.license}
          </a>
        ) : (
          dataset.license
        )}
        .
      </p>
    </div>
  );
}

export default function Chat() {
  const [params, setParams] = useSearchParams();
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [pending, setPending] = useState(false);
  const [question, setQuestion] = useState("");
  const [selected, setSelected] = useState<{ itemId: string; citationId: number } | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const sessionId = useRef(newId());
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const closeSource = () => {
    setSelected(null);
    opener.current?.focus(); // return focus to the citation that opened the panel
  };
  const narrow = useIsNarrow();
  const selectId = useId();
  const inputId = useId();
  const hintId = useId();

  const loadDatasets = useCallback(async () => {
    setDatasetsError(null);
    try {
      const res = await api.datasets();
      setDatasets(res.datasets);
      if (!params.get("dataset")) setParams({ dataset: res.default }, { replace: true });
    } catch (e) {
      setDatasetsError(e instanceof ApiError ? e.message : "Could not load datasets.");
    }
  }, [params, setParams]);

  // Load once on mount. loadDatasets reads the current URL params, so re-running it on every URL change is not wanted.
  const loadOnce = useRef(loadDatasets);
  useEffect(() => {
    loadOnce.current();
  }, []);

  const datasetName = params.get("dataset") ?? "";
  const dataset = useMemo(() => datasets?.find((d) => d.name === datasetName) ?? datasets?.[0] ?? null, [datasets, datasetName]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [items, pending]);

  const selectedCitation = useMemo(() => {
    if (!selected) return null;
    const item = items.find((i) => i.id === selected.itemId);
    return item?.kind === "answer" ? (item.citations.find((c) => c.citation_id === selected.citationId) ?? null) : null;
  }, [items, selected]);

  const switchDataset = (name: string) => {
    setParams({ dataset: name });
    setItems([]);
    setSelected(null);
    setQuestion("");
    setAnnouncement("");
    sessionId.current = newId();
  };

  const ask = async (text: string, replaceId?: string) => {
    const q = text.trim();
    if (!q || pending || !dataset) return;
    setPending(true);
    setItems((prev) => {
      const base = replaceId ? prev.filter((i) => i.id !== replaceId) : prev;
      return replaceId ? base : [...base, { id: newId(), kind: "question", text: q }];
    });
    setQuestion("");
    try {
      const res = await api.chat(q, dataset.name, sessionId.current);
      setItems((prev) => [
        ...prev,
        { id: newId(), kind: "answer", text: res.answer, citations: res.citations, escalated: res.escalated, traceId: res.trace_id },
      ]);
      setAnnouncement(res.escalated ? "Your question was handed to a human support agent." : `Answer received. ${res.answer}`);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError("unknown", "Something went wrong.", 0);
      if (err.isLimit) {
        setItems((prev) => [...prev, { id: newId(), kind: "limit", message: err.message }]);
      } else {
        setItems((prev) => [...prev, { id: newId(), kind: "error", question: q, message: err.message }]);
      }
      setAnnouncement(err.message);
    } finally {
      setPending(false);
      inputRef.current?.focus();
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      ask(question);
    }
  };

  const citationButton = (itemId: string, citations: Citation[]) => (id: number, key: string) => {
    const exists = citations.some((c) => c.citation_id === id);
    if (!exists) return <span key={key}>[{id}]</span>;
    const active = selected?.itemId === itemId && selected.citationId === id;
    return (
      <button
        key={key}
        type="button"
        onClick={(e) => {
          opener.current = e.currentTarget;
          setSelected({ itemId, citationId: id });
        }}
        aria-label={`Show source ${id}`}
        aria-pressed={active}
        className={`mx-0.5 inline-flex h-5 min-w-6 items-center justify-center rounded-md border px-1 align-baseline font-mono text-xs transition-[background-color,border-color,color,transform] duration-150 active:scale-90 ${
          active ? "border-accent bg-accent text-accent-fg" : "border-line-strong bg-accent-soft text-accent-text hover:border-accent-text"
        }`}
      >
        {id}
      </button>
    );
  };

  return (
    <Page>
      <div className="page-wash">
      <div className="mx-auto grid min-h-[calc(100dvh-3.5rem)] max-w-6xl gap-6 px-4 pt-6 sm:px-6 md:grid-cols-[minmax(0,1fr)_minmax(300px,380px)]">
        <div className="flex min-w-0 flex-col">
          <div className="border-b border-line pb-4">
            <label htmlFor={selectId} className={ui.label}>
              Dataset
            </label>
            {datasets ? (
              <select
                id={selectId}
                value={dataset?.name ?? ""}
                onChange={(e) => switchDataset(e.target.value)}
                className={`${ui.field} mt-1.5 h-10 max-w-sm`}
              >
                {datasets.map((d) => (
                  <option key={d.name} value={d.name}>
                    {d.display_name}
                  </option>
                ))}
              </select>
            ) : datasetsError ? (
              <div role="alert" className="mt-2 flex flex-wrap items-center gap-3 text-sm text-fg-muted">
                {datasetsError}
                <button type="button" className={ui.buttonSecondary} onClick={loadDatasets}>
                  <ArrowClockwise size={16} weight={ICON_WEIGHT} aria-hidden />
                  Retry
                </button>
              </div>
            ) : (
              <div className="skeleton mt-1.5 h-10 max-w-sm" aria-label="Loading datasets" />
            )}
            {dataset && <DatasetMeta dataset={dataset} />}
          </div>

          <div aria-live="polite" role="status" className="sr-only">
            {announcement}
          </div>

          <div className="flex-1 space-y-6 py-6" aria-busy={pending}>
            {items.length === 0 && !pending && dataset && (
              <motion.div key={dataset.name} variants={staggerParent} initial="hidden" animate="show" className="space-y-3">
                <motion.h1 variants={staggerItem} className="text-lg font-semibold text-fg">
                  Ask about {dataset.display_name}
                </motion.h1>
                <motion.p variants={staggerItem} className="text-sm text-fg-muted">
                  {dataset.description}
                </motion.p>
                <motion.p variants={staggerItem} className="pt-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-accent-text">
                  Example questions
                </motion.p>
                <ul className="flex flex-col gap-2">
                  {dataset.examples.map((ex) => (
                    <motion.li key={ex} variants={staggerItem}>
                      <button
                        type="button"
                        onClick={() => ask(ex)}
                        className="w-full rounded-md border border-line bg-surface px-3 py-2.5 text-left text-sm text-fg transition-[background-color,border-color,transform] duration-200 hover:border-accent-text hover:bg-surface-2 active:scale-[0.99]"
                      >
                        {ex}
                      </button>
                    </motion.li>
                  ))}
                </ul>
              </motion.div>
            )}

            <AnimatePresence initial={false}>
              {items.map((item) => (
                <motion.article key={item.id} layout="position" {...fadeRise} aria-label={item.kind === "question" ? "You asked" : "Agent response"}>
                  {item.kind === "question" && (
                    <div className="flex justify-end">
                      <p className="max-w-[85%] whitespace-pre-wrap rounded-md border border-accent/30 bg-accent-soft px-3.5 py-2.5 text-sm text-fg">{item.text}</p>
                    </div>
                  )}

                  {item.kind === "answer" && !item.escalated && (
                    <div className="flex gap-3 text-[15px] text-fg">
                      <span className="mt-0.5">
                        <Logo size={22} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <RichText text={item.text} renderCitation={citationButton(item.id, item.citations)} />
                        <p className="mt-2 font-mono text-xs text-fg-subtle">trace {item.traceId.slice(0, 8)}</p>
                      </div>
                    </div>
                  )}

                  {item.kind === "answer" && item.escalated && (
                    <div className="flex gap-3 rounded-md border border-accent/40 bg-accent-soft p-4" data-testid="escalation">
                      <Headset size={20} weight={ICON_WEIGHT} className="mt-0.5 shrink-0 text-accent-text" aria-hidden />
                      <div className="text-sm">
                        <p className="font-semibold text-fg">Handed to a human agent</p>
                        <p className="mt-1 text-fg-muted">{item.text}</p>
                        <p className="mt-2 font-mono text-xs text-fg-subtle">trace {item.traceId.slice(0, 8)}</p>
                      </div>
                    </div>
                  )}

                  {item.kind === "error" && (
                    <div role="alert" className={`${ui.panel} flex flex-wrap items-start gap-3 p-4 text-sm`}>
                      <Warning size={20} weight={ICON_WEIGHT} className="mt-0.5 shrink-0 text-fg-muted" aria-hidden />
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-fg">The answer could not be loaded</p>
                        <p className="mt-1 text-fg-muted">{item.message}</p>
                      </div>
                      <button type="button" className={ui.buttonSecondary} onClick={() => ask(item.question, item.id)} disabled={pending}>
                        <ArrowClockwise size={16} weight={ICON_WEIGHT} aria-hidden />
                        Retry
                      </button>
                    </div>
                  )}

                  {item.kind === "limit" && (
                    <div role="alert" className={`${ui.panel} flex gap-3 p-4 text-sm`} data-testid="limit">
                      <Warning size={20} weight={ICON_WEIGHT} className="mt-0.5 shrink-0 text-fg-muted" aria-hidden />
                      <div>
                        <p className="font-medium text-fg">{item.message}</p>
                        <p className="mt-1 text-fg-muted">This public demo limits how many questions it answers to keep model costs down.</p>
                      </div>
                    </div>
                  )}
                </motion.article>
              ))}
            </AnimatePresence>

            <AnimatePresence>{pending && <AnswerSkeleton key="skeleton" />}</AnimatePresence>
            <div ref={endRef} />
          </div>

          <form
            className="sticky bottom-0 border-t border-line bg-bg pb-4 pt-3"
            onSubmit={(e) => {
              e.preventDefault();
              ask(question);
            }}
          >
            <label htmlFor={inputId} className={ui.label}>
              Your question
            </label>
            <div className="mt-1.5 flex items-end gap-2">
              <textarea
                id={inputId}
                ref={inputRef}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={onKeyDown}
                rows={2}
                maxLength={MAX_QUESTION_CHARS}
                aria-describedby={hintId}
                disabled={!dataset}
                className={`${ui.field} min-h-[44px] resize-none py-2.5 leading-snug focus:border-accent-text`}
              />
              <button type="submit" className={`${ui.buttonAccent} h-11 shrink-0 disabled:cursor-not-allowed disabled:opacity-50`} disabled={pending || !question.trim() || !dataset}>
                <PaperPlaneRight size={16} weight={ICON_WEIGHT} aria-hidden />
                Send
              </button>
            </div>
            <p id={hintId} className="mt-1.5 flex justify-between gap-4 text-xs text-fg-subtle">
              <span>Enter to send, Shift+Enter for a new line.</span>
              <span className="font-mono">
                {question.length}/{MAX_QUESTION_CHARS}
              </span>
            </p>
          </form>
        </div>

        {!narrow && dataset && (
          <aside className="hidden md:block">
            <div className="sticky top-20">
              <AnimatePresence mode="wait">
                <motion.div
                  key={selectedCitation ? `${selected?.itemId}-${selected?.citationId}` : "empty"}
                  initial={{ opacity: 0, x: 12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -6 }}
                  transition={{ duration: 0.26, ease: EASE }}
                >
                  <SourcePanel dataset={dataset.name} citation={selectedCitation} onClose={closeSource} />
                </motion.div>
              </AnimatePresence>
            </div>
          </aside>
        )}
      </div>
      </div>

      <AnimatePresence>
        {narrow && dataset && selectedCitation && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 flex flex-col justify-end bg-zinc-950/50"
            onClick={closeSource}
          >
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-labelledby="source-title"
              onClick={(e) => e.stopPropagation()}
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={sheetSpring}
            >
              <SourcePanel dataset={dataset.name} citation={selectedCitation} onClose={closeSource} sheet />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </Page>
  );
}
