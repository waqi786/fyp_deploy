import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./styles/tokens.css";
import "./styles/tailwind.css";

type SyncRegistration = ServiceWorkerRegistration & {
  sync?: {
    register(tag: string): Promise<void>;
  };
};

const isLocalDevelopmentHost = ["127.0.0.1", "localhost"].includes(window.location.hostname);

function renderRuntimeFallback(error: unknown) {
  const root = document.getElementById("root");
  if (!root) {
    return;
  }

  const message = error instanceof Error ? error.message : "Unknown startup error";
  root.innerHTML = `
    <div style="min-height:100vh;background:#020306;color:#fff;display:grid;place-items:center;padding:24px;font-family:Georgia,'Times New Roman',serif">
      <section style="max-width:720px;border:1px solid #ff6a00;border-radius:28px;background:#070b12;padding:32px;box-shadow:0 0 42px rgba(255,106,0,.18)">
        <p style="margin:0 0 10px;color:#ff6a00;letter-spacing:.22em;text-transform:uppercase;font-size:12px">Resora startup guard</p>
        <h1 style="margin:0 0 12px;font-size:34px;line-height:1.1">The app could not finish loading.</h1>
        <p style="margin:0 0 18px;color:#b7c3d7;line-height:1.7">Please press <strong>Ctrl + F5</strong>. If it still appears, restart the dev server. This guard prevents the blank black screen and shows the actual issue.</p>
        <pre style="white-space:pre-wrap;background:#000;border:1px solid #1a2a42;border-radius:16px;padding:16px;color:#ffb38a;overflow:auto">${message}</pre>
      </section>
    </div>
  `;
}

async function clearLocalServiceWorkerState() {
  if (!("serviceWorker" in navigator)) {
    return;
  }

  const registrations = await navigator.serviceWorker.getRegistrations();
  await Promise.all(registrations.map((registration) => registration.unregister()));

  if ("caches" in window) {
    const cacheKeys = await caches.keys();
    await Promise.all(cacheKeys.map((cacheKey) => caches.delete(cacheKey)));
  }
}

class ResoraRuntimeBoundary extends React.Component<React.PropsWithChildren, { error?: Error }> {
  state: { error?: Error } = {};

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <main className="min-h-screen bg-[#020306] p-6 text-white">
          <section className="mx-auto mt-20 max-w-3xl rounded-[28px] border border-[#ff6a00] bg-[#070b12] p-8 shadow-[0_0_42px_rgba(255,106,0,.18)]">
            <p className="text-xs uppercase tracking-[0.22em] text-[#ff6a00]">Resora runtime guard</p>
            <h1 className="mt-3 text-4xl">The screen failed to render.</h1>
            <p className="mt-4 text-[#b7c3d7]">
              Press Ctrl + F5 once. The app is showing this instead of a blank black page so we can fix the
              exact crash.
            </p>
            <pre className="mt-5 overflow-auto rounded-2xl border border-[#1a2a42] bg-black p-4 text-sm text-[#ffb38a]">
              {this.state.error.message}
            </pre>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}

function renderApp() {
  const root = document.getElementById("root");
  if (!root) {
    throw new Error("Root element #root was not found.");
  }

  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      <ResoraRuntimeBoundary>
        <App />
      </ResoraRuntimeBoundary>
    </React.StrictMode>,
  );
}

async function bootstrap() {
  if (isLocalDevelopmentHost) {
    await Promise.race([
      clearLocalServiceWorkerState(),
      new Promise((resolve) => {
        window.setTimeout(resolve, 1800);
      }),
    ]);
  }

  renderApp();
}

void bootstrap().catch(renderRuntimeFallback);

if ("serviceWorker" in navigator && !isLocalDevelopmentHost) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js")
      .then(async (registration) => {
        const syncRegistration = registration as SyncRegistration;
        if (syncRegistration.sync) {
          try {
            await syncRegistration.sync.register("resora-offline-sync");
          } catch {
            // Background sync is best-effort across browsers.
          }
        }
      })
      .catch(() => {});
  });
}
