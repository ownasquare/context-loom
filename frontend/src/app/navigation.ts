import type { IconName } from "../components/icons/Icon";

export type RouteId = "overview" | "hydrate" | "resources" | "threads" | "integrations" | "settings";

export interface NavigationItem {
  id: RouteId;
  label: string;
  shortLabel: string;
  path: string;
  icon: IconName;
}

export const navigationItems: readonly NavigationItem[] = [
  { id: "overview", label: "Home", shortLabel: "Home", path: "/", icon: "overview" },
  { id: "hydrate", label: "Prepare", shortLabel: "Prepare", path: "/hydrate", icon: "threads" },
  { id: "resources", label: "Project files", shortLabel: "Files", path: "/resources", icon: "file" },
  { id: "threads", label: "Savings", shortLabel: "Savings", path: "/threads", icon: "token" },
  { id: "integrations", label: "Connections", shortLabel: "Connect", path: "/integrations", icon: "plug" },
  { id: "settings", label: "Settings", shortLabel: "Settings", path: "/settings", icon: "settings" },
] as const;

export function routeFromPath(pathname: string): RouteId {
  const item = navigationItems.find((candidate) => candidate.path === pathname);
  return item?.id ?? "overview";
}

export function navigationItemFor(route: RouteId): NavigationItem {
  return navigationItems.find((item) => item.id === route) ?? navigationItems[0]!;
}
