import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";
import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { useCurrentUser } from "@/hooks/useAuth";
import { onSessionExpired } from "@/lib/api";
import { AnalyticsPage } from "@/pages/Analytics";
import { CamerasPage } from "@/pages/Cameras";
import { IncidentsPage } from "@/pages/Incidents";
import { LiveMonitoringPage } from "@/pages/LiveMonitoring";
import { LoginPage } from "@/pages/Login";
import { OverviewPage } from "@/pages/Overview";
import { DemoModePage } from "@/pages/DemoMode";
import { SettingsPage } from "@/pages/Settings";
import { ZonesPage } from "@/pages/Zones";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
    },
  },
});

function ProtectedShell() {
  const { data: user, isLoading } = useCurrentUser();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg text-sm text-text-muted">
        Loading…
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <AppShell />;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedShell />}>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/live" element={<LiveMonitoringPage />} />
        <Route path="/incidents" element={<IncidentsPage />} />
        <Route path="/cameras" element={<CamerasPage />} />
        <Route path="/zones" element={<ZonesPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/demo" element={<DemoModePage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  useEffect(() => onSessionExpired(() => {
    queryClient.setQueryData(["auth", "me"], null);
    queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "auth" });
  }), []);

  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <AppRoutes />
      </Router>
    </QueryClientProvider>
  );
}
