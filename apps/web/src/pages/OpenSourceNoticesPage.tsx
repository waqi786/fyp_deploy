import { useEffect, useState } from "react";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";
type Pack = { package: string; version: string; license: string; license_evidence: string; source: string; commercial_use: string };
type ModelRecord = { model?: string; converted_repository?: string; key?: string; pair?: string; revision?: string; license?: string; license_source?: string; license_url?: string; quantization?: string; attribution?: string };
type Inventory = { status?: string; installed_packs?: Pack[]; installed_pairs?: string[]; m2m100?: ModelRecord; opus_models?: ModelRecord[] };

export function OpenSourceNoticesPage() {
  const [inventory, setInventory] = useState<Inventory | null>(null);
  useEffect(() => {
    let active = true;
    void fetch(`${apiBaseUrl}/search/translation/licenses`)
      .then((response) => response.ok ? response.json() as Promise<Inventory> : null)
      .then((value) => { if (active && value) setInventory(value); })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  const packs = inventory?.installed_packs ?? [];
  const models = [inventory?.m2m100, ...(inventory?.opus_models ?? [])].filter((item): item is ModelRecord => Boolean(item));
  return (
    <main className="mx-auto w-full max-w-5xl px-5 py-8 text-text sm:px-8">
      <header className="mb-8">
        <p className="resora-label">Transparency</p>
        <h1 className="mt-2 text-3xl font-semibold">Open-source notices</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-text-dim">
          Resora uses local translation software and downloadable model weights. Each model is listed with its own license and source.
        </p>
      </header>

      <section className="mb-6 rounded-2xl border border-border bg-panel p-5">
        <h2 className="text-xl font-semibold">Translation engine</h2>
        <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
          <div><dt className="text-text-faint">Argos Translate</dt><dd className="mt-1">MIT library; individual model sources need review</dd></div>
          <div><dt className="text-text-faint">M2M-100 418M</dt><dd className="mt-1">MIT model, CTranslate2 int8</dd></div>
          <div><dt className="text-text-faint">OPUS-MT</dt><dd className="mt-1">License checked per model; approved licenses and attribution are recorded</dd></div>
          <div><dt className="text-text-faint">Installed inventory</dt><dd className="mt-1">{inventory?.status === "translator_unavailable" ? "Translator service unavailable" : inventory?.status === "models_missing" ? "Models not downloaded" : `${packs.length} Argos packs reported`}</dd></div>
        </dl>
        <p className="mt-4 text-xs leading-5 text-text-faint">
          Argos packages do not expose a reliable per-pack license in the index. Unreviewed packs are excluded. M2M and OPUS model details appear in the live inventory when downloaded.
        </p>
      </section>

      <section className="overflow-hidden rounded-2xl border border-border bg-panel">
        <div className="border-b border-border px-5 py-4"><h2 className="text-xl font-semibold">Downloaded model licenses</h2></div>
        {models.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-left text-sm">
              <thead><tr className="bg-panel-raised text-xs uppercase tracking-wide text-text-faint"><th className="px-5 py-3">Model</th><th className="px-5 py-3">Pair</th><th className="px-5 py-3">License</th><th className="px-5 py-3">Revision</th><th className="px-5 py-3">Source</th></tr></thead>
              <tbody>{models.map((model) => <tr key={model.key ?? model.model} className="border-t border-border"><td className="px-5 py-3"><span className="font-medium">{model.model ?? model.key}</span>{model.attribution ? <p className="mt-1 max-w-sm text-xs leading-5 text-text-faint">{model.attribution}</p> : null}</td><td className="px-5 py-3">{model.pair ?? model.quantization ?? "M2M-100 shared model"}</td><td className="px-5 py-3">{model.license ?? "Not reported"}</td><td className="px-5 py-3 font-mono text-xs">{model.revision ?? "Pinned model card"}</td><td className="space-x-3 px-5 py-3">{model.license_source ? <a className="text-green-text underline" href={model.license_source} target="_blank" rel="noreferrer">Model card</a> : null}{model.license_url ? <a className="text-green-text underline" href={model.license_url} target="_blank" rel="noreferrer">License</a> : null}</td></tr>)}</tbody>
            </table>
          </div>
        ) : <p className="px-5 py-6 text-sm text-text-dim">No local model licenses have been loaded yet.</p>}
      </section>

      <section className="mt-6 overflow-hidden rounded-2xl border border-border bg-panel">
        <div className="border-b border-border px-5 py-4"><h2 className="text-xl font-semibold">Installed translation packs</h2></div>
        {packs.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px] border-collapse text-left text-sm">
              <thead><tr className="bg-panel-raised text-xs uppercase tracking-wide text-text-faint"><th className="px-5 py-3">Language pair</th><th className="px-5 py-3">Version</th><th className="px-5 py-3">License basis</th><th className="px-5 py-3">Sources</th></tr></thead>
              <tbody>{packs.map((pack) => <tr key={`${pack.package}-${pack.version}`} className="border-t border-border"><td className="px-5 py-3">{pack.package}</td><td className="px-5 py-3">{pack.version}</td><td className="px-5 py-3">{pack.license}</td><td className="space-x-3 px-5 py-3"><a className="text-green-text underline" href={pack.source} target="_blank" rel="noreferrer">Package</a><a className="text-green-text underline" href={pack.license_evidence} target="_blank" rel="noreferrer">License evidence</a></td></tr>)}</tbody>
            </table>
          </div>
        ) : <p className="px-5 py-6 text-sm text-text-dim">The installed model inventory is not available yet. Start the local translator to load its package list.</p>}
        <nav className="flex flex-wrap gap-4 border-t border-border px-5 py-4 text-sm">
          <a className="text-green-text underline" href="https://github.com/argosopentech/argos-translate/blob/master/LICENSE" target="_blank" rel="noreferrer">Argos Translate license</a>
          <a className="text-green-text underline" href="https://github.com/argosopentech/argos-translate/issues/533" target="_blank" rel="noreferrer">Model license statement</a>
          <a className="text-green-text underline" href="https://github.com/argosopentech/argospm-index/blob/main/LICENSE" target="_blank" rel="noreferrer">Package index license</a>
        </nav>
      </section>
    </main>
  );
}
