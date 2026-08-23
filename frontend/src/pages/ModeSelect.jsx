import { useNavigate } from "react-router-dom";
import { Droplets, Building2, ArrowRight, KeyRound } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/context/AuthContext";

const Choice = ({ icon: Icon, title, blurb, points, onClick, testId }) => (
  <button onClick={onClick} data-testid={testId}
          className="group text-left bg-white border border-slate-200 rounded-md p-7 hover:border-slate-900 focus:ring-2 focus:ring-slate-900 focus:outline-none"
          style={{ transition: "border-color 0.2s ease, box-shadow 0.2s ease" }}>
    <div className="flex items-start justify-between">
      <span className="inline-flex items-center justify-center w-11 h-11 rounded-md bg-slate-900 text-white">
        <Icon className="w-5 h-5" />
      </span>
      <ArrowRight className="w-5 h-5 text-slate-300 group-hover:text-slate-900" style={{ transition: "color 0.2s ease" }} />
    </div>
    <h3 className="font-display text-xl font-bold mt-5 text-slate-900">{title}</h3>
    <p className="text-sm text-slate-600 mt-2 leading-relaxed">{blurb}</p>
    <ul className="mt-5 space-y-1.5">
      {points.map((p) => (
        <li key={p} className="text-xs text-slate-500 flex gap-2">
          <span className="text-slate-300">—</span> {p}
        </li>
      ))}
    </ul>
  </button>
);

export default function ModeSelect() {
  const { setMode } = useApp();
  const { user } = useAuth();
  const nav = useNavigate();

  const pick = (m, to) => { setMode(m); nav(to, { replace: true }); };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
      <div className="w-full max-w-3xl fade-up">
        <div className="flex items-center gap-2">
          <Droplets className="w-5 h-5 text-slate-900" />
          <span className="font-display font-bold tracking-tight text-slate-900">SocietyHub</span>
        </div>
        <div className="label-caps mt-8">Welcome back, {user?.name}</div>
        <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight text-slate-900 mt-2">
          What are you managing today?
        </h1>
        <p className="text-sm text-slate-500 mt-2">You can switch between the two at any time from the header.</p>

        <div className="grid sm:grid-cols-2 gap-5 mt-8">
          <Choice testId="mode-maintenance-btn" icon={Droplets} title="Maintenance Management"
                  blurb="Split water, recurring charges and repairs across the flats of a building and reconcile per owner."
                  points={["Tanker purchases & meter readings", "Reserve and per-litre cost engine",
                           "Owner statements, MIS, month reset"]}
                  onClick={() => pick("maintenance", "/")} />
          <Choice testId="mode-rentals-btn" icon={Building2} title="Property Management"
                  blurb="Rent, deposits and bills for the properties you own or manage for family and friends."
                  points={["Rent roll: collected, pending, overdue", "Deposits held, refunds and deductions",
                           "Bills paid on behalf of a building, tallied separately"]}
                  onClick={() => pick("rentals", "/rentals")} />
        </div>

        <p className="mt-8 text-xs text-slate-400 flex items-center gap-1.5">
          <KeyRound className="w-3.5 h-3.5" /> Signed in as {user?.email} · {user?.role?.replace("_", " ")}
        </p>
      </div>
    </div>
  );
}
