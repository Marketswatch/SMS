import { NavLink, Outlet } from "react-router-dom";
import { useState } from "react";
import {
  LayoutDashboard, Building2, Droplets, Receipt, Scale, FileSpreadsheet, LogOut, Menu, X, Lock, User,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useApp } from "@/context/AppContext";
import { monthLabel } from "@/lib/format";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const adminNav = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, id: "dashboard" },
  { to: "/setup", label: "Building Setup", icon: Building2, id: "setup" },
  { to: "/water", label: "Water", icon: Droplets, id: "water" },
  { to: "/charges", label: "Charges", icon: Receipt, id: "charges" },
  { to: "/reconcile", label: "Reconciliation", icon: Scale, id: "reconcile" },
  { to: "/mis", label: "MIS Report", icon: FileSpreadsheet, id: "mis" },
];

export default function Layout() {
  const { user, logout, isAdmin } = useAuth();
  const { properties, propertyId, setPropertyId, periods, month, setMonth, locked } = useApp();
  const [open, setOpen] = useState(false);

  const nav = isAdmin ? adminNav : [{ to: "/my-dues", label: "My Dues", icon: User, id: "my-dues" }];

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-40 bg-white border-b border-slate-200">
        <div className="flex items-center gap-3 px-4 lg:px-6 h-14">
          <button className="lg:hidden p-1" onClick={() => setOpen(!open)} data-testid="mobile-menu-btn">
            {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
          <div className="flex items-center gap-2">
            <Droplets className="w-5 h-5 text-slate-900" />
            <span className="font-display font-bold tracking-tight text-slate-900 hidden sm:inline">SocietyHub</span>
          </div>

          <div className="ml-auto flex items-center gap-1.5 sm:gap-3 min-w-0">
            {properties.length > 0 && (
              <Select value={propertyId} onValueChange={setPropertyId}>
                <SelectTrigger className="h-9 w-[104px] sm:w-[200px] text-sm" data-testid="property-switcher">
                  <SelectValue placeholder="Property" />
                </SelectTrigger>
                <SelectContent>
                  {properties.map((p) => (
                    <SelectItem key={p.id} value={p.id} data-testid={`property-option-${p.id}`}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {periods.length > 0 && (
              <Select value={month} onValueChange={setMonth}>
                <SelectTrigger className="h-9 w-[104px] sm:w-[160px] text-sm" data-testid="period-switcher">
                  <SelectValue placeholder="Period" />
                </SelectTrigger>
                <SelectContent>
                  {periods.map((p) => (
                    <SelectItem key={p.month} value={p.month} data-testid={`period-option-${p.month}`}>
                      {monthLabel(p.month)} {p.status === "locked" ? "· locked" : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <button onClick={logout} data-testid="logout-btn"
                    className="p-2 text-slate-500 hover:text-slate-900" title="Sign out">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
        {locked && (
          <div data-testid="locked-banner"
               className="flex items-center gap-2 px-4 lg:px-6 py-1.5 bg-amber-50 border-t border-amber-200 text-amber-800 text-xs">
            <Lock className="w-3.5 h-3.5" /> {monthLabel(month)} is locked — historical record, read only.
          </div>
        )}
      </header>

      <div className="flex">
        <aside className={`${open ? "block" : "hidden"} lg:block fixed lg:sticky left-0 z-30 w-60 bg-white border-r border-slate-200 p-3 ${
          locked ? "top-[5.6rem] h-[calc(100vh-5.6rem)]" : "top-14 h-[calc(100vh-3.5rem)]"
        }`}>
          <nav className="space-y-0.5">
            {nav.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/"} onClick={() => setOpen(false)}
                       data-testid={`nav-${n.id}`}
                       className={({ isActive }) =>
                         `flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium ${
                           isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                         }`}>
                <n.icon className="w-4 h-4" /> {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="absolute bottom-4 left-3 right-3 border-t border-slate-200 pt-3">
            <div className="text-sm font-medium text-slate-800 truncate">{user?.name}</div>
            <div className="label-caps mt-0.5">{user?.role?.replace("_", " ")}</div>
          </div>
        </aside>

        <main className="flex-1 min-w-0 max-w-full overflow-x-hidden p-4 lg:p-8" data-testid="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
