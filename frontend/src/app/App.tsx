import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../components/layout/AppShell";
import { navigationItemFor, routeFromPath } from "./navigation";
import type { RouteId } from "./navigation";
import { HydratePage } from "../pages/HydratePage";
import { IntegrationsPage } from "../pages/IntegrationsPage";
import { OverviewPage } from "../pages/OverviewPage";
import { ResourcesPage } from "../pages/ResourcesPage";
import { SettingsPage } from "../pages/SettingsPage";
import { ThreadsPage } from "../pages/ThreadsPage";

export function App() {
  const [route, setRoute] = useState<RouteId>(() => routeFromPath(window.location.pathname));

  useEffect(() => {
    const handlePopState = () => {
      setRoute(routeFromPath(window.location.pathname));
      window.requestAnimationFrame(() => document.getElementById("main-content")?.focus());
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    document.title = `${navigationItemFor(route).label} · Context Loom`;
  }, [route]);

  const navigate = useCallback((nextRoute: RouteId) => {
    const destination = navigationItemFor(nextRoute);
    window.history.pushState({}, "", `${destination.path}${window.location.search}`);
    setRoute(nextRoute);
    window.scrollTo({ top: 0, behavior: "smooth" });
    window.requestAnimationFrame(() => document.getElementById("main-content")?.focus());
  }, []);

  return (
    <AppShell activeRoute={route} onNavigate={navigate}>
      <Page activeRoute={route} onNavigate={navigate} />
    </AppShell>
  );
}

interface PageProps {
  activeRoute: RouteId;
  onNavigate: (route: RouteId) => void;
}

function Page({ activeRoute, onNavigate }: PageProps) {
  switch (activeRoute) {
    case "hydrate":
      return <HydratePage />;
    case "resources":
      return <ResourcesPage />;
    case "threads":
      return <ThreadsPage onNavigate={onNavigate} />;
    case "integrations":
      return <IntegrationsPage />;
    case "settings":
      return <SettingsPage />;
    case "overview":
    default:
      return <OverviewPage onNavigate={onNavigate} />;
  }
}
