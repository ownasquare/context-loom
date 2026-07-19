import type { ReactNode } from "react";

type BadgeTone = "neutral" | "success" | "warning" | "danger" | "accent" | "info";

interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  dot?: boolean;
}

export function Badge({ children, tone = "neutral", dot = false }: BadgeProps) {
  return (
    <span className={`badge badge--${tone}`}>
      {dot ? <span aria-hidden="true" className="badge__dot" /> : null}
      {children}
    </span>
  );
}
