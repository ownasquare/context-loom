import type { HealthStatus } from "../../api/types";
import type { IconName } from "../icons/Icon";

export interface PrivacyStatusPresentation {
  chip: string;
  detail: string;
  icon: IconName;
  tone: "neutral" | "safe" | "warning";
  title: string;
}

export function privacyStatusFor(
  health: HealthStatus | undefined,
  isPending: boolean,
): PrivacyStatusPresentation {
  if (health?.outbound_allowed && health.retain_message_content) {
    return {
      chip: "Outbound + retention",
      detail: "Selected context may leave · messages retained",
      icon: "network",
      tone: "warning",
      title: "Outbound and retention on",
    };
  }
  if (health?.outbound_allowed) {
    return {
      chip: "Outbound enabled",
      detail: "Selected context may leave this machine",
      icon: "network",
      tone: "warning",
      title: "Outbound access on",
    };
  }
  if (health?.retain_message_content) {
    return {
      chip: "Retention on",
      detail: "Prepared messages are kept locally",
      icon: "clock",
      tone: "warning",
      title: "Message retention on",
    };
  }
  if (health) {
    return {
      chip: "Local",
      detail: "Outbound blocked · messages not retained",
      icon: "shield",
      tone: "safe",
      title: "Local by default",
    };
  }
  if (isPending) {
    return {
      chip: "Checking",
      detail: "Reading local settings",
      icon: "clock",
      tone: "neutral",
      title: "Checking privacy",
    };
  }
  return {
    chip: "Status unavailable",
    detail: "Open Settings to review",
    icon: "info",
    tone: "warning",
    title: "Privacy status unavailable",
  };
}
