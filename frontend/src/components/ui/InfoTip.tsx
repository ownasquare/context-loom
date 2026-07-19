import { useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Icon } from "../icons/Icon";

interface InfoTipProps {
  children: ReactNode;
  label: string;
}

export function InfoTip({ children, label }: InfoTipProps) {
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const tooltipId = useId();
  const rootRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    function closeOnOutsidePress(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
        setDismissed(true);
      }
    }

    document.addEventListener("pointerdown", closeOnOutsidePress);
    return () => document.removeEventListener("pointerdown", closeOnOutsidePress);
  }, [open]);

  return (
    <span
      className={`info-tip${open ? " info-tip--open" : ""}${dismissed ? " info-tip--dismissed" : ""}`}
      onMouseLeave={() => setDismissed(false)}
      ref={rootRef}
    >
      <button
        aria-describedby={tooltipId}
        aria-label={`About ${label}`}
        className="info-tip__trigger"
        onBlur={() => setDismissed(false)}
        onClick={() => {
          setDismissed(false);
          setOpen((current) => !current);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setOpen(false);
            setDismissed(true);
          }
        }}
        type="button"
      >
        <Icon name="info" size={14} />
      </button>
      <span className="info-tip__content" id={tooltipId} role="tooltip">{children}</span>
    </span>
  );
}
