import type { SVGProps } from "react";

export type IconName =
  | "overview"
  | "spark"
  | "layers"
  | "threads"
  | "plug"
  | "settings"
  | "arrow"
  | "check"
  | "copy"
  | "download"
  | "chevron"
  | "search"
  | "shield"
  | "clock"
  | "token"
  | "moon"
  | "sun"
  | "monitor"
  | "refresh"
  | "info"
  | "file"
  | "terminal"
  | "network"
  | "database";

interface IconProps extends SVGProps<SVGSVGElement> {
  name: IconName;
  size?: number;
}

const PATHS: Record<IconName, string> = {
  overview: "M4 13h6V4H4v9Zm0 7h6v-4H4v4Zm10 0h6v-9h-6v9Zm0-16v4h6V4h-6Z",
  spark: "m12 2 1.8 5.2L19 9l-5.2 1.8L12 16l-1.8-5.2L5 9l5.2-1.8L12 2Zm6 13 .9 2.6 2.6.9-2.6.9L18 22l-.9-2.6-2.6-.9 2.6-.9L18 15Z",
  layers: "m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5m-18 4 9 5 9-5",
  threads: "M7 8h10M7 12h7m-9 8 2.6-3H18a3 3 0 0 0 3-3V6a3 3 0 0 0-3-3H6a3 3 0 0 0-3 3v8a3 3 0 0 0 2 2.8V20Z",
  plug: "m8 12 8-8m-6-1 3 3m-7 6 6 6m1-4 3 3m-8-5-3 3a4.2 4.2 0 0 0 6 6l3-3",
  settings: "M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm7-3.5 2-1-2-3-2.2.3-1.3-1.2L15 5l-3-1-1.5 1.6-1.7.6L6.5 5 4 7.5l1.2 2.3-.3 1.8L3 13l1 3 2.2.3 1.3 1.2L8 20l3 1 1.5-1.6 1.7-.6 2.3 1.2 2.5-2.5-1.2-2.3.3-1.8L21 12h-2Z",
  arrow: "M5 12h14m-5-5 5 5-5 5",
  check: "m5 12 4 4L19 6",
  copy: "M9 8h10v12H9V8Zm-4 8H4V4h10v1",
  download: "M12 3v12m-5-5 5 5 5-5M5 20h14",
  chevron: "m8 10 4 4 4-4",
  search: "m20 20-4.2-4.2m2.2-5.3a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z",
  shield: "M12 3 5 6v5c0 4.7 2.8 8.2 7 10 4.2-1.8 7-5.3 7-10V6l-7-3Zm-3 9 2 2 4-5",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13v5l3 2",
  token: "M12 3 4.5 7.5v9L12 21l7.5-4.5v-9L12 3Zm0 0v18m-7.5-13.5L12 12l7.5-4.5",
  moon: "M20 15.2A8 8 0 0 1 8.8 4 8.5 8.5 0 1 0 20 15.2Z",
  sun: "M12 3v2m0 14v2m9-9h-2M5 12H3m15.4-6.4-1.4 1.4M7 17l-1.4 1.4m12.8 0L17 17M7 7 5.6 5.6M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  monitor: "M4 5h16v11H4V5Zm5 15h6m-3-4v4",
  refresh: "M20 7v5h-5M4 17v-5h5m10.2 0A7.5 7.5 0 0 0 6.4 7M4.8 12A7.5 7.5 0 0 0 17.6 17",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-10v6m0-10v.1",
  file: "M6 3h8l4 4v14H6V3Zm8 0v5h4",
  terminal: "m5 8 4 4-4 4m7 0h7",
  network: "M12 3v5m0 8v5M3 12h5m8 0h5M8.5 8.5l-3-3m10 3 3-3m-10 10-3 3m10-3 3 3M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z",
  database: "M19 5c0 1.1-3.1 2-7 2S5 6.1 5 5s3.1-2 7-2 7 .9 7 2Zm0 0v14c0 1.1-3.1 2-7 2s-7-.9-7-2V5m14 7c0 1.1-3.1 2-7 2s-7-.9-7-2",
};

export function Icon({ name, size = 20, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      {...props}
    >
      <path d={PATHS[name]} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}
