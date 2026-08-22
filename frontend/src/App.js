import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { AppProvider } from "@/context/AppContext";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Setup from "@/pages/Setup";
import Water from "@/pages/Water";
import Charges from "@/pages/Charges";
import Reconcile from "@/pages/Reconcile";
import MIS from "@/pages/MIS";
import MyDues from "@/pages/MyDues";
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

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Toaster position="bottom-right" richColors />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <Gate>
                <AppProvider>
                  <Layout />
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
            <Route path="/my-dues" element={<MyDues />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
