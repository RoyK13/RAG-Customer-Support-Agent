import { ArrowRight, CheckCircle, GithubLogo, Headset, ListMagnifyingGlass, Scales, TextAlignLeft } from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { motion } from "motion/react";
import { ICON_WEIGHT, Page } from "../components/Layout";
import { BlurText, EASE } from "../components/motion";
import { ScrollStack, ScrollStackItem } from "../components/ScrollStack";
import evalData from "../generated/eval.json";
import { GITHUB_URL, ui } from "../lib/site";

const STEPS: { name: string; icon: Icon; text: string; detail: string }[] = [
  { name: "Retrieve", icon: ListMagnifyingGlass, text: "Runs a dense search over the selected dataset's own Qdrant collection, reranks the top 20 with a cross-encoder, and keeps the best 6, plus the sections on either side of the best match.", detail: "Qdrant, bge-small-en-v1.5, MiniLM cross-encoder" },
  { name: "Grade", icon: Scales, text: "A model call checks whether those sections actually contain the answer. If they do not, the question goes straight to Escalate.", detail: 'returns {"sufficient": bool, "reason": str}' },
  { name: "Answer", icon: TextAlignLeft, text: "Writes an answer from the numbered sections only, citing each sentence inline as [1], [2].", detail: "persona and sources from dataset.yaml" },
  { name: "Validate", icon: CheckCircle, text: "Checks that every cited number exists in the retrieved set and that no sentence is uncited. A failed answer is regenerated once.", detail: "IDs in range, every sentence cited, one retry" },
  { name: "Escalate", icon: Headset, text: "If the context is insufficient or validation fails twice, the agent hands the question to a human and says so.", detail: "escalated: true, logged to the escalations table" },
];

type Metric = { value: number | null };
type Result = {
  generated_at: string;
  config: { chat_model: string; judge_models: string[]; judge_models_used?: string[]; embedding: string; reranker?: string | null; top_k: number };
  counts: { questions: number };
  metrics: Record<string, Metric>;
};
type DatasetEval = { name: string; display_name: string; notice: string | null; result: Result | null };

const COLUMNS: { key: string; label: string }[] = [
  { key: "faithfulness", label: "Faithfulness" },
  { key: "context_precision", label: "Context precision" },
  { key: "answer_relevancy", label: "Answer relevancy" },
  { key: "citation_accuracy", label: "Citation accuracy" },
  { key: "escalation_accuracy", label: "Escalation accuracy" },
];

/** Formats a 0-1 score as a percentage, truncated (never rounded up) to one decimal place. */
function pct(m: Metric | undefined): string {
  if (!m || m.value === null || m.value === undefined) return "n/a";
  return `${(Math.floor(m.value * 1000) / 10).toFixed(1)}%`;
}

function EvalTable() {
  const rows = (evalData as { datasets: DatasetEval[] }).datasets;
  const withResults = rows.filter((r) => r.result);
  return (
    <div className="space-y-3">
      <div className={`${ui.panel} overflow-x-auto`}>
        <table className="w-full min-w-[720px] text-left text-sm">
          <caption className="sr-only">Evaluation results per dataset</caption>
          <thead>
            <tr className="border-b border-line bg-surface-2/60">
              <th scope="col" className={`${ui.micro} px-4 py-3`}>
                Dataset
              </th>
              {COLUMNS.map((c) => (
                <th key={c.key} scope="col" className={`${ui.micro} px-4 py-3 text-right`}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name} className="border-b border-line last:border-b-0">
                <th scope="row" className="px-4 py-4 font-medium text-fg">
                  {row.display_name}
                  {row.result && <span className="block font-mono text-xs font-normal text-fg-subtle">{row.result.counts.questions} questions</span>}
                </th>
                {row.result ? (
                  COLUMNS.map((c) => (
                    <td key={c.key} className="px-4 py-4 text-right font-mono text-fg">
                      {pct(row.result!.metrics[c.key])}
                    </td>
                  ))
                ) : (
                  <td colSpan={COLUMNS.length} className="px-4 py-3 text-fg-muted">
                    Evaluation not run yet
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {withResults.length > 0 && (
        <p className="text-sm text-fg-muted">
          Measured with Ragas, DeepEval, and custom checks by <code className="font-mono text-xs">python -m eval.run</code>. Chat model{" "}
          <span className="font-mono text-xs">{withResults[0].result!.config.chat_model}</span>, grader models{" "}
          <span className="font-mono text-xs">
            {[...new Set(withResults.flatMap((r) => r.result!.config.judge_models_used ?? r.result!.config.judge_models.slice(0, 1)))].join(", ")}
          </span>
          , embeddings{" "}
          <span className="font-mono text-xs">{withResults[0].result!.config.embedding}</span>
          {withResults[0].result!.config.reranker ? (
            <>
              , reranker <span className="font-mono text-xs">{withResults[0].result!.config.reranker}</span>
            </>
          ) : (
            ", measured before reranking was added"
          )}
          . Each dataset includes 6 questions
          its documents cannot answer, which should escalate. Last run{" "}
          {withResults.map((r) => `${r.display_name} ${r.result!.generated_at.slice(0, 10)}`).join(", ")}.
        </p>
      )}
    </div>
  );
}

export default function Landing() {
  const { hash } = useLocation();
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView();
  }, [hash]);

  return (
    <Page>
      <div className="hero-wash">
      <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-24 pt-14 sm:px-6 md:pt-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:pt-24 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
        <div>
          <BlurText
            text="A support agent that cites every claim"
            className="max-w-xl text-4xl font-semibold leading-[1.05] tracking-[-0.03em] text-fg sm:text-5xl lg:text-[2.6rem] xl:text-5xl"
          />
          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: EASE, delay: 0.45 }}
            className="mt-5 max-w-md text-lg leading-normal text-fg-muted"
          >
            It answers questions from a document set, cites the exact section for each claim, and escalates when it cannot.
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: EASE, delay: 0.6 }}
            className="mt-8 flex flex-wrap gap-3"
          >
            <Link to="/chat" className={`${ui.buttonAccent} no-underline hover:text-accent-fg`}>
              Try the demo
              <ArrowRight size={16} weight={ICON_WEIGHT} aria-hidden />
            </Link>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className={`${ui.buttonSecondary} no-underline hover:text-fg`}>
              <GithubLogo size={16} weight={ICON_WEIGHT} aria-hidden />
              View on GitHub
            </a>
          </motion.div>
        </div>
        <motion.figure
          initial={{ opacity: 0, y: 16, scale: 0.985 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.8, ease: EASE, delay: 0.3 }}
          className="min-w-0"
        >
          <img
            src="/screenshots/chat-light.png"
            alt="The chat demo answering a warranty question for Halden Home Appliances, with inline citation numbers and the source panel showing the cited Warranty Policy section."
            width={1440}
            height={900}
            className="theme-light-only w-full rounded-md border border-line shadow-[var(--shadow-mockup)]"
          />
          <img
            src="/screenshots/chat-dark.png"
            alt="The chat demo in dark theme answering a warranty question for Halden Home Appliances, with inline citation numbers and the source panel showing the cited Warranty Policy section."
            width={1440}
            height={900}
            className="theme-dark-only w-full rounded-md border border-line shadow-[var(--shadow-mockup)]"
          />
        </motion.figure>
      </section>
      </div>

      <section id="how-it-works" aria-labelledby="how" className="scroll-mt-16 border-t border-line">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 pt-24 sm:px-6 md:grid-cols-[minmax(0,4fr)_minmax(0,8fr)]">
          <div className="md:sticky md:top-24 md:self-start">
            <h2 id="how" className="text-2xl font-semibold tracking-[-0.02em] text-fg sm:text-3xl">
              How it works
            </h2>
            <p className="mt-3 text-sm text-fg-muted">
              One LangGraph graph serves every dataset. Each dataset is a folder with Markdown documents and a config file, so
              nothing in the code is specific to either demo.
            </p>
          </div>
          <ScrollStack label="Agent steps">
            {STEPS.map(({ name, icon: StepIcon, text, detail }) => (
              <ScrollStackItem key={name}>
                <div className="flex items-center gap-3">
                  <span className="inline-flex size-10 items-center justify-center rounded-md bg-accent-soft text-accent-text">
                    <StepIcon size={20} weight={ICON_WEIGHT} aria-hidden />
                  </span>
                  <h3 className="text-xl font-semibold tracking-[-0.01em] text-fg">{name}</h3>
                </div>
                <p className="mt-4 text-[15px] leading-relaxed text-fg-muted">{text}</p>
                <p className="mt-5 border-t border-line pt-4 font-mono text-xs text-fg-subtle">{detail}</p>
              </ScrollStackItem>
            ))}
          </ScrollStack>
        </div>
      </section>

      <section id="results" aria-labelledby="results-title" className="scroll-mt-16 border-t border-line">
        <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
          <h2 id="results-title" className="text-2xl font-semibold tracking-[-0.02em] text-fg sm:text-3xl">
            Evaluation results
          </h2>
          <p className="mt-4 max-w-2xl text-[15px] text-fg-muted">
            Faithfulness: answer claims supported by the retrieved text. Citation accuracy: citations whose passage supports the
            sentence they are attached to. Escalation accuracy: questions where the agent escalated exactly when it should have.
          </p>
          <div className="mt-6">
            <EvalTable />
          </div>
        </div>
      </section>
    </Page>
  );
}
