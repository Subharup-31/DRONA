import fs from "node:fs";
import path from "node:path";
import DashboardView from "../DashboardView";

export const dynamic = "force-dynamic";
export const revalidate = 0;

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

type LoadedReport = {
  data: BenchmarkReport;
  sourceName: string;
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

function findWorkspace(startDir: string): string {
  let curr = startDir;
  while (curr !== path.parse(curr).root) {
    if (fs.existsSync(path.join(curr, "Anvil-P-E"))) {
      return curr;
    }
    curr = path.dirname(curr);
  }
  return startDir; // Fallback
}

const workspace = findWorkspace(process.cwd());
const root = path.join(workspace, "DRONA");

function readJson<T>(candidates: Array<{ path: string; sourceName: string }>): { data: T; sourceName: string } | null {
  for (const candidate of candidates) {
    try {
      if (candidate.path && fs.existsSync(candidate.path)) {
        const content = fs.readFileSync(candidate.path, "utf8");
        return {
          data: JSON.parse(content) as T,
          sourceName: candidate.sourceName
        };
      }
    } catch (e) {
      console.error(`Failed to load ${candidate.path}:`, e);
      // Continue to next candidate
    }
  }
  return null;
}

function loadReport(): LoadedReport {
  const benchDir = path.join(workspace, "Anvil-P-E", "bench-p02-context");
  const candidates: Array<{ path: string; sourceName: string }> = [
    { path: process.env.DRONA_REPORT_PATH || "", sourceName: process.env.DRONA_REPORT_PATH ? path.basename(process.env.DRONA_REPORT_PATH) : "" }
  ];

  // Auto-discover the latest report in the bench directory (Highest priority after ENV)
  try {
    if (fs.existsSync(benchDir)) {
      const files = fs.readdirSync(benchDir);
      const reportFiles = files
        .filter((f) => f.startsWith("report") && f.endsWith(".json"))
        .map((f) => ({
          name: f,
          path: path.join(benchDir, f),
          mtime: fs.statSync(path.join(benchDir, f)).mtimeMs
        }))
        .sort((a, b) => b.mtime - a.mtime);

      for (const rf of reportFiles) {
        candidates.push({ path: rf.path, sourceName: `Auto: ${rf.name}` });
      }
    }
  } catch (e) {
    console.error("Error scanning for reports:", e);
  }

  // Fallback to project root or specific fallbacks
  candidates.push({ path: path.join(root, "report_improved.json"), sourceName: "DRONA report_improved.json" });
  candidates.push({ path: path.join(root, "report.json"), sourceName: "DRONA report.json" });
  candidates.push({ path: path.join(benchDir, "report_improved.json"), sourceName: "Anvil-P-E report_improved.json" });

  return (
    readJson<BenchmarkReport>(candidates) || {
      data: {
        aggregated: {
          "recall@5": 0,
          "precision@5_mean": 0,
          remediation_acc: 0,
          latency_p95_ms: 0
        },
        per_seed: []
      },
      sourceName: "No report found"
    }
  );
}

function loadDebug(): DebugReport | null {
  return readJson<DebugReport>([
    { path: process.env.DRONA_DEBUG_PATH || "", sourceName: process.env.DRONA_DEBUG_PATH ? path.basename(process.env.DRONA_DEBUG_PATH) : "" },
    { path: path.join(workspace, "Anvil-P-E", "bench-p02-context", "debug_analysis.json"), sourceName: "debug_analysis.json" }
  ])?.data || null;
}

export default function DashboardPage() {
  const loadedReport = loadReport();
  const debug = loadDebug();

  return <DashboardView report={loadedReport.data} reportSourceName={loadedReport.sourceName} debug={debug} isFullPage={true} />;
}
