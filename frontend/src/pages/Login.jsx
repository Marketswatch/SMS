import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Droplets, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { errMsg } from "@/lib/api";

export default function Login() {
  const { login, user } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("admin@societyhub.com");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) nav(user.role === "admin" || user.role === "super_admin" ? "/mode" : "/my-dues", { replace: true });
  }, [user, nav]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const u = await login(email, password);
      nav(u.role === "admin" || u.role === "super_admin" ? "/mode" : "/my-dues", { replace: true });
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr]">
      <div className="hidden lg:block relative bg-slate-900">
        <img
          src="https://images.unsplash.com/photo-1515263487990-61b07816b324?crop=entropy&cs=srgb&fm=jpg&w=1400&q=80"
          alt="Apartment building"
          className="absolute inset-0 w-full h-full object-cover opacity-30 grayscale"
        />
        <div className="relative h-full flex flex-col justify-between p-12 text-white">
          <div className="flex items-center gap-2">
            <Droplets className="w-6 h-6" />
            <span className="font-display text-xl font-bold tracking-tight">SocietyHub</span>
          </div>
          <div className="max-w-lg">
            <h1 className="font-display text-4xl sm:text-5xl font-bold leading-[1.05]">
              Honest water math for every flat.
            </h1>
            <p className="mt-6 text-base text-slate-300 leading-relaxed">
              Tanker purchases, meter readings, reserve drawdown, recurring charges and repairs — split
              fairly, reconciled per owner, locked at month end.
            </p>
            <div className="mt-10 grid grid-cols-3 gap-4 mono text-sm">
              <div><div className="label-caps text-slate-400">Split unit</div><div className="mt-1">Per flat</div></div>
              <div><div className="label-caps text-slate-400">Reserve</div><div className="mt-1">Purchased − used</div></div>
              <div><div className="label-caps text-slate-400">History</div><div className="mt-1">Locked</div></div>
            </div>
          </div>
          <p className="text-xs text-slate-400">Admin-driven · No payment gateway · Manual reconciliation</p>
        </div>
      </div>

      <div className="flex items-center justify-center p-6 sm:p-12 bg-white">
        <form onSubmit={submit} className="w-full max-w-sm fade-up" data-testid="login-form">
          <div className="flex items-center gap-2 lg:hidden mb-8">
            <Droplets className="w-6 h-6 text-slate-900" />
            <span className="font-display text-xl font-bold">SocietyHub</span>
          </div>
          <div className="label-caps">Sign in</div>
          <h2 className="font-display text-2xl sm:text-3xl font-bold mt-2 text-slate-900">Admin console</h2>
          <div className="mt-8 space-y-4">
            <div>
              <Label htmlFor="email" className="label-caps">Email</Label>
              <Input id="email" data-testid="login-email-input" type="email" value={email}
                     onChange={(e) => setEmail(e.target.value)} className="mt-2 h-11" required />
            </div>
            <div>
              <Label htmlFor="password" className="label-caps">Password</Label>
              <Input id="password" data-testid="login-password-input" type="password" value={password}
                     onChange={(e) => setPassword(e.target.value)} className="mt-2 h-11" required />
            </div>
          </div>
          {error && (
            <div data-testid="login-error" className="mt-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {error}
            </div>
          )}
          <Button type="submit" data-testid="login-submit-btn" disabled={busy}
                  className="mt-6 w-full h-11 bg-slate-900 hover:bg-slate-700 text-white">
            <LogIn className="w-4 h-4 mr-2" /> {busy ? "Signing in…" : "Sign in"}
          </Button>
          <p className="mt-6 text-xs text-slate-500 mono">
            Demo admin · admin@societyhub.com / admin123
          </p>
        </form>
      </div>
    </div>
  );
}
