import type { MouseEvent } from "react";
import { apiClient } from "../../api/client";
import { navigationItems } from "../../app/navigation";
import type { NavigationItem, RouteId } from "../../app/navigation";
import { useHealth } from "../../api/queries";
import { Icon } from "../icons/Icon";
import { LogoMark } from "../icons/LogoMark";
import { Badge } from "../ui/Badge";
import { WorkspaceControl } from "../../features/workspaces/WorkspaceControl";
import { privacyStatusFor } from "./privacyStatus";

interface SidebarProps {
  activeRoute: RouteId;
  onNavigate: (route: RouteId) => void;
}

interface SidebarLinkProps extends SidebarProps {
  item: NavigationItem;
}

export function Sidebar({ activeRoute, onNavigate }: SidebarProps) {
  const health = useHealth();
  const privacyStatus = privacyStatusFor(health.data, health.isPending);

  return (
    <aside className="sidebar">
      <div className="brand-lockup">
        <LogoMark />
        <div className="brand-lockup__text">
          <strong>Context Loom</strong>
          <span>Local project context</span>
        </div>
      </div>

      <WorkspaceControl />

      <nav aria-label="Primary" className="sidebar__nav">
        <p className="sidebar__label">Work</p>
        {navigationItems.slice(0, 4).map((item) => (
          <SidebarLink activeRoute={activeRoute} item={item} key={item.id} onNavigate={onNavigate} />
        ))}
        <p className="sidebar__label sidebar__label--manage">Manage</p>
        {navigationItems.slice(4).map((item) => (
          <SidebarLink activeRoute={activeRoute} item={item} key={item.id} onNavigate={onNavigate} />
        ))}
      </nav>

      <div className="sidebar__footer">
        <div className="local-status">
          <Icon name={privacyStatus.icon} size={18} />
          <div>
            <strong>{privacyStatus.title}</strong>
            <span>{privacyStatus.detail}</span>
          </div>
        </div>
        {apiClient.isDemoMode() ? <Badge tone="accent">Demo workspace</Badge> : null}
      </div>
    </aside>
  );
}

function SidebarLink({ activeRoute, item, onNavigate }: SidebarLinkProps) {
  const query = window.location.search;

  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    onNavigate(item.id);
  }

  return (
    <a
      aria-current={activeRoute === item.id ? "page" : undefined}
      className="sidebar-link"
      href={`${item.path}${query}`}
      onClick={handleClick}
    >
      <Icon name={item.icon} size={19} />
      <span>{item.label}</span>
    </a>
  );
}
