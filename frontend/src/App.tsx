// src/App.tsx
import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "./utils/toast";
import { AuthProvider } from "./providers/AuthProvider";
import { ThemeProvider } from "./providers/ThemeProvider";
import { EncryptionProvider } from "./providers/EncryptionProvider";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AdminRoute } from "./components/admin/AdminRoute";
import { LoadingSpinner } from "./components/ui/LoadingSpinner";

import "./App.css";

const queryClient = new QueryClient();

// Lazy load layouts
const AuthLayout = lazy(() => import("./layouts/AuthLayout").then(m => ({ default: m.AuthLayout })));
const DashboardLayout = lazy(() => import("./layouts/DashboardLayout").then(m => ({ default: m.DashboardLayout })));
const MappingLayout = lazy(() => import("./layouts/MappingLayout").then(m => ({ default: m.MappingLayout })));
const AdminLayout = lazy(() => import("./layouts/AdminLayout").then(m => ({ default: m.AdminLayout })));

// Lazy load admin pages
const AdminDashboard = lazy(() => import("./pages/admin/AdminDashboard").then(m => ({ default: m.AdminDashboard })));
const AdminUsers = lazy(() => import("./pages/admin/AdminUsers").then(m => ({ default: m.AdminUsers })));
const AdminSecurity = lazy(() => import("./pages/admin/AdminSecurity").then(m => ({ default: m.AdminSecurity })));
const AdminMetrics = lazy(() => import("./pages/admin/AdminMetrics").then(m => ({ default: m.AdminMetrics })));
const AdminHealth = lazy(() => import("./pages/admin/AdminHealth").then(m => ({ default: m.AdminHealth })));

// Lazy load auth pages (lower priority - only loaded when needed)
const Login = lazy(() => import("./pages/auth/Login").then(m => ({ default: m.Login })));
const Register = lazy(() => import("./pages/auth/Register").then(m => ({ default: m.Register })));
const VerifyEmail = lazy(() => import("./pages/auth/VerifyEmail").then(m => ({ default: m.VerifyEmail })));

// Lazy load main pages
const Dashboard = lazy(() => import("./pages/Dashboard").then(m => ({ default: m.Dashboard })));
const ProjectMapping = lazy(() => import("./pages/ProjectMapping").then(m => ({ default: m.ProjectMapping })));
const ProjectVersions = lazy(() => import("./pages/ProjectVersions").then(m => ({ default: m.ProjectVersions })));
const Team = lazy(() => import("./pages/Team").then(m => ({ default: m.Team })));
const Settings = lazy(() => import("./pages/Settings").then(m => ({ default: m.Settings })));

function App() {
  return (
    <QueryClientProvider client={queryClient}>
    <ThemeProvider>
      <AuthProvider>
        <EncryptionProvider>
          <BrowserRouter>
            <Toaster
              position="top-right"
              containerStyle={{
                top: 16,
                right: 16,
                bottom: 'auto',
                left: 'auto',
              }}
              toastOptions={{
                duration: 3000,
                style: {
                  background: 'var(--card)',
                  color: 'var(--foreground)',
                  border: '1px solid var(--border)',
                },
                success: {
                  iconTheme: {
                    primary: '#10b981',
                    secondary: '#fff',
                  },
                },
                error: {
                  iconTheme: {
                    primary: '#ef4444',
                    secondary: '#fff',
                  },
                },
              }}
            />
            <Suspense fallback={<LoadingSpinner fullscreen size="lg" />}>
              <Routes>
              {/* Ruta raíz - redirige a dashboard */}
              <Route path="/" element={<Navigate to="/dashboard" replace />} />

              {/* Rutas de autenticación (públicas) */}
              <Route element={<AuthLayout />}>
                <Route path="/login" element={<Login />} />
                <Route path="/register" element={<Register />} />
                <Route path="/verify" element={<VerifyEmail />} />
              </Route>

              {/* Dashboard routes - Layout con Sidebar/Topbar */}
              <Route element={<ProtectedRoute />}>
                <Route element={<DashboardLayout />}>
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/projects" element={<Dashboard />} />
                  <Route path="/team" element={<Team />} />
                  <Route path="/settings" element={<Settings />} />
                </Route>
              </Route>

              {/* Mapping routes - Layout con Sidebar/Topbar */}
              <Route element={<ProtectedRoute />}>
                <Route element={<MappingLayout />}>
                  <Route path="/projects/:projectId/mapping" element={<ProjectMapping />} />
                  <Route path="/projects/:projectId/versions" element={<ProjectVersions />} />
                </Route>
              </Route>

              {/* Admin routes */}
              <Route element={<AdminRoute />}>
                <Route element={<AdminLayout />}>
                  <Route path="/admin" element={<AdminDashboard />} />
                  <Route path="/admin/users" element={<AdminUsers />} />
                  <Route path="/admin/security" element={<AdminSecurity />} />
                  <Route path="/admin/metrics" element={<AdminMetrics />} />
                  <Route path="/admin/health" element={<AdminHealth />} />
                </Route>
              </Route>

              {/* Ruta 404 */}
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
        </EncryptionProvider>
      </AuthProvider>
    </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;