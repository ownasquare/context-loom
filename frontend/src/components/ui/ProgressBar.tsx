interface ProgressBarProps {
  value: number;
  label: string;
  tone?: "accent" | "success" | "warning";
}

export function ProgressBar({ value, label, tone = "accent" }: ProgressBarProps) {
  const clampedValue = Math.min(Math.max(value, 0), 1);
  return (
    <div className="progress" title={`${Math.round(clampedValue * 100)}%`}>
      <span className="sr-only">{label}: {Math.round(clampedValue * 100)}%</span>
      <span aria-hidden="true" className="progress__track">
        <span className={`progress__fill progress__fill--${tone}`} style={{ width: `${clampedValue * 100}%` }} />
      </span>
    </div>
  );
}
