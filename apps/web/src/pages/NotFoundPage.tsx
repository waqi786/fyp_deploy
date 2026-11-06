import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section className="mx-auto flex min-h-[60vh] max-w-3xl flex-col items-start justify-center gap-4 px-6 py-16">
      <p className="text-sm uppercase tracking-[0.3em] text-gold-text">404</p>
      <h1 className="text-4xl font-semibold text-white">This route is not available yet.</h1>
      <p className="max-w-xl text-slate-300">
        The Phase 0 router skeleton is in place. Continue from the dashboard while the remaining product pages are
        wired in.
      </p>
      <Link
        className="rounded-full bg-white px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-slate-200"
        to="/dashboard"
      >
        Back to Dashboard
      </Link>
    </section>
  );
}
