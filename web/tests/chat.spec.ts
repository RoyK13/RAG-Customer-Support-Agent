import { expect, test, type Page, type Route } from "@playwright/test";

const API = "http://api.mock";

const DATASETS = {
  default: "halden",
  datasets: [
    {
      name: "fastapi",
      display_name: "FastAPI documentation",
      description: "The English user documentation of the FastAPI web framework.",
      source: "FastAPI documentation, github.com/fastapi/fastapi (docs/en/docs)",
      source_url: "https://fastapi.tiangolo.com",
      license: "MIT License, Copyright (c) 2018 Sebastián Ramírez",
      license_url: "https://github.com/fastapi/fastapi/blob/master/LICENSE",
      notice: "Unofficial demo using FastAPI's public documentation",
      examples: ["How do I make a query parameter required?", "How do I load a model at startup?", "How do I override a dependency in tests?"],
    },
    {
      name: "halden",
      display_name: "Halden Home Appliances",
      description: "Support documents for a fictional appliance company.",
      source: "Fictional documents written for this demo",
      source_url: null,
      license: "Fictional content, written for this project",
      license_url: null,
      notice: null,
      examples: ["How long is the warranty on the dishwasher pump motor?", "My washer shows error F02. What should I do?", "Can I return a dishwasher after it has been installed?"],
    },
  ],
};

const HALDEN_ANSWER = {
  answer: "The pump motor is covered for 5 years from delivery, parts only [1]. Labor is covered for the first 2 years [1].",
  citations: [
    {
      citation_id: 1,
      doc_id: "warranty-policy",
      doc_title: "Warranty Policy",
      section_path: "Warranty Policy > Coverage > Coverage periods",
      source: "docs/warranty-policy.md",
      excerpt: "Sealed components (dishwasher pump motor and washer drive motor): 5 years from the date of delivery, parts only.",
    },
  ],
  escalated: false,
  trace_id: "11111111-2222-3333-4444-555555555555",
};

const FASTAPI_ANSWER = {
  answer: "Do not declare a default value for the parameter [1].",
  citations: [
    {
      citation_id: 1,
      doc_id: "tutorial/query-params",
      doc_title: "Query Parameters",
      section_path: "Query Parameters > Required query parameters",
      source: "https://fastapi.tiangolo.com/tutorial/query-params/",
      excerpt: "✅ But when you want to make a query parameter required, you can just not declare any default value.",
    },
  ],
  escalated: false,
  trace_id: "66666666-7777-8888-9999-000000000000",
};

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body), headers: { "access-control-allow-origin": "*" } });

async function mockDatasets(page: Page) {
  await page.route(`${API}/datasets`, (route) => json(route, DATASETS));
}

async function mockChat(page: Page, handler: (body: { question: string; dataset: string }) => [unknown, number?]) {
  await page.route(`${API}/chat`, async (route) => {
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "content-type" } });
    const [body, status] = handler(route.request().postDataJSON());
    await json(route, body, status ?? 200);
  });
}

test.beforeEach(async ({ page }) => {
  await mockDatasets(page);
});

test("sends a question with Enter and shows the answer with citations", async ({ page }) => {
  const asked: string[] = [];
  await mockChat(page, (body) => {
    asked.push(`${body.dataset}:${body.question}`);
    return [HALDEN_ANSWER];
  });
  await page.goto("/chat");
  const input = page.getByLabel("Your question");
  await input.fill("How long is the pump motor warranty?");
  await input.press("Shift+Enter");
  await expect(input).toHaveValue("How long is the pump motor warranty?\n");
  await input.press("Enter");

  await expect(page.getByRole("article", { name: "Agent response" }).getByText("The pump motor is covered for 5 years")).toBeVisible();
  await expect(page.getByRole("button", { name: "Show source 1" })).toHaveCount(2);
  expect(asked).toEqual(["halden:How long is the pump motor warranty?"]);
  await expect(input).toHaveValue("");
});

test("send is disabled while a request is pending and a skeleton is shown", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  await page.route(`${API}/chat`, async (route) => {
    await gate;
    await json(route, HALDEN_ANSWER);
  });
  await page.goto("/chat");
  await page.getByLabel("Your question").fill("Warranty?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("answer-skeleton")).toBeVisible();
  await page.getByLabel("Your question").fill("Another question");
  await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
  release();
  await expect(page.getByRole("article", { name: "Agent response" }).getByText("The pump motor is covered for 5 years")).toBeVisible();
  await expect(page.getByTestId("answer-skeleton")).toHaveCount(0);
});

test("switching datasets starts a new conversation and loads its examples", async ({ page }) => {
  await mockChat(page, () => [HALDEN_ANSWER]);
  await page.goto("/chat");
  await page.getByRole("button", { name: "How long is the warranty on the dishwasher pump motor?" }).click();
  await expect(page.getByRole("article", { name: "Agent response" }).getByText("The pump motor is covered for 5 years")).toBeVisible();

  await page.getByLabel("Dataset").selectOption("fastapi");
  await expect(page).toHaveURL(/dataset=fastapi/);
  await expect(page.getByRole("article", { name: "Agent response" }).getByText("The pump motor is covered for 5 years")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "How do I make a query parameter required?" })).toBeVisible();
  await expect(page.getByText("Unofficial demo using FastAPI's public documentation")).toBeVisible();
  await expect(page.getByRole("link", { name: "MIT License, Copyright (c) 2018 Sebastián Ramírez" })).toBeVisible();
});

test("clicking a citation opens the source panel", async ({ page }) => {
  await mockChat(page, () => [HALDEN_ANSWER]);
  await page.goto("/chat");
  await page.getByRole("button", { name: "How long is the warranty on the dishwasher pump motor?" }).click();
  await page.getByRole("button", { name: "Show source 1" }).first().click();

  const panel = page.getByRole("region", { name: "Warranty Policy" });
  await expect(panel).toBeVisible();
  await expect(panel.getByText("Coverage > Coverage periods")).toBeVisible();
  await expect(panel.getByText("Sealed components (dishwasher pump motor")).toBeVisible();
  await expect(panel.getByRole("button", { name: "Show full document" })).toBeVisible();
});

test("a FastAPI citation links to the real docs page in a new tab", async ({ page }) => {
  await mockChat(page, () => [FASTAPI_ANSWER]);
  await page.goto("/chat?dataset=fastapi");
  await page.getByRole("button", { name: "How do I make a query parameter required?" }).click();
  await page.getByRole("button", { name: "Show source 1" }).click();
  const link = page.getByRole("link", { name: /Open on fastapi\.tiangolo\.com/ });
  await expect(link).toHaveAttribute("href", "https://fastapi.tiangolo.com/tutorial/query-params/");
  await expect(link).toHaveAttribute("target", "_blank");
  // Decorative emoji from the source docs are not shown
  const passage = page.getByText("But when you want to make a query parameter required");
  await expect(passage).toBeVisible();
  expect(await passage.textContent()).not.toContain("✅");
});

test("escalation renders as a handoff message, not an error", async ({ page }) => {
  await mockChat(page, () => [
    { answer: "I have handed your question to a human support agent.", citations: [], escalated: true, trace_id: "abcdef12-0000-0000-0000-000000000000" },
  ]);
  await page.goto("/chat");
  await page.getByLabel("Your question").fill("Who is the CEO?");
  await page.getByRole("button", { name: "Send" }).click();
  const escalation = page.getByTestId("escalation");
  await expect(escalation).toBeVisible();
  await expect(escalation.getByText("Handed to a human agent")).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByRole("status")).toHaveText("Your question was handed to a human support agent.");
});

test("an API failure shows an inline error with a working retry", async ({ page }) => {
  let calls = 0;
  await mockChat(page, () => {
    calls += 1;
    return calls === 1 ? [{ error: "model_unavailable", message: "The language model is not responding right now. Try again in a minute." }, 503] : [HALDEN_ANSWER];
  });
  await page.goto("/chat");
  await page.getByLabel("Your question").fill("Warranty?");
  await page.getByRole("button", { name: "Send" }).click();
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("The answer could not be loaded");
  await expect(alert).toContainText("Try again in a minute");
  await alert.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("article", { name: "Agent response" }).getByText("The pump motor is covered for 5 years")).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(calls).toBe(2);
});

test("rate limit and daily cap responses show a clear message", async ({ page }) => {
  let calls = 0;
  await mockChat(page, () => {
    calls += 1;
    return calls === 1
      ? [{ error: "rate_limited", message: "You have sent too many questions in the last hour. Try again later." }, 429]
      : [{ error: "daily_cap", message: "Demo limit reached, try again tomorrow." }, 429];
  });
  await page.goto("/chat");
  const input = page.getByLabel("Your question");
  await input.fill("First");
  await input.press("Enter");
  await expect(page.getByTestId("limit").first()).toContainText("too many questions in the last hour");
  await input.fill("Second");
  await input.press("Enter");
  await expect(page.getByTestId("limit").nth(1)).toContainText("Demo limit reached, try again tomorrow.");
  await expect(page.getByRole("button", { name: "Retry" })).toHaveCount(0);
});

test("on a phone the source panel opens as a bottom sheet and closes with Escape", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockChat(page, () => [HALDEN_ANSWER]);
  await page.goto("/chat");
  await page.getByRole("button", { name: "How long is the warranty on the dishwasher pump motor?" }).click();
  await page.getByRole("button", { name: "Show source 1" }).first().click();
  const sheet = page.getByRole("dialog");
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText("Warranty Policy")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Show source 1" }).first()).toBeFocused();
});
