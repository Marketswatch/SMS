import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { AppProvider, useApp } from "@/context/AppContext";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import ModeSelect from "@/pages/ModeSelect";
import Dashboard from "@/pages/Dashboard";
import Setup from "@/pages/Setup";
import Water from "@/pages/Water";
import Charges from "@/pages/Charges";
import Reconcile from "@/pages/Reconcile";
import MIS from "@/pages/MIS";
import Annual from "@/pages/Annual";
import MyDues from "@/pages/MyDues";
import RentDashboard from "@/pages/rentals/RentDashboard";
import Units from "@/pages/rentals/Units";
import Collections from "@/pages/rentals/Collections";
import Expenses from "@/pages/rentals/Expenses";
import RentReport from "@/pages/rentals/RentReport";
import "@/index.css";

function Gate({ children, adminOnly }) {
  const { user, isAdmin } = useAuth();
  if (user === null)
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-500" data-testid="auth-loading">
        Loading…
      </div>
    );
  if (user === false) return <Navigate to="/login" replace />;
  if (adminOnly && !isAdmin) return <Navigate to="/my-dues" replace />;
  return children;
}

function ModeGate({ children }) {
  const { mode } = useApp();
  const { isAdmin } = useAuth();
  if (isAdmin && !mode) return <Navigate to="/mode" replace />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Toaster position="bottom-right" richColors />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/mode" element={<Gate adminOnly><AppProvider><ModeSelect /></AppProvider></Gate>} />
          <Route
            element={
              <Gate>
                <AppProvider>
                  <ModeGate>
                    <Layout />
                  </ModeGate>
                </AppProvider>
              </Gate>
            }
          >
            <Route path="/" element={<Gate adminOnly><Dashboard /></Gate>} />
            <Route path="/setup" element={<Gate adminOnly><Setup /></Gate>} />
            <Route path="/water" element={<Gate adminOnly><Water /></Gate>} />
            <Route path="/charges" element={<Gate adminOnly><Charges /></Gate>} />
            <Route path="/reconcile" element={<Gate adminOnly><Reconcile /></Gate>} />
            <Route path="/mis" element={<Gate adminOnly><MIS /></Gate>} />
            <Route path="/annual" element={<Gate adminOnly><Annual /></Gate>} />
            <Route path="/my-dues" element={<MyDues />} />
            <Route path="/rentals" element={<Gate adminOnly><RentDashboard /></Gate>} />
            <Route path="/rentals/units" element={<Gate adminOnly><Units /></Gate>} />
            <Route path="/rentals/collections" element={<Gate adminOnly><Collections /></Gate>} />
            <Route path="/rentals/expenses" element={<Gate adminOnly><Expenses /></Gate>} />
            <Route path="/rentals/report" element={<Gate adminOnly><RentReport /></Gate>} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
