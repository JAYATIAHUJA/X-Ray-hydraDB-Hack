import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "@fontsource-variable/source-sans-3";
import "@fontsource/instrument-serif/400.css";
import "@fontsource/instrument-serif/400-italic.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { Landing } from "./Landing";
import "./styles.css";

const root = document.getElementById("root");

if (root === null) {
  throw new Error("Missing root element");
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Render free tier cold-starts often fail the first request; retry so
      // engine status does not stick on Offline after a transient 502/timeout.
      retry: 3,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
      refetchOnWindowFocus: true
    }
  }
});

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      {window.location.pathname === "/app" ? <App /> : <Landing />}
    </QueryClientProvider>
  </StrictMode>
);
