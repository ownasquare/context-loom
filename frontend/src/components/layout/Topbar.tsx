import { useEffect, useRef } from "react";
import { apiClient } from "../../api/client";
import { navigationItemFor } from "../../app/navigation";
import type { RouteId } from "../../app/navigation";
import { Icon } from "../icons/Icon";
import { LogoMark } from "../icons/LogoMark";
import { Badge } from "../ui/Badge";
import { useWorkspace } from "../../app/workspace";
import { useHealth } from "../../api/queries";
import { WorkspaceControl } from "../../features/workspaces/WorkspaceControl";
import { privacyStatusFor } from "./privacyStatus";

interface TopbarProps {
  activeRoute: RouteId;
  onNavigate: (route: RouteId) => void;
}

export function Topbar({ activeRoute, onNavigate }: TopbarProps) {
  const item = navigationItemFor(activeRoute);
  const { selectedWorkspace, workspacesQuery } = useWorkspace();
  const health = useHealth();
  const privacyStatus = privacyStatusFor(health.data, health.isPending);
  const moreRef = useRef<HTMLDetailsElement>(null);

  function closeMore({ restoreFocus = false } = {}) {
    const details = moreRef.current;
    if (!details?.open) {
      return;
    }
    details.removeAttribute("open");
    if (restoreFocus) {
      details.querySelector("summary")?.focus();
    }
  }

  function navigateFromMore(route: RouteId) {
    closeMore();
    onNavigate(route);
  }

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      const details = moreRef.current;
      if (details?.open && event.target instanceof Node && !details.contains(event.target)) {
        closeMore();
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && moreRef.current?.open) {
        event.preventDefault();
        closeMore({ restoreFocus: true });
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  return (
    <header className="topbar">
      <div className="topbar__mobile-brand">
        <LogoMark size={30} />
      </div>
      <div className="topbar__title">
        <strong>{item.label}</strong>
        <span>{workspacesQuery.isPending ? "Loading project…" : selectedWorkspace?.name ?? "No project connected"}</span>
      </div>
      <div className="topbar__actions">
        {apiClient.isDemoMode() ? <Badge dot tone="accent">Demo data</Badge> : null}
        <span aria-label={`${privacyStatus.title}. ${privacyStatus.detail}`} className={`privacy-chip privacy-chip--${privacyStatus.tone}`}>
          <Icon name={privacyStatus.icon} size={15} />
          <span>{privacyStatus.chip}</span>
        </span>
        <details className="mobile-more" ref={moreRef}>
          <summary aria-label="Project and app controls" role="button"><Icon name="settings" size={18} /></summary>
          <div className="mobile-more__panel">
            <div className="mobile-more__projects"><WorkspaceControl compact /></div>
            <div className="mobile-more__links">
              <button onClick={() => navigateFromMore("integrations")} type="button"><Icon name="plug" size={17} />Connections</button>
              <button onClick={() => navigateFromMore("settings")} type="button"><Icon name="settings" size={17} />Settings</button>
            </div>
          </div>
        </details>
      </div>
      <span aria-atomic="true" aria-live="polite" className="sr-only">{item.label} page</span>
    </header>
  );
}
