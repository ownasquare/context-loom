export function formatRelativeTime(isoDate: string | null): string {
  if (!isoDate) {
    return "Never";
  }

  const deltaSeconds = Math.round((new Date(isoDate).getTime() - Date.now()) / 1000);
  const absoluteSeconds = Math.abs(deltaSeconds);
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

  if (absoluteSeconds < 60) {
    return formatter.format(deltaSeconds, "second");
  }
  if (absoluteSeconds < 3_600) {
    return formatter.format(Math.round(deltaSeconds / 60), "minute");
  }
  if (absoluteSeconds < 86_400) {
    return formatter.format(Math.round(deltaSeconds / 3_600), "hour");
  }
  return formatter.format(Math.round(deltaSeconds / 86_400), "day");
}

export function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function formatPercent(value: number): string {
  return new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 }).format(value);
}

export function shortHash(hash: string): string {
  return `${hash.slice(0, 8)}…${hash.slice(-5)}`;
}

export function titleCase(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
