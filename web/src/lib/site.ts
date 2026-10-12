/** Repository link. Set VITE_GITHUB_URL at build time. */
export const GITHUB_URL = (import.meta.env.VITE_GITHUB_URL as string | undefined) || "https://github.com/";

export const CONTACT_EMAIL = "13kaustav@gmail.com";

/** Retention periods shown on the privacy page. Keep in line with LOG_RETENTION_DAYS and
 * REQUEST_LOG_RETENTION_DAYS on the API (set VITE_ versions at build time if you change them). */
export const LOG_RETENTION_DAYS = Number(import.meta.env.VITE_LOG_RETENTION_DAYS ?? 30);
export const REQUEST_LOG_RETENTION_DAYS = Number(import.meta.env.VITE_REQUEST_LOG_RETENTION_DAYS ?? 2);

export const FASTAPI_DOCS_URL = "https://fastapi.tiangolo.com";
export const FASTAPI_REPO_URL = "https://github.com/fastapi/fastapi";
export const FASTAPI_LICENSE_URL = "https://github.com/fastapi/fastapi/blob/master/LICENSE";

/** Shared class names so every control uses the same shape, sizes, and states. */
export const ui = {
  buttonPrimary:
    "inline-flex items-center justify-center gap-2 rounded-md bg-primary px-4 h-10 text-sm font-medium text-primary-fg transition-[background-color,transform] duration-150 hover:bg-primary-hover active:translate-y-px active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50",
  /** Mint call to action, used once per page for the main action */
  buttonAccent:
    "inline-flex items-center justify-center gap-2 rounded-md bg-accent px-4 h-10 text-sm font-medium text-accent-fg transition-[background-color,transform] duration-150 hover:bg-accent-hover active:translate-y-px active:scale-[0.98]",
  buttonSecondary:
    "inline-flex items-center justify-center gap-2 rounded-md border border-control bg-surface px-4 h-10 text-sm font-medium text-fg transition-[background-color,transform] duration-150 hover:bg-surface-2 active:translate-y-px active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50",
  buttonGhost:
    "inline-flex items-center justify-center gap-2 rounded-md px-3 h-9 text-sm text-fg-muted transition-colors hover:bg-surface-2 hover:text-fg",
  panel: "rounded-md border border-line bg-surface",
  label: "block text-sm font-medium text-fg",
  /** Small uppercase label for panel and table headers */
  micro: "text-[11px] font-semibold uppercase tracking-[0.06em] text-fg-subtle",
  field:
    "w-full rounded-md border border-control bg-surface px-3 text-sm text-fg transition-colors hover:border-fg-subtle focus-visible:outline-2 focus-visible:outline-accent-text",
};
