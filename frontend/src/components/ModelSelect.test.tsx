import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ModelSelect } from "./ModelSelect";

// Feature 033 (sc-251): a read-only label names the live LLM provider.

afterEach(cleanup);

const props = { models: ["m1", "m2"], value: "m1", onChange: () => {} };

describe("ModelSelect provider label", () => {
  it("names Vertex AI", () => {
    render(<ModelSelect {...props} provider="vertex" />);
    expect(screen.getByText("Vertex AI")).toBeTruthy();
    expect(screen.queryByText("Anthropic API")).toBeNull();
  });

  it("names the Anthropic API", () => {
    render(<ModelSelect {...props} provider="anthropic" />);
    expect(screen.getByText("Anthropic API")).toBeTruthy();
  });

  it("shows no label until the provider is known", () => {
    render(<ModelSelect {...props} />);
    expect(screen.queryByText("Vertex AI")).toBeNull();
    expect(screen.queryByText("Anthropic API")).toBeNull();
  });
});
