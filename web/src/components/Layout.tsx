import { GithubLogo, Moon, Sun } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { FASTAPI_DOCS_URL, FASTAPI_LICENSE_URL, GITHUB_URL, ui } from "../lib/site";
import { useTheme } from "../lib/theme";
import { Logo } from "./Logo";
import { EASE } from "./motion";

export const ICON_WEIGHT = "regular" as const;

function ThemeToggle() {
  const [theme, toggle] = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button type="button" onClick={toggle} className={ui.buttonGhost} aria-label={`Switch to ${next} theme`} title={`Switch to ${next} theme`}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme}
          className="inline-flex"
          initial={{ opacity: 0, rotate: -60, scale: 0.7 }}
          animate={{ opacity: 1, rotate: 0, scale: 1 }}
          exit={{ opacity: 0, rotate: 60, scale: 0.7 }}
          transition={{ duration: 0.2, ease: EASE }}
        >
          {theme === "dark" ? <Sun size={18} weight={ICON_WEIGHT} aria-hidden /> : <Moon size={18} weight={ICON_WEIGHT} aria-hidden />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}

export function Header() {
  const onChat = useLocation().pathname === "/chat";
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-bg/95 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2.5 rounded-md text-[15px] font-semibold tracking-tight text-fg no-underline hover:text-fg">
          <Logo size={26} />
          Support Agent
        </Link>
        <nav aria-label="Main" className="flex items-center gap-1">
          <Link to="/#how-it-works" className={`${ui.buttonGhost} no-underline max-md:hidden`}>
            How it works
          </Link>
          <Link to="/#results" className={`${ui.buttonGhost} no-underline max-md:hidden`}>
            Results
          </Link>
          <a href={GITHUB_URL} className={`${ui.buttonGhost} no-underline`} target="_blank" rel="noreferrer">
            <GithubLogo size={18} weight={ICON_WEIGHT} aria-hidden />
            <span className="hidden sm:inline">GitHub</span>
            <span className="sr-only sm:hidden">GitHub</span>
          </a>
          <ThemeToggle />
          {!onChat && (
            <Link to="/chat" className={`${ui.buttonPrimary} ml-1 h-9 px-3.5 no-underline hover:text-primary-fg max-sm:hidden`}>
              Try the demo
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}

export function Footer() {
  const linkClass = "text-fg-muted no-underline hover:text-fg";
  return (
    <footer className="border-t border-line">
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <div className="grid gap-8 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
          <div className="max-w-sm">
            <Link to="/" className="flex items-center gap-2.5 text-[15px] font-semibold tracking-tight text-fg no-underline hover:text-fg">
              <Logo size={22} />
              Support Agent
            </Link>
            <p className="mt-3 text-sm text-fg-muted">A portfolio project: a retrieval-augmented support agent that cites the source section for every claim.</p>
          </div>
          <nav aria-label="Project" className="text-sm">
            <p className={ui.micro}>Project</p>
            <ul className="mt-3 space-y-2">
              <li>
                <Link to="/chat" className={linkClass}>
                  Demo
                </Link>
              </li>
              <li>
                <a href={GITHUB_URL} target="_blank" rel="noreferrer" className={linkClass}>
                  GitHub
                </a>
              </li>
              <li>
                <Link to="/#results" className={linkClass}>
                  Evaluation results
                </Link>
              </li>
            </ul>
          </nav>
          <nav aria-label="Legal" className="text-sm">
            <p className={ui.micro}>Legal</p>
            <ul className="mt-3 space-y-2">
              <li>
                <Link to="/privacy" className={linkClass}>
                  Privacy policy
                </Link>
              </li>
              <li>
                <Link to="/terms" className={linkClass}>
                  Terms
                </Link>
              </li>
            </ul>
          </nav>
        </div>
        <p className="mt-10 border-t border-line pt-6 text-sm text-fg-muted">
          The FastAPI dataset uses the{" "}
          <a href={FASTAPI_DOCS_URL} target="_blank" rel="noreferrer">
            FastAPI documentation
          </a>
          , MIT License, Copyright (c) 2018 Sebastián Ramírez (
          <a href={FASTAPI_LICENSE_URL} target="_blank" rel="noreferrer">
            license
          </a>
          ). This is an unofficial demo and is not affiliated with the FastAPI project. Halden Home Appliances is a fictional company.
        </p>
      </div>
    </footer>
  );
}

export function Page({ children }: { children: ReactNode }) {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (!hash) window.scrollTo(0, 0); // new page starts at the top; anchors scroll themselves
  }, [pathname, hash]);
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only rounded-md bg-primary px-3 py-2 text-primary-fg focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50"
      >
        Skip to content
      </a>
      <Header />
      <motion.main
        id="main"
        className="flex-1"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.25, ease: EASE }}
      >
        {children}
      </motion.main>
      <Footer />
    </div>
  );
}

