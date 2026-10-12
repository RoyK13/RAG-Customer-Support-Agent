import { MotionConfig } from "motion/react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { Page } from "./components/Layout";
import "./index.css";
import Chat from "./pages/Chat";
import Landing from "./pages/Landing";
import { Privacy, Terms } from "./pages/Legal";

function NotFound() {
  return (
    <Page>
      <div className="mx-auto max-w-2xl px-4 py-16 sm:px-6">
        <h1 className="text-2xl font-semibold text-fg">Page not found</h1>
        <p className="mt-2 text-fg-muted">
          This page does not exist. Go to the <Link to="/">home page</Link> or the <Link to="/chat">demo</Link>.
        </p>
      </div>
    </Page>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </MotionConfig>
  </StrictMode>,
);
