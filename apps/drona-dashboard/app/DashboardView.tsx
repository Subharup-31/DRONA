"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { ChangeEvent, ComponentType, ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  Activity,
  ArrowLeft,
  BarChart3,
  CheckCircle2,
  Clock,
  Database,
  FileJson,
  FileUp,
  Gauge,
  Home,
  ShieldCheck,
  Upload,
  XCircle,
  Zap
} from "lucide-react";

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
  ingest_ms?: number;
  n_train?: number;
  n_eval?: number;
  n_signals?: number;
  mode?: string;
};

type BenchmarkReport = {
  mode?: string;
  aggregated: Record<string, number>;
  per_seed: SeedRun[];
  score?: { weighted_score?: number; max_automated?: number };
};

type RawReport = Partial<BenchmarkReport> & {
  report?: unknown;
  result?: unknown;
  data?: unknown;
  summary?: Record<string, number>;
  seeds?: unknown;
  runs?: unknown;
  incidents?: unknown;
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

interface Props {
  report: BenchmarkReport;
  reportSourceName?: string;
  debug: DebugReport | null;
  isFullPage?: boolean;
}

const emptyReport: BenchmarkReport = {
  aggregated: {
    "recall@5": 0,
    "precision@5_mean": 0,
    remediation_acc: 0,
    latency_p95_ms: 0,
    latency_mean_ms: 0,
    n: 0,
    n_seeds: 0
  },
  per_seed: []
};

export default function DashboardView({ report, reportSourceName = "report_improved.json", debug }: Props) {
  const [activeReport, setActiveReport] = useState<BenchmarkReport>(normalizeReport(report));
  const [sourceName, setSourceName] = useState(reportSourceName);
  const [uploadError, setUploadError] = useState("");
  const [selectedSeed, setSelectedSeed] = useState<number | "all">("all");
  const [reportRevision, setReportRevision] = useState(0);

  const agg = activeReport.aggregated || emptyReport.aggregated;
  const weighted = activeReport.score?.weighted_score ?? average([agg["recall@5"], agg["precision@5_mean"], agg.remediation_acc]);
  const seeds = activeReport.per_seed || [];
  const totalIncidents = seeds.reduce((sum, seed) => sum + (seed.per_incident?.length || 0), 0);
  const selectedRun = selectedSeed === "all" ? seeds[0] : seeds.find((seed) => seed.seed === selectedSeed) || seeds[0];
  const incidents = selectedSeed === "all" ? seeds.flatMap((seed) => seed.per_incident || []) : selectedRun?.per_incident || [];

  const chartData = useMemo(
    () =>
      seeds.map((seed) => ({
        seed: String(seed.seed),
        recall: pct(seed.summary["recall@5"]),
        precision: pct(seed.summary["precision@5_mean"]),
        remediation: pct(seed.summary.remediation_acc),
        latency: roundNumber(seed.summary.latency_p95_ms)
      })),
    [seeds]
  );

  const radarData = [
    { metric: "Recall", value: pct(agg["recall@5"]) },
    { metric: "Precision", value: pct(agg["precision@5_mean"]) },
    { metric: "Remediation", value: pct(agg.remediation_acc) },
    { metric: "Speed", value: Math.max(0, 100 - (agg.latency_p95_ms || 0) * 10) },
    { metric: "Score", value: pct(weighted) }
  ];

  const debugIncident = debug?.runs.flatMap((run) => run.incidents).find((incident) => !incident.recall || incident.precision < 1);

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const parsed = JSON.parse(await file.text()) as unknown;
      const nextReport = normalizeReport(parsed);
      if (!nextReport.per_seed.length && !hasUsefulMetrics(nextReport.aggregated)) {
        throw new Error("No benchmark data found.");
      }
      setActiveReport(nextReport);
      setSourceName(`${file.name} (uploaded ${new Date().toLocaleTimeString()})`);
      setUploadError("");
      setSelectedSeed("all");
      setReportRevision((revision) => revision + 1);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Could not read that JSON file.");
    } finally {
      event.target.value = "";
    }
  }

  return (
    <main className="min-h-screen bg-[#f7f7f2] text-[#101315]">
      <header className="sticky top-0 z-40 border-b border-black/10 bg-white/85 backdrop-blur-xl">
        <nav className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            <Link href="/" className="grid h-10 w-10 place-items-center rounded-full bg-[#101315] text-white">
              <Home className="h-5 w-5" />
            </Link>
            <div>
              <p className="text-xs font-black uppercase tracking-[0.22em] text-[#101315]/45">DRONA</p>
              <h1 className="text-lg font-black">Execution Dashboard</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/" className="hidden items-center gap-2 rounded-full border border-black/10 bg-white px-4 py-2 text-sm font-bold sm:inline-flex">
              <ArrowLeft className="h-4 w-4" />
              Landing
            </Link>
            <label htmlFor="report-upload" className="inline-flex cursor-pointer items-center gap-2 rounded-full bg-[#2a75ff] px-4 py-2 text-sm font-black text-white transition hover:bg-[#1d63df]">
              <Upload className="h-4 w-4" />
              Upload JSON
              <input id="report-upload" type="file" accept="application/json,.json" className="hidden" onChange={handleUpload} />
            </label>
          </div>
        </nav>
      </header>

      <section className="mx-auto max-w-7xl px-5 py-8">
        <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
          <div className="rounded-[2rem] bg-[#101315] p-6 text-white shadow-[0_24px_80px_rgba(16,19,21,0.18)] md:p-8">
            <div className="flex flex-col justify-between gap-6 md:flex-row md:items-start">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-xs font-black uppercase tracking-[0.18em] text-white/65">
                  <FileJson className="h-4 w-4" />
                  {sourceName}
                </div>
                <h2 className="mt-5 max-w-3xl text-4xl font-black tracking-tight md:text-6xl">Report health at a glance.</h2>
                <p className="mt-4 max-w-2xl leading-7 text-white/62">
                  Review the loaded execution report or upload a new JSON file to demonstrate aggregate performance, seed stability, latency, and incident-level outcomes.
                </p>
              </div>
              <div className="rounded-3xl bg-white p-5 text-[#101315]">
                <p className="text-sm font-black text-[#101315]/50">Weighted score</p>
                <p className="mt-2 text-5xl font-black">{weighted.toFixed(4)}</p>
                <div className="mt-3 flex flex-col gap-1 border-t border-black/5 pt-3">
                  <p className="text-xs font-bold text-[#101315]/70">
                    {weighted.toFixed(4)} / {activeReport.score?.max_automated?.toFixed(2) ?? "0.00"} max automated
                  </p>
                  <p className="text-xs font-black text-[#2a75ff]">
                    {activeReport.score?.max_automated 
                      ? `${((weighted / activeReport.score.max_automated) * 100).toFixed(1)}% of budget achieved`
                      : "No automated budget set"}
                  </p>
                  <p className="mt-1 text-[10px] leading-tight text-[#101315]/40 italic">
                    manual_context + manual_explain → panel-graded (not included)
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-[2rem] border border-black/10 bg-white p-6">
            <div className="flex items-center gap-3">
              <div className="grid h-12 w-12 place-items-center rounded-2xl bg-[#101315] text-white">
                <Database className="h-6 w-6" />
              </div>
              <div>
                <h3 className="font-black">Report source</h3>
                <p className="text-sm text-[#101315]/55">{sourceName}</p>
              </div>
            </div>
            <div className="mt-5 rounded-2xl bg-[#f1f3ee] p-4 text-sm leading-6 text-[#101315]/65">
              By default this page loads DRONA/report_improved.json. Uploading a JSON file replaces the dashboard data locally in the browser.
            </div>
            {uploadError && <p className="mt-3 rounded-2xl bg-red-50 p-3 text-sm font-bold text-red-700">{uploadError}</p>}
          </div>
        </div>

        <div key={`stats-${reportRevision}`} className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <StatCard icon={Activity} label="Recall @5" value={`${pct(agg["recall@5"]).toFixed(1)}%`} tone="blue" />
          <StatCard icon={Zap} label="Precision" value={`${pct(agg["precision@5_mean"]).toFixed(1)}%`} tone="dark" />
          <StatCard icon={ShieldCheck} label="Remediation" value={`${pct(agg.remediation_acc).toFixed(1)}%`} tone="green" />
          <StatCard icon={Clock} label="p95 latency" value={`${round(agg.latency_p95_ms)} ms`} tone="dark" />
          <StatCard icon={Gauge} label="Incidents" value={String(agg.n || totalIncidents)} tone="blue" />
        </div>

        <div className="mt-5 grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
          <Panel title="Seed Stability" icon={<BarChart3 className="h-5 w-5" />}>
            <div className="h-80">
              <ResponsiveContainer key={`seed-chart-${reportRevision}`} width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(16,19,21,0.08)" />
                  <XAxis dataKey="seed" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Bar dataKey="recall" fill="#2a75ff" radius={[8, 8, 0, 0]} />
                  <Bar dataKey="precision" fill="#101315" radius={[8, 8, 0, 0]} />
                  <Bar dataKey="remediation" fill="#28be94" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <Panel title="Metric Shape" icon={<Gauge className="h-5 w-5" />}>
            <div className="h-80">
              <ResponsiveContainer key={`radar-chart-${reportRevision}`} width="100%" height="100%">
                <RadarChart data={radarData}>
                  <PolarGrid stroke="rgba(16,19,21,0.12)" />
                  <PolarAngleAxis dataKey="metric" tick={{ fill: "#586066", fontSize: 12 }} />
                  <Radar dataKey="value" stroke="#2a75ff" fill="#2a75ff" fillOpacity={0.28} />
                  <Tooltip />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </Panel>
        </div>

        <div className="mt-5 grid gap-5 xl:grid-cols-[0.85fr_1.15fr]">
          <Panel title="Latency Trend" icon={<Clock className="h-5 w-5" />}>
            <div className="h-72">
              <ResponsiveContainer key={`latency-chart-${reportRevision}`} width="100%" height="100%">
                <AreaChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(16,19,21,0.08)" />
                  <XAxis dataKey="seed" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Area type="monotone" dataKey="latency" stroke="#2a75ff" fill="#2a75ff" fillOpacity={0.18} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <Panel title="Seed Reports" icon={<Database className="h-5 w-5" />}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead>
                  <tr className="border-b border-black/10 text-xs uppercase tracking-[0.18em] text-[#101315]/45">
                    <th className="py-3">Seed</th>
                    <th>Recall</th>
                    <th>Precision</th>
                    <th>Remediation</th>
                    <th>Latency</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {seeds.map((seed) => (
                    <tr
                      key={seed.seed}
                      className="cursor-pointer border-b border-black/5 transition hover:bg-[#f1f3ee]"
                      onClick={() => setSelectedSeed(seed.seed)}
                    >
                      <td className="py-4 font-mono font-black text-[#2a75ff]">{seed.seed}</td>
                      <td>{pct(seed.summary["recall@5"]).toFixed(0)}%</td>
                      <td>{pct(seed.summary["precision@5_mean"]).toFixed(0)}%</td>
                      <td>{pct(seed.summary.remediation_acc).toFixed(0)}%</td>
                      <td>{round(seed.summary.latency_p95_ms)} ms</td>
                      <td>
                        <StatusBadge ok={(seed.summary["recall@5"] || 0) >= 0.6} />
                      </td>
                    </tr>
                  ))}
                  {!seeds.length && (
                    <tr>
                      <td colSpan={6} className="py-8 text-center font-bold text-[#101315]/50">
                        No seed rows found in this report.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>

        <div className="mt-5 grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
          <Panel
            title="Incident Explorer"
            icon={<FileJson className="h-5 w-5" />}
            action={
              <select
                className="rounded-full border border-black/10 bg-white px-3 py-2 text-sm font-bold"
                value={selectedSeed}
                onChange={(event) => setSelectedSeed(event.target.value === "all" ? "all" : Number(event.target.value))}
              >
                <option value="all">All seeds</option>
                {seeds.map((seed) => (
                  <option key={seed.seed} value={seed.seed}>
                    Seed {seed.seed}
                  </option>
                ))}
              </select>
            }
          >
            <div className="max-h-[440px] overflow-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="sticky top-0 bg-white">
                  <tr className="border-b border-black/10 text-xs uppercase tracking-[0.18em] text-[#101315]/45">
                    <th className="py-3">Incident</th>
                    <th>Family hit</th>
                    <th>Precision</th>
                    <th>Remediation</th>
                    <th>Latency</th>
                  </tr>
                </thead>
                <tbody>
                  {incidents.map((incident) => (
                    <tr key={`${incident.incident_id}-${incident.latency_ms}`} className="border-b border-black/5">
                      <td className="py-4 font-mono font-black">{incident.incident_id}</td>
                      <td>{incident.correct_family_in_top_k ? <CheckCircle2 className="h-5 w-5 text-emerald-600" /> : <XCircle className="h-5 w-5 text-red-500" />}</td>
                      <td>{pct(incident.precision_at_k).toFixed(0)}%</td>
                      <td>{incident.remediation_matches ? "Matched" : "Missed"}</td>
                      <td>{round(incident.latency_ms)} ms</td>
                    </tr>
                  ))}
                  {!incidents.length && (
                    <tr>
                      <td colSpan={5} className="py-8 text-center font-bold text-[#101315]/50">
                        No incidents found in this report.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Debug Evidence" icon={<FileUp className="h-5 w-5" />}>
            {debugIncident ? (
              <div>
                <div className="rounded-2xl bg-[#101315] p-5 text-white">
                  <p className="text-xs font-black uppercase tracking-[0.2em] text-white/45">Focus incident</p>
                  <h3 className="mt-2 text-2xl font-black">{debugIncident.incident_id}</h3>
                  <p className="mt-3 text-sm leading-6 text-white/62">{debugIncident.explain || "Debug analysis is available for this incident."}</p>
                </div>
                <div className="mt-4 grid gap-3">
                  {(debugIncident.candidates || []).slice(0, 4).map((candidate) => (
                    <div key={`${candidate.rank}-${candidate.incident_id}`} className="rounded-2xl border border-black/10 p-4">
                      <div className="flex items-center justify-between">
                        <p className="font-mono text-sm font-black">{candidate.incident_id}</p>
                        <span className={`rounded-full px-2 py-1 text-xs font-black ${candidate.hit ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>
                          Rank {candidate.rank}
                        </span>
                      </div>
                      <p className="mt-2 text-sm text-[#101315]/55">Similarity {candidate.similarity.toFixed(3)} - family {candidate.family}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="rounded-2xl bg-[#f1f3ee] p-5 text-sm leading-7 text-[#101315]/65">
                No debug_analysis.json was found. The dashboard still shows aggregate, seed, and incident data from the report.
              </div>
            )}
          </Panel>
        </div>
      </section>
    </main>
  );
}

function Panel({
  title,
  icon,
  children,
  action
}: {
  title: string;
  icon: ReactNode;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="rounded-[2rem] border border-black/10 bg-white p-5 shadow-sm">
      <div className="mb-5 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-2xl bg-[#101315] text-white">{icon}</div>
          <h2 className="text-lg font-black">{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  tone
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
  tone: "blue" | "green" | "dark";
}) {
  const toneClass = {
    blue: "bg-[#2a75ff] text-white",
    green: "bg-[#28be94] text-white",
    dark: "bg-[#101315] text-white"
  }[tone];

  return (
    <div className="rounded-[1.5rem] border border-black/10 bg-white p-5">
      <div className={`grid h-11 w-11 place-items-center rounded-2xl ${toneClass}`}>
        <Icon className="h-5 w-5" />
      </div>
      <p className="mt-5 text-sm font-black text-[#101315]/50">{label}</p>
      <p className="mt-1 text-3xl font-black">{value}</p>
    </div>
  );
}

function StatusBadge({ ok }: { ok: boolean }) {
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-black ${ok ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
      {ok ? "Stable" : "Review"}
    </span>
  );
}

function normalizeReport(value: unknown): BenchmarkReport {
  const report = unwrapReport(value);
  if (!report) return emptyReport;
  const perSeed = normalizeSeeds(report);
  const aggregated = normalizeMetrics(report.aggregated || report.summary) || summarize(perSeed);
  return {
    mode: typeof report.mode === "string" ? report.mode : undefined,
    score: normalizeScore(report.score),
    aggregated,
    per_seed: perSeed
  };
}

function unwrapReport(value: unknown): RawReport | null {
  if (Array.isArray(value)) {
    return { per_seed: value as SeedRun[] };
  }
  if (!isRecord(value)) return null;
  const direct = value as RawReport;
  for (const key of ["report", "result", "results", "data"] as const) {
    const nested = direct[key];
    if (isRecord(nested) || Array.isArray(nested)) {
      const unwrapped = unwrapReport(nested);
      if (unwrapped) return unwrapped;
    }
  }
  return direct;
}

function normalizeSeeds(report: RawReport): SeedRun[] {
  const candidates = [report.per_seed, report.runs, report.seeds];
  const seedRows = candidates.find((c) => Array.isArray(c) && c.length > 0 && typeof c[0] === "object") as unknown[] | undefined;

  if (seedRows) {
    return seedRows.map(normalizeSeed).filter((seed): seed is SeedRun => Boolean(seed));
  }

  if (Array.isArray(report.incidents)) {
    return [
      normalizeSeed({
        seed: 0,
        per_incident: report.incidents
      })
    ].filter((seed): seed is SeedRun => Boolean(seed));
  }

  return [];
}

function normalizeSeed(value: unknown): SeedRun | null {
  if (!isRecord(value)) return null;
  const incidents = Array.isArray(value.per_incident)
    ? value.per_incident.map(normalizeIncident).filter((incident): incident is Incident => Boolean(incident))
    : [];
  const summary = normalizeMetrics(value.summary) || summarize([{ seed: numberFrom(value.seed), summary: {}, per_incident: incidents }]);

  return {
    seed: numberFrom(value.seed),
    summary,
    per_incident: incidents,
    ingest_ms: optionalNumber(value.ingest_ms),
    n_train: optionalNumber(value.n_train),
    n_eval: optionalNumber(value.n_eval),
    n_signals: optionalNumber(value.n_signals),
    mode: typeof value.mode === "string" ? value.mode : undefined
  };
}

function normalizeIncident(value: unknown): Incident | null {
  if (!isRecord(value)) return null;
  return {
    incident_id: stringFrom(value.incident_id || value.id || value.name, "unknown-incident"),
    correct_family_in_top_k: booleanFrom(value.correct_family_in_top_k ?? value.recall ?? value.hit),
    precision_at_k: numberFrom(value.precision_at_k ?? value.precision),
    remediation_matches: booleanFrom(value.remediation_matches ?? value.remediation_match ?? value.remediation),
    latency_ms: numberFrom(value.latency_ms ?? value.latency)
  };
}

function normalizeMetrics(value: unknown): Record<string, number> | null {
  if (!isRecord(value)) return null;
  return {
    "recall@5": numberFrom(value["recall@5"] ?? value.recall),
    "precision@5_mean": numberFrom(value["precision@5_mean"] ?? value.precision),
    remediation_acc: numberFrom(value.remediation_acc ?? value.remediation),
    latency_p95_ms: numberFrom(value.latency_p95_ms ?? value.p95_latency_ms ?? value.latency),
    latency_mean_ms: numberFrom(value.latency_mean_ms),
    n_seeds: numberFrom(value.n_seeds),
    n: numberFrom(value.n)
  };
}

function normalizeScore(value: unknown): BenchmarkReport["score"] {
  if (!isRecord(value)) return undefined;
  return {
    weighted_score: optionalNumber(value.weighted_score),
    max_automated: optionalNumber(value.max_automated)
  };
}

function hasUsefulMetrics(metrics: Record<string, number>) {
  return Object.values(metrics).some((value) => value > 0);
}

function summarize(seeds: SeedRun[]): Record<string, number> {
  const rows = seeds.flatMap((seed) => seed.per_incident || []);
  if (!rows.length) return emptyReport.aggregated;
  return {
    "recall@5": average(rows.map((row) => (row.correct_family_in_top_k ? 1 : 0))),
    "precision@5_mean": average(rows.map((row) => row.precision_at_k)),
    remediation_acc: average(rows.map((row) => (row.remediation_matches ? 1 : 0))),
    latency_p95_ms: percentile(rows.map((row) => row.latency_ms), 0.95),
    latency_mean_ms: average(rows.map((row) => row.latency_ms)),
    n_seeds: seeds.length,
    n: rows.length
  };
}

function pct(value: number | undefined) {
  return (value || 0) * 100;
}

function round(value: number | undefined) {
  return roundNumber(value).toFixed(2);
}

function roundNumber(value: number | undefined) {
  return Number((value || 0).toFixed(2));
}

function average(values: Array<number | undefined>) {
  const usable = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!usable.length) return 0;
  return usable.reduce((sum, value) => sum + value, 0) / usable.length;
}

function percentile(values: number[], p: number) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) return 0;
  const index = Math.min(sorted.length - 1, Math.ceil(sorted.length * p) - 1);
  return sorted[index];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function numberFrom(value: unknown) {
  const parsed = typeof value === "number" ? value : typeof value === "string" ? Number(value) : 0;
  return Number.isFinite(parsed) ? parsed : 0;
}

function optionalNumber(value: unknown) {
  const parsed = numberFrom(value);
  return parsed || parsed === 0 ? parsed : undefined;
}

function booleanFrom(value: unknown) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value > 0;
  if (typeof value === "string") return ["true", "yes", "matched", "hit", "1"].includes(value.toLowerCase());
  return false;
}

function stringFrom(value: unknown, fallback: string) {
  return typeof value === "string" && value.trim() ? value : fallback;
}
