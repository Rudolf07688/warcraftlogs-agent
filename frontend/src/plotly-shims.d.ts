// Minimal ambient declarations for the untyped Plotly packages (US2). We only use
// the factory + a dist build, so loose typing here keeps the build green without
// pulling in @types/react-plotly.js.
declare module "react-plotly.js/factory" {
  import type { ComponentType } from "react";
  const createPlotlyComponent: (plotly: unknown) => ComponentType<{
    data: unknown[];
    layout?: Record<string, unknown>;
    config?: Record<string, unknown>;
    style?: Record<string, unknown>;
    useResizeHandler?: boolean;
    className?: string;
  }>;
  export default createPlotlyComponent;
}

declare module "plotly.js-dist-min" {
  const Plotly: unknown;
  export default Plotly;
}
