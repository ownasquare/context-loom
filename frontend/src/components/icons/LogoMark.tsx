interface LogoMarkProps {
  size?: number;
}

export function LogoMark({ size = 34 }: LogoMarkProps) {
  return (
    <svg aria-hidden="true" className="logo-mark" height={size} viewBox="0 0 36 36" width={size}>
      <rect fill="currentColor" height="36" rx="11" width="36" />
      <path d="M10 11.5h10.5a5 5 0 0 1 0 10H15a3.5 3.5 0 0 0 0 7h11" fill="none" stroke="var(--logo-thread)" strokeLinecap="round" strokeWidth="3" />
      <circle cx="10" cy="11.5" fill="var(--logo-pin)" r="2.5" />
      <circle cx="26" cy="28.5" fill="var(--logo-pin)" r="2.5" />
    </svg>
  );
}
