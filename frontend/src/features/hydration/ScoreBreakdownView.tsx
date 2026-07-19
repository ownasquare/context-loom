import type { ScoreBreakdown } from "../../api/types";

interface ScoreBreakdownViewProps {
  score: ScoreBreakdown;
}

const SCORE_KEYS: readonly { key: keyof ScoreBreakdown; label: string }[] = [
  { key: "lexical", label: "Lexical" },
  { key: "dense", label: "Similarity" },
  { key: "direct_reference", label: "Direct ref" },
  { key: "recency", label: "Freshness" },
  { key: "authority", label: "Authority" },
  { key: "thread_affinity", label: "Thread" },
];

export function ScoreBreakdownView({ score }: ScoreBreakdownViewProps) {
  return (
    <div className="score-breakdown">
      {SCORE_KEYS.map(({ key, label }) => (
        <div className="score-breakdown__row" key={key}>
          <span>{label}</span>
          <span aria-hidden="true" className="score-breakdown__track">
            <span style={{ width: `${Math.min(Math.max(score[key], 0), 1) * 100}%` }} />
          </span>
          <strong>{score[key].toFixed(2)}</strong>
        </div>
      ))}
      <div className="score-breakdown__total"><span>Weighted total</span><strong>{score.total.toFixed(2)}</strong></div>
    </div>
  );
}
