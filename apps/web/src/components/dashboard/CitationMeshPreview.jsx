const meshNodes = [
  { id: "seed", label: "Seed paper", tone: "gold" },
  { id: "bridge", label: "Bridge node", tone: "teal" },
  { id: "method", label: "Method cluster", tone: "neutral" },
  { id: "dataset", label: "Dataset cluster", tone: "coral" },
];

const coordinates = {
  seed: [72, 128],
  bridge: [172, 74],
  method: [274, 74],
  dataset: [274, 180],
};

const tones = {
  gold: { fill: "#351400", stroke: "#FF6A00", text: "#FFE0C2" },
  teal: { fill: "#04283A", stroke: "#00D5FF", text: "#C5F7FF" },
  coral: { fill: "#052914", stroke: "#39FF88", text: "#D9FFE8" },
  neutral: { fill: "#360512", stroke: "#FF174D", text: "#FFD4DE" },
};

export function CitationMeshPreview() {
  return (
    <article className="panel-surface overflow-hidden">
      <div className="border-b border-border px-5 py-4">
        <p className="resora-label">Citation mesh</p>
        <h3 className="mt-2 font-display text-[22px] font-normal text-text">Bridge nodes, method groups, and dataset links</h3>
      </div>

      <div className="grid gap-0 xl:grid-cols-[280px_minmax(0,1fr)]">
        <div className="border-b border-border px-5 py-5 xl:border-b-0 xl:border-r">
          <div className="space-y-3">
            {meshNodes.map((node) => (
              <div key={node.id} className="rounded-[10px] border border-border bg-panel px-4 py-3">
                <p className="resora-label">{node.id}</p>
                <p className="mt-2 text-[13px] text-text">{node.label}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="px-5 py-5">
          <div className="rounded-[10px] border border-border bg-panel p-4">
            <svg viewBox="0 0 340 240" className="h-[260px] w-full">
              <line x1="72" y1="128" x2="172" y2="74" stroke="#36577E" strokeWidth="2" />
              <line x1="172" y1="74" x2="274" y2="74" stroke="#36577E" strokeWidth="2" />
              <line x1="172" y1="74" x2="274" y2="180" stroke="#36577E" strokeWidth="2" />
              {meshNodes.map((node) => {
                const [x, y] = coordinates[node.id];
                const tone = tones[node.tone];
                return (
                  <g key={node.id}>
                    <circle cx={x} cy={y} r="24" fill={tone.fill} stroke={tone.stroke} strokeWidth="2" />
                    <text x={x} y={y + 4} textAnchor="middle" fill={tone.text} fontSize="10" fontFamily="Consolas, monospace">
                      {node.id.toUpperCase().slice(0, 4)}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        </div>
      </div>
    </article>
  );
}
