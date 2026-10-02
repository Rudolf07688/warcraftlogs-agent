import { lazy, Suspense, useMemo } from "react";
import type { ChartArtifact } from "../types";

// Plotly is heavy, so load it (and the React wrapper factory) only when a chart is
// actually rendered — keeps it out of the main bundle (US2 / polish T050).
const Plot = lazy(async () => {
  const [{ default: createPlotlyComponent }, plotlyMod] = await Promise.all([
    import("react-plotly.js/factory"),
    import("plotly.js-dist-min"),
  ]);
  const Plotly = (plotlyMod as { default?: unknown }).default ?? plotlyMod;
  return { default: createPlotlyComponent(Plotly) };
});

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function PlotlyArtifact({ artifact }: { artifact: ChartArtifact }) {
  const reduced = useMemo(prefersReducedMotion, []);

  const layout = useMemo(
    () => ({
      ...artifact.figure.layout,
      autosize: true,
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#c7d0db" },
      // Honor reduced-motion: no animated transitions (hover/zoom still work).
      transition: reduced ? { duration: 0 } : undefined,
    }),
    [artifact.figure.layout, reduced],
  );

  const config = useMemo(
    () => ({ responsive: true, displayModeBar: false, displaylogo: false }),
    [],
  );

  return (
    <div className="chart-artifact" role="img" aria-label={`Chart: ${artifact.title}`}>
      <Suspense fallback={<div className="chart-loading">Rendering chart…</div>}>
        <Plot
          data={artifact.figure.data}
          layout={layout}
          config={config}
          useResizeHandler
          style={{ width: "100%", height: "320px" }}
        />
      </Suspense>
    </div>
  );
}
