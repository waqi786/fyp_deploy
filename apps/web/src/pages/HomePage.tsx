import { useState } from "react";
import { useNavigate } from "react-router-dom";

const graphNodes = [
  [120, 190], [210, 110], [340, 160], [270, 290], [185, 450], [75, 540], [300, 570],
  [1320, 180], [1230, 100], [1100, 150], [1170, 290], [1255, 450], [1365, 550], [1140, 580],
];
const graphEdges = [
  [0, 1], [1, 2], [1, 3], [0, 3], [3, 4], [4, 5], [4, 6],
  [7, 8], [8, 9], [8, 10], [7, 10], [10, 11], [11, 12], [11, 13],
];

function ResearchNetwork() {
  return (
    <svg className="resora-home-network" viewBox="0 0 1440 680" preserveAspectRatio="none" aria-hidden="true" focusable="false">
      <g className="resora-home-network-lines">
        {graphEdges.map(([from, to]) => (
          <line key={String(from) + "-" + to} x1={graphNodes[from][0]} y1={graphNodes[from][1]} x2={graphNodes[to][0]} y2={graphNodes[to][1]} />
        ))}
      </g>
      <g className="resora-home-network-nodes">
        {graphNodes.map(([cx, cy], index) => (
          <g key={String(cx) + "-" + cy} className={index === 1 || index === 8 ? "is-featured" : ""}>
            <circle cx={cx} cy={cy} r="5" />
            {(index === 1 || index === 8) && <circle className="resora-home-node-core" cx={cx} cy={cy} r="2" />}
          </g>
        ))}
      </g>
    </svg>
  );
}

export function HomePage() {
  const [query, setQuery] = useState("");
  const navigate = useNavigate();

  function search(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = query.trim();
    if (value) navigate("/search?q=" + encodeURIComponent(value));
  }

  return (
    <section className="resora-home">
      <ResearchNetwork />
      <div className="resora-home-main">
        <h1>Research, made <em>clear.</em></h1>
        <form className="resora-home-search" onSubmit={search} role="search">
          <label className="sr-only" htmlFor="research-query">Ask about research</label>
          <span className="resora-home-search-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" focusable="false">
              <circle cx="10.8" cy="10.8" r="6.3" />
              <path d="m15.5 15.5 4.2 4.2" />
            </svg>
          </span>
          <input id="research-query" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ask anything about research" />
          <button type="submit" aria-label="Search research" disabled={!query.trim()}>
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h13M13 6l6 6-6 6" /></svg>
          </button>
        </form>
      </div>
    </section>
  );
}