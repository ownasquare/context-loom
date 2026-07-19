import type { ReactNode } from "react";
import type { RouteId } from "../../app/navigation";
import { MobileNavigation } from "./MobileNavigation";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

interface AppShellProps {
  activeRoute: RouteId;
  onNavigate: (route: RouteId) => void;
  children: ReactNode;
}

export function AppShell({ activeRoute, onNavigate, children }: AppShellProps) {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <Sidebar activeRoute={activeRoute} onNavigate={onNavigate} />
      <div className="app-shell__surface">
        <Topbar activeRoute={activeRoute} onNavigate={onNavigate} />
        <main className="main-content" id="main-content" tabIndex={-1}>
          {children}
        </main>
      </div>
      <MobileNavigation activeRoute={activeRoute} onNavigate={onNavigate} />
    </div>
  );
}
