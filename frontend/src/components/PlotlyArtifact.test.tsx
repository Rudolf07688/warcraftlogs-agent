import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { PlotlyArtifact } from "./PlotlyArtifact";

// jsdom can't run Plotly's WebGL/canvas code; the chart container is what is under test.
vi.mock("plotly.js-dist-min", () => ({ default: {} }));
vi.mock("react-plotly.js/factory", () => ({ default: () => () => null }));

afterEach(cleanup);

describe("PlotlyArtifact", () => {
  it("renders a stored artifact's chart container", () => {
    render(
      <PlotlyArtifact
        artifact={{
          artifact_id: "a1",
          kind: "line",
          title: "DPS",
          figure: { data: [{ type: "scatter", x: [1], y: [2] }], layout: {} },
          message_seq: 1,
        }}
      />,
    );
    expect(screen.getByRole("img", { name: "Chart: DPS" })).toBeTruthy();
  });
});
