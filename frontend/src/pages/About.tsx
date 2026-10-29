/** About page: project summary + pipeline diagram + tech list. */

function PipelineDiagram() {
  return (
    <svg viewBox="0 0 520 60" className="w-full max-w-[520px] h-auto">
      <g stroke="hsl(var(--border))" strokeWidth="1">
        <rect x="10" y="18" width="90" height="24" rx="4" fill="hsl(var(--subtle))" />
        <rect x="115" y="18" width="90" height="24" rx="4" fill="hsl(var(--subtle))" />
        <rect x="220" y="18" width="90" height="24" rx="4" fill="hsl(var(--subtle))" />
        <rect x="325" y="18" width="90" height="24" rx="4" fill="hsl(var(--subtle))" />
        <rect x="430" y="18" width="80" height="24" rx="4" fill="hsl(var(--subtle))" />
      </g>
      <g fill="hsl(var(--text))" fontSize="10" fontFamily="IBM Plex Sans, sans-serif">
        <text x="55" y="33" textAnchor="middle">Preprocess</text>
        <text x="160" y="33" textAnchor="middle">Regex</text>
        <text x="265" y="33" textAnchor="middle">SBERT+LogReg</text>
        <text x="370" y="33" textAnchor="middle">DBSCAN</text>
        <text x="470" y="33" textAnchor="middle">LLM</text>
      </g>
      <g stroke="hsl(var(--muted))" strokeWidth="1" markerEnd="url(#arrow)">
        <line x1="100" y1="30" x2="115" y2="30" />
        <line x1="205" y1="30" x2="220" y2="30" />
        <line x1="310" y1="30" x2="325" y2="30" />
        <line x1="415" y1="30" x2="430" y2="30" />
      </g>
      <defs>
        <marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L0,6 L6,3 z" fill="hsl(var(--muted))" />
        </marker>
      </defs>
    </svg>
  );
}

export default function AboutPage() {
  return (
    <div className="max-w-3xl space-y-4 text-[13px] leading-relaxed">
      <div>
        <h2 className="text-[16px] font-medium">SmartLog AI</h2>
        <p className="text-muted">Intelligent Incident Classification using Hybrid AI for Enterprise Log Monitoring</p>
      </div>
      <p>
        SmartLog AI classifies enterprise logs (CRM, HRMS, billing, cloud/server) into incident
        categories in real time. A hybrid pipeline short-circuits at the first confident stage:
        regex rules for known patterns, Sentence-BERT embeddings + Logistic Regression for the
        rest, DBSCAN clustering for unknown anomalies, and an LLM fallback at the very end.
      </p>
      <div>
        <div className="text-[15px] font-medium mb-2">Pipeline</div>
        <PipelineDiagram />
        <ol className="list-decimal ml-5 space-y-1 mt-2">
          <li>Preprocess — strip timestamps, IDs, IPs, hex, numbers and symbols</li>
          <li>Regex classifier — known patterns, high confidence</li>
          <li>SBERT + Logistic Regression — accepted at ≥ 0.70 probability</li>
          <li>DBSCAN — noise points become unknown anomalies; clusters feed the Anomaly Explorer</li>
          <li>Claude LLM fallback — few-shot, strict JSON, degrades to Unknown if unreachable</li>
        </ol>
      </div>
      <div>
        <div className="text-[15px] font-medium mb-1">Tech</div>
        <p className="text-muted">
          React, TypeScript, Vite, Tailwind, shadcn/ui, Recharts, React Router, TanStack Query,
          lucide-react · FastAPI, SQLAlchemy, SQLite, WebSockets · sentence-transformers
          (all-MiniLM-L6-v2), scikit-learn, joblib · Anthropic Claude API
        </p>
      </div>
      <p className="text-muted">RV College of Engineering · Experiential Learning Phase I</p>
    </div>
  );
}
