import { money } from "@/lib/format";
import { ArrowDown, ArrowUp, Minus } from "lucide-react";

export const PageHeader = ({ title, subtitle, children }) => (
  <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
    <div>
      <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">{title}</h1>
      {subtitle && <p className="text-sm text-slate-500 mt-1">{subtitle}</p>}
    </div>
    <div className="flex flex-wrap gap-2">{children}</div>
  </div>
);

export const Stat = ({ label, value, sub, tone = "default", testId }) => {
  const tones = {
    default: "text-slate-900",
    positive: "text-emerald-600",
    negative: "text-red-600",
    warning: "text-amber-600",
  };
  return (
    <div className="stat-card fade-up" data-testid={testId}>
      <div className="label-caps">{label}</div>
      <div className={`mono text-xl sm:text-2xl font-semibold mt-2 ${tones[tone]}`}>{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  );
};

export const NetBadge = ({ value, testId }) => {
  const v = Number(value || 0);
  if (v === 0)
    return (
      <span data-testid={testId} className="inline-flex items-center gap-1 mono text-xs px-2 py-0.5 rounded border bg-slate-50 text-slate-600 border-slate-200">
        <Minus className="w-3 h-3" /> settled
      </span>
    );
  const owes = v > 0;
  return (
    <span data-testid={testId}
          className={`inline-flex items-center gap-1 mono text-xs px-2 py-0.5 rounded border ${
            owes ? "bg-red-50 text-red-700 border-red-200" : "bg-emerald-50 text-emerald-700 border-emerald-200"
          }`}>
      {owes ? <ArrowDown className="w-3 h-3" /> : <ArrowUp className="w-3 h-3" />}
      {money(Math.abs(v))} {owes ? "owes" : "owed"}
    </span>
  );
};

export const Empty = ({ title, hint, children, testId }) => (
  <div className="bg-white border border-dashed border-slate-300 rounded-md p-10 text-center" data-testid={testId}>
    <div className="font-display text-lg font-semibold text-slate-800">{title}</div>
    {hint && <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">{hint}</p>}
    <div className="mt-4 flex justify-center gap-2">{children}</div>
  </div>
);

export const Card = ({ title, action, children, testId, className = "" }) => (
  <section className={`bg-white border border-slate-200 rounded-md ${className}`} data-testid={testId}>
    {(title || action) && (
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-slate-200">
        <h3 className="font-display text-base font-semibold text-slate-800">{title}</h3>
        {action}
      </div>
    )}
    <div className="p-4">{children}</div>
  </section>
);
