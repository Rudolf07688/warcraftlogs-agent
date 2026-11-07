import type { Raid } from "../../types";
import { Button } from "../ui/button";
import { RaidSummaryPanel } from "./RaidSummaryPanel";
import { bossSummary, raidWhen } from "./raidFormat";

interface Props {
  raid: Raid;
  analyzeDisabled: boolean;
  onAnalyze: (reportCode: string) => void;
}

/** One raid's tab body: its header, the Analyze button and the stored data. */
export function RaidTab({ raid, analyzeDisabled, onAnalyze }: Props) {
  const meta = [raid.zone, raid.guild, raidWhen(raid)].filter(Boolean).join(" · ");
  const bosses = bossSummary(raid, 8);
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-lg font-semibold" title={raid.label}>
            {raid.label}
          </h2>
          {meta && <div className="truncate text-sm text-muted-foreground">{meta}</div>}
          {bosses && <div className="truncate text-sm text-muted-foreground">{bosses}</div>}
        </div>
        <Button
          onClick={() => onAnalyze(raid.report_code)}
          disabled={analyzeDisabled}
          title={analyzeDisabled ? "Wait for the current answer to finish" : undefined}
        >
          Analyze this raid
        </Button>
      </div>
      <RaidSummaryPanel reportCode={raid.report_code} />
    </div>
  );
}
