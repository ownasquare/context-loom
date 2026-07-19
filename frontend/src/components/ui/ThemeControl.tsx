import type { ThemePreference } from "../../api/types";
import { useTheme } from "../../app/theme";
import { Icon } from "../icons/Icon";
import type { IconName } from "../icons/Icon";

const OPTIONS: readonly { value: ThemePreference; label: string; icon: IconName }[] = [
  { value: "light", label: "Light", icon: "sun" },
  { value: "dark", label: "Dark", icon: "moon" },
  { value: "system", label: "System", icon: "monitor" },
];

export function ThemeControl() {
  const { preference, setPreference } = useTheme();
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);

  function moveSelection(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      nextIndex = (index + 1) % OPTIONS.length;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      nextIndex = (index - 1 + OPTIONS.length) % OPTIONS.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = OPTIONS.length - 1;
    }
    if (nextIndex === null) {
      return;
    }
    event.preventDefault();
    const option = OPTIONS[nextIndex];
    if (option) {
      setPreference(option.value);
      buttons.current[nextIndex]?.focus();
    }
  }

  return (
    <div aria-label="Color theme" className="segmented-control" role="radiogroup">
      {OPTIONS.map((option, index) => (
        <button
          aria-checked={preference === option.value}
          className="segmented-control__option"
          key={option.value}
          onClick={() => setPreference(option.value)}
          onKeyDown={(event) => moveSelection(event, index)}
          ref={(node) => { buttons.current[index] = node; }}
          role="radio"
          tabIndex={preference === option.value ? 0 : -1}
          type="button"
        >
          <Icon name={option.icon} size={16} />
          <span>{option.label}</span>
        </button>
      ))}
    </div>
  );
}
import { useRef } from "react";
import type { KeyboardEvent } from "react";
