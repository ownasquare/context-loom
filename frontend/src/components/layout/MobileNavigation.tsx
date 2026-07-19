import type { MouseEvent } from "react";
import { navigationItems } from "../../app/navigation";
import type { NavigationItem, RouteId } from "../../app/navigation";
import { Icon } from "../icons/Icon";

interface MobileNavigationProps {
  activeRoute: RouteId;
  onNavigate: (route: RouteId) => void;
}

interface MobileLinkProps extends MobileNavigationProps {
  item: NavigationItem;
}

export function MobileNavigation({ activeRoute, onNavigate }: MobileNavigationProps) {
  const primaryItems = navigationItems.slice(0, 4);
  return (
    <nav aria-label="Mobile primary" className="mobile-navigation">
      {primaryItems.map((item) => (
        <MobileLink activeRoute={activeRoute} item={item} key={item.id} onNavigate={onNavigate} />
      ))}
    </nav>
  );
}

function MobileLink({ activeRoute, item, onNavigate }: MobileLinkProps) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
    onNavigate(item.id);
  }

  return (
    <a
      aria-current={activeRoute === item.id ? "page" : undefined}
      href={`${item.path}${window.location.search}`}
      onClick={handleClick}
    >
      <Icon name={item.icon} size={19} />
      <span>{item.shortLabel}</span>
    </a>
  );
}
