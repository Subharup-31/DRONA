import fs from "node:fs";
import path from "node:path";

type Incident = {
  incident_id: string;
  correct_family_in_top_k: boolean;
  precision_at_k: number;
  remediation_matches: boolean;
  latency_ms: number;
};

type SeedRun = {
  seed: number;
  summary: Record<string, number>;
  per_incident: Incident[];
};

type BenchmarkReport = {
  aggregated: Record<string, number>;
  per_seed: SeedRun[];
  score?: { weighted_score?: number; max_automated?: number };
};

type DebugCandidate = {
  rank: number;
  incident_id: string;
  family: string;
  hit: boolean;
  similarity: number;
  components?: Record<string, string | number | boolean>;
};

type DebugIncident = {
  incident_id: string;
  family: number;
  recall: boolean;
  precision: number;
  latency_ms: number;
  candidates: DebugCandidate[];
  related_events?: Array<Record<string, unknown>>;
  explain?: string;
};

type DebugReport = {
  runs: Array<{ seed: number; incidents: DebugIncident[] }>;
};

const root = path.resolve(process.cwd(), "..", "..");
const workspace = path.resolve(root, "..");

function readJson<T>(candidates: string[]): T | null {
  for (const candidate of candidates) {
    try {
      if (fs.existsSync(candidate)) {
        return JSON.parse(fs.readFileSync(candidate, "utf8")) as T;
      }
    } catch {
      return null;
    }
  }
  return null;
}

function loadReport(): BenchmarkReport {
  return (
    readJson<BenchmarkReport>([
      process.env.DRONA_REPORT_PATH || "",
      path.join(root, "report_improved.json"),
      path.join(root, "report.json"),
      path.join(workspace, "Anvil-P-E", "bench-p02-context", "report_improved.json")
    ]) || {
      aggregated: {
        "recall@5": 0,
        "precision@5_mean": 0,
        remediation_acc: 0,
        latency_p95_ms: 0
      },
      per_seed: []
    }
  );
}

function loadDebug(): DebugReport | null {
  return readJson<DebugReport>([
    process.env.DRONA_DEBUG_PATH || "",
    path.join(workspace, "Anvil-P-E", "bench-p02-context", "debug_analysis.json")
  ]);
}

function pct(value = 0) {
  return `${Math.round(value * 100)}%`;
}

function familyOf(id: string) {
  return id.includes("-") ? id.split("-").at(-1) || "?" : "?";
}

function metricColor(value: number) {
  if (value >= 0.8) return "good";
  if (value >= 0.45) return "warn";
  return "bad";
}

export default function Page() {
  const report = loadReport();
  const debug = loadDebug();
  const agg = report.aggregated;
  const weighted = report.score?.weighted_score ?? 0;
  const falsePositives = debug?.runs
    .flatMap((run) =>
      run.incidents
        .filter((incident) => incident.precision < 1)
        .map((incident) => ({ ...incident, seed: run.seed }))
    )
    .slice(0, 8);
  const firstDebug = falsePositives?.[0];

  return (
    <main>
      <section className="hero">
        <nav>
          <div className="brand">DRONA</div>
          <div className="navPills">
            <span>DuckDB temporal core</span>
            <span>Vector fingerprint sidecar</span>
            <span>Two-stage reranker</span>
          </div>
        </nav>

        <div className="heroGrid">
          <div className="heroCopy">
            <p className="eyebrow">Persistent Context Benchmark</p>
            <h1>Incident memory that explains why it remembers.</h1>
            <p className="lede">
              Live benchmark telemetry, false-positive analysis, causal replay,
              and behavioral fingerprint vectors in one command center.
            </p>
          </div>

          <div className="scorePanel" aria-label="Benchmark score overview">
            <div className="scoreHeader">
              <span>Automated Score</span>
              <strong>{weighted.toFixed(3)}</strong>
            </div>
            <Metric label="Recall @5" value={agg["recall@5"] ?? 0} />
            <Metric label="Precision @5" value={agg["precision@5_mean"] ?? 0} />
            <Metric label="Remediation" value={agg.remediation_acc ?? 0} />
            <div className="latencyLine">
              <span>p95 latency</span>
              <strong>{(agg.latency_p95_ms ?? 0).toFixed(2)} ms</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="band">
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Seed Health</p>
            <h2>Aggregate score map</h2>
          </div>
          <p>
            Each row is one seed. The heatmap makes regressions visible before
            they hide inside averages.
          </p>
        </div>
        <div className="heatmap">
          <div className="heatHead">Seed</div>
          <div className="heatHead">Recall</div>
          <div className="heatHead">Precision</div>
          <div className="heatHead">Remediation</div>
          <div className="heatHead">Latency</div>
          {report.per_seed.map((seed) => (
            <SeedRow key={seed.seed} seed={seed} />
          ))}
        </div>
      </section>

      <section className="analysisGrid">
        <div className="panel">
          <div className="sectionHeader compact">
            <div>
              <p className="eyebrow">False Positive Explorer</p>
              <h2>Top noisy incidents</h2>
            </div>
          </div>
          <div className="incidentList">
            {(falsePositives || []).map((incident) => (
              <div className="incidentRow" key={`${incident.seed}-${incident.incident_id}`}>
                <span>Seed {incident.seed}</span>
                <strong>{incident.incident_id}</strong>
                <em>F{incident.family}</em>
                <b className={metricColor(incident.precision)}>{pct(incident.precision)}</b>
              </div>
            ))}
            {!falsePositives?.length && (
              <div className="empty">Run debug_evaluator.py to populate candidate traces.</div>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="sectionHeader compact">
            <div>
              <p className="eyebrow">Why Matched</p>
              <h2>Candidate score components</h2>
            </div>
          </div>
          <div className="candidateStack">
            {(firstDebug?.candidates || []).map((candidate) => (
              <div className="candidate" key={candidate.incident_id}>
                <div className="candidateTop">
                  <span>#{candidate.rank}</span>
                  <strong>{candidate.incident_id}</strong>
                  <em className={candidate.hit ? "goodText" : "badText"}>
                    {candidate.hit ? "correct" : "false positive"}
                  </em>
                </div>
                <div className="componentGrid">
                  {Object.entries(candidate.components || {}).slice(0, 5).map(([key, value]) => (
                    <span key={key}>
                      {key}
                      <b>{String(value)}</b>
                    </span>
                  ))}
                </div>
              </div>
            ))}
            {!firstDebug && (
              <div className="empty">No debug candidates loaded yet.</div>
            )}
          </div>
        </div>
      </section>

      <section className="band">
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Incident Replay</p>
            <h2>Causal timeline</h2>
          </div>
          <p>
            The timeline uses the debug run context so judges can inspect the
            evidence behind a match.
          </p>
        </div>
        <div className="timeline">
          {(firstDebug?.related_events || []).slice(0, 8).map((event, index) => (
            <div className="timelineItem" key={`${event.ts}-${index}`}>
              <span>{String(event.ts || "")}</span>
              <strong>{String(event.kind || "event")}</strong>
              <p>{String(event.service || event.svc || event.msg || event.name || "")}</p>
            </div>
          ))}
          {!firstDebug?.related_events?.length && (
            <div className="empty">No replay loaded yet.</div>
          )}
        </div>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metricLine">
      <span>{label}</span>
      <div className="meter">
        <i className={metricColor(value)} style={{ width: pct(value) }} />
      </div>
      <strong>{pct(value)}</strong>
    </div>
  );
}

function SeedRow({ seed }: { seed: SeedRun }) {
  const recall = seed.summary["recall@5"] ?? 0;
  const precision = seed.summary["precision@5_mean"] ?? 0;
  const remediation = seed.summary.remediation_acc ?? 0;
  const latency = seed.summary.latency_p95_ms ?? 0;
  return (
    <>
      <div className="heatSeed">{seed.seed}</div>
      <HeatCell value={recall} label={pct(recall)} />
      <HeatCell value={precision} label={pct(precision)} />
      <HeatCell value={remediation} label={pct(remediation)} />
      <div className="heatCell neutral">{latency.toFixed(1)} ms</div>
    </>
  );
}

function HeatCell({ value, label }: { value: number; label: string }) {
  return <div className={`heatCell ${metricColor(value)}`}>{label}</div>;
}
