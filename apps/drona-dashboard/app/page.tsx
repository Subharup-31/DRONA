"use client";

import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Check,
  ChevronRight,
  CircuitBoard,
  FileUp,
  GitBranch,
  Menu,
  Radar,
  Sparkles,
  Workflow,
  X
} from "lucide-react";
import { useState } from "react";

const navItems = [
  { label: "Features", href: "#features" },
  { label: "How it works", href: "#how-it-works" },
  { label: "Pricing", href: "#pricing" },
  { label: "Join", href: "#join" }
];

const metrics = [
  { label: "Recall @5", value: "70%", detail: "families recovered across seeds" },
  { label: "Remediation", value: "100%", detail: "matching fix guidance" },
  { label: "p95 latency", value: "4.07ms", detail: "fast report execution" }
];

const featureCards = [
  {
    icon: GitBranch,
    title: "Temporal incident memory",
    copy: "Track service identity through deploys, renames, topology mutations, and noisy background events."
  },
  {
    icon: Radar,
    title: "Benchmark clarity",
    copy: "See recall, precision, remediation accuracy, latency, and seed-level stability in one clean surface."
  },
  {
    icon: FileUp,
    title: "Bring your own report",
    copy: "Upload a JSON execution report and the dashboard updates instantly with the new run data."
  }
];

const steps = [
  {
    title: "Ingest execution data",
    copy: "DRONA reads incidents, service signals, topology changes, and previous execution metadata."
  },
  {
    title: "Build causal context",
    copy: "The engine links evidence into persistent signatures so incidents stay recognizable over time."
  },
  {
    title: "Review the report",
    copy: "Open the dashboard, compare seeds, inspect incident outcomes, and upload new JSON runs."
  }
];

export default function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <main className="min-h-screen overflow-hidden bg-[#f7f7f2] text-[#101315]">
      <header className="sticky top-4 z-50 px-4">
        <nav className="mx-auto flex max-w-6xl items-center justify-between rounded-full border border-black/10 bg-white/80 px-3 py-2 shadow-[0_20px_70px_rgba(16,19,21,0.10)] backdrop-blur-xl">
          <Link href="/" className="flex items-center gap-2 rounded-full px-2 py-1">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-[#101315] text-white">
              <CircuitBoard className="h-5 w-5" />
            </span>
            <span className="text-sm font-black tracking-[0.22em]">DRONA</span>
          </Link>

          <div className="hidden items-center gap-1 rounded-full bg-[#101315]/5 p-1 md:flex">
            {navItems.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="rounded-full px-4 py-2 text-sm font-semibold text-[#101315]/70 transition hover:bg-white hover:text-[#101315]"
              >
                {item.label}
              </a>
            ))}
          </div>

          <div className="hidden items-center gap-2 md:flex">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 rounded-full bg-[#2a75ff] px-5 py-2.5 text-sm font-black text-white shadow-[0_14px_32px_rgba(42,117,255,0.24)] transition hover:bg-[#1d63df]"
            >
              Dashboard
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          <button
            className="grid h-10 w-10 place-items-center rounded-full bg-[#101315] text-white md:hidden"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label="Toggle navigation"
          >
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </nav>

        {menuOpen && (
          <div className="mx-auto mt-2 grid max-w-6xl gap-2 rounded-3xl border border-black/10 bg-white p-3 shadow-xl md:hidden">
            {navItems.map((item) => (
              <a key={item.href} href={item.href} className="rounded-2xl px-4 py-3 text-sm font-bold">
                {item.label}
              </a>
            ))}
            <Link href="/dashboard" className="rounded-2xl bg-[#2a75ff] px-4 py-3 text-sm font-black text-white">
              Dashboard
            </Link>
          </div>
        )}
      </header>

      <section className="relative mx-auto grid min-h-[calc(100vh-88px)] max-w-6xl items-center gap-10 px-5 pb-16 pt-12 sm:pt-16 lg:grid-cols-[1.05fr_0.95fr]">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-black/10 bg-white px-3 py-2 text-sm font-bold text-[#101315]/70">
            <Sparkles className="h-4 w-4 text-[#2a75ff]" />
            Incident memory for execution reports
          </div>
          <h1 className="mt-6 max-w-4xl text-4xl font-black leading-[1.02] tracking-tight text-[#101315] sm:text-5xl md:text-6xl lg:text-7xl">
            See what DRONA remembered, missed, and fixed.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-[#101315]/68">
            A clean benchmark command center for root-cause recall, precision, remediation accuracy, latency, and seed-by-seed execution health.
          </p>
          <div className="mt-9 flex flex-col gap-3 sm:flex-row">
            <Link
              href="/dashboard"
              className="inline-flex items-center justify-center gap-2 rounded-full bg-[#2a75ff] px-6 py-4 text-sm font-black text-white shadow-[0_18px_40px_rgba(42,117,255,0.25)] transition hover:bg-[#1d63df]"
            >
              Open dashboard
              <ArrowRight className="h-4 w-4" />
            </Link>
            <a
              href="#how-it-works"
              className="inline-flex items-center justify-center gap-2 rounded-full border border-black/10 bg-white px-6 py-4 text-sm font-black text-[#101315] transition hover:border-black/20"
            >
              How it works
              <ChevronRight className="h-4 w-4" />
            </a>
          </div>
        </div>

        <div className="rounded-[2rem] border border-black/10 bg-[#101315] p-3 shadow-[0_30px_100px_rgba(16,19,21,0.28)]">
          <div className="rounded-[1.45rem] bg-[#151b1f] p-5 text-white">
            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.24em] text-white/40">Latest run</p>
                <h2 className="mt-1 text-xl font-black">report_improved.json</h2>
              </div>
              <span className="rounded-full bg-emerald-400/15 px-3 py-1 text-xs font-black text-emerald-200">Ready</span>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              {metrics.map((metric) => (
                <div key={metric.label} className="rounded-2xl bg-white/[0.06] p-4">
                  <p className="text-xs font-bold text-white/45">{metric.label}</p>
                  <p className="mt-2 text-2xl font-black">{metric.value}</p>
                  <p className="mt-1 text-xs leading-5 text-white/45">{metric.detail}</p>
                </div>
              ))}
            </div>

            <div className="mt-4 rounded-2xl bg-white/[0.06] p-4">
              <div className="mb-4 flex items-center justify-between">
                <p className="text-sm font-black">Seed health</p>
                <BarChart3 className="h-5 w-5 text-[#7cc7ff]" />
              </div>
              {[100, 80, 40, 70, 60].map((value, index) => (
                <div key={index} className="mb-3 grid grid-cols-[64px_1fr_44px] items-center gap-3 last:mb-0">
                  <span className="font-mono text-xs text-white/50">S{index + 1}</span>
                  <span className="h-2 overflow-hidden rounded-full bg-white/10">
                    <span className="block h-full rounded-full bg-[#7cc7ff]" style={{ width: `${value}%` }} />
                  </span>
                  <span className="text-right text-xs font-bold text-white/70">{value}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="relative mx-auto max-w-6xl px-5 py-20">
        <div className="max-w-2xl">
          <p className="text-sm font-black uppercase tracking-[0.26em] text-[#2a75ff]">Features</p>
          <h2 className="mt-3 text-4xl font-black tracking-tight md:text-5xl">Everything your report needs to explain itself.</h2>
        </div>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {featureCards.map((feature) => {
            const Icon = feature.icon;
            return (
              <article key={feature.title} className="rounded-3xl border border-black/10 bg-white p-6 shadow-sm">
                <div className="grid h-12 w-12 place-items-center rounded-2xl bg-[#101315] text-white">
                  <Icon className="h-6 w-6" />
                </div>
                <h3 className="mt-6 text-xl font-black">{feature.title}</h3>
                <p className="mt-3 leading-7 text-[#101315]/65">{feature.copy}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section id="how-it-works" className="relative bg-[#101315] px-5 py-20 text-white">
        <div className="mx-auto max-w-6xl">
          <div className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr]">
            <div>
              <p className="text-sm font-black uppercase tracking-[0.26em] text-[#7cc7ff]">How it works</p>
              <h2 className="mt-3 text-4xl font-black tracking-tight md:text-5xl">From raw run to readable decision trail.</h2>
            </div>
            <div className="grid gap-4">
              {steps.map((step, index) => (
                <div key={step.title} className="grid gap-4 rounded-3xl border border-white/10 bg-white/[0.04] p-5 sm:grid-cols-[56px_1fr]">
                  <div className="grid h-12 w-12 place-items-center rounded-full bg-white text-lg font-black text-[#101315]">
                    {index + 1}
                  </div>
                  <div>
                    <h3 className="text-xl font-black">{step.title}</h3>
                    <p className="mt-2 leading-7 text-white/62">{step.copy}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="pricing" className="relative mx-auto max-w-6xl px-5 py-20">
        <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <div>
            <p className="text-sm font-black uppercase tracking-[0.26em] text-[#2a75ff]">Pricing</p>
            <h2 className="mt-3 text-4xl font-black tracking-tight md:text-5xl">Start with reports. Scale into operations.</h2>
          </div>
          <Link href="/dashboard" className="inline-flex items-center gap-2 rounded-full bg-[#2a75ff] px-5 py-3 text-sm font-black text-white shadow-[0_14px_32px_rgba(42,117,255,0.22)]">
            Try dashboard
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
        <div className="mt-10 grid gap-4 lg:grid-cols-3">
          <PriceCard name="Starter" price="Free" items={["Local report dashboard", "JSON upload", "Seed table", "Incident explorer"]} />
          <PriceCard name="Team" price="$49/mo" featured items={["Shared report history", "Debug evidence view", "Export summaries", "Priority support"]} />
          <PriceCard name="Enterprise" price="Custom" items={["Private deployment", "Custom benchmark axes", "SRE onboarding", "Security review"]} />
        </div>
      </section>

      <section id="join" className="relative mx-auto max-w-6xl px-5 pb-20">
        <div className="grid gap-8 rounded-[2rem] bg-[#2a75ff] p-8 text-white md:grid-cols-[1fr_auto] md:items-center md:p-12">
          <div>
            <p className="text-sm font-black uppercase tracking-[0.26em] text-white/65">Join</p>
            <h2 className="mt-3 text-4xl font-black tracking-tight">Make every execution report easier to trust.</h2>
            <p className="mt-4 max-w-2xl leading-7 text-white/75">
              Open the dashboard, review the previous run, or upload your own JSON to demonstrate DRONA end to end.
            </p>
          </div>
          <Link href="/dashboard" className="inline-flex items-center justify-center gap-2 rounded-full bg-white px-6 py-4 text-sm font-black text-[#101315]">
            Launch now
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      <footer className="relative border-t border-black/10 bg-white px-5 py-10">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-full bg-[#101315] text-white">
              <Workflow className="h-5 w-5" />
            </span>
            <div>
              <p className="font-black">DRONA</p>
              <p className="text-sm text-[#101315]/55">Incident memory and benchmark reporting.</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-4 text-sm font-bold text-[#101315]/65">
            <a href="#features">Features</a>
            <a href="#how-it-works">How it works</a>
            <a href="#pricing">Pricing</a>
            <Link href="/dashboard">Dashboard</Link>
          </div>
        </div>
      </footer>
    </main>
  );
}

function PriceCard({
  name,
  price,
  items,
  featured = false
}: {
  name: string;
  price: string;
  items: string[];
  featured?: boolean;
}) {
  return (
    <article className={`rounded-3xl border p-6 ${featured ? "border-[#2a75ff] bg-[#101315] text-white" : "border-black/10 bg-white"}`}>
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-xl font-black">{name}</h3>
          <p className={`mt-1 text-sm ${featured ? "text-white/55" : "text-[#101315]/55"}`}>For DRONA report teams</p>
        </div>
        <p className="text-2xl font-black">{price}</p>
      </div>
      <ul className="mt-8 grid gap-3">
        {items.map((item) => (
          <li key={item} className="flex items-center gap-3 text-sm font-semibold">
            <span className={`grid h-6 w-6 place-items-center rounded-full ${featured ? "bg-white text-[#101315]" : "bg-[#101315] text-white"}`}>
              <Check className="h-4 w-4" />
            </span>
            {item}
          </li>
        ))}
      </ul>
    </article>
  );
}
