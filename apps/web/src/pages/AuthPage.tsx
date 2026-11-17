import { FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { supabaseClient } from "../auth/supabase";

const wording = {
  en: {
    title: "Sign in to Resora",
    intro: "Sign in to use your private library, writing tools, teams, and Studio.",
    email: "Email",
    password: "Password",
    signIn: "Sign in",
    signUp: "Create account",
    switchToSignUp: "New to Resora? Create an account",
    switchToSignIn: "Already have an account? Sign in",
    missingConfig: "Sign-in is not configured for this deployment yet.",
    confirmation: "Check your email for the confirmation link, then return here to sign in.",
    unknownError: "We could not sign you in. Check your details and try again.",
    back: "Back to Resora",
    working: "Please wait...",
  },
} as const;

type Props = { interfaceLanguage: string };

export default function AuthPage({ interfaceLanguage }: Props) {
  const ui = wording.en;
  const [creatingAccount, setCreatingAccount] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as { from?: string } | null;
  const destination = state?.from?.startsWith("/") ? state.from : "/library";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    if (!supabaseClient) {
      setMessage(ui.missingConfig);
      return;
    }

    setBusy(true);
    try {
      if (creatingAccount) {
        const { data, error } = await supabaseClient.auth.signUp({
          email: email.trim(),
          password,
          options: { emailRedirectTo: window.location.origin + "/auth" },
        });
        if (error) throw error;
        if (data.session) navigate(destination, { replace: true });
        else setMessage(ui.confirmation);
      } else {
        const { error } = await supabaseClient.auth.signInWithPassword({ email: email.trim(), password });
        if (error) throw error;
        navigate(destination, { replace: true });
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : ui.unknownError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-[65vh] max-w-xl items-center px-5 py-10" dir="ltr" data-no-translate="" lang={interfaceLanguage}>
      <section className="w-full rounded-3xl border border-line bg-panel p-6 shadow-xl sm:p-9">
        <p className="resora-label">Resora</p>
        <h1 className="mt-2 text-3xl font-semibold text-text">{ui.title}</h1>
        <p className="mt-2 text-sm text-text-muted">{ui.intro}</p>
        <form className="mt-7 grid gap-4" onSubmit={submit}>
          <label className="grid gap-2 text-sm text-text">
            {ui.email}
            <input className="resora-input w-full" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label className="grid gap-2 text-sm text-text">
            {ui.password}
            <input className="resora-input w-full" type="password" autoComplete={creatingAccount ? "new-password" : "current-password"} minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          {message ? <p className="rounded-xl border border-line bg-surface p-3 text-sm text-text" role="status">{message}</p> : null}
          <button className="resora-button-primary w-full" type="submit" disabled={busy}>
            {busy ? ui.working : creatingAccount ? ui.signUp : ui.signIn}
          </button>
        </form>
        <button className="mt-4 w-full text-sm text-accent underline" type="button" onClick={() => { setCreatingAccount((value) => !value); setMessage(""); }}>
          {creatingAccount ? ui.switchToSignIn : ui.switchToSignUp}
        </button>
        <Link className="mt-6 inline-block text-sm text-text-muted underline" to="/">{ui.back}</Link>
      </section>
    </main>
  );
}
