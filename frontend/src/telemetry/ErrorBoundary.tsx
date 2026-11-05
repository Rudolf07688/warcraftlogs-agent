import { Component, useEffect, type ErrorInfo, type ReactNode } from "react";
import { useRouteError } from "react-router-dom";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { reportError } from "./context";

// Feature 060 (sc-416, spec §7.1): an error boundary per panel and one around the app shell.
// It reports the way Faro's own ErrorBoundary does (an error named "React ErrorBoundary <type>"
// whose stack is the component stack), through the registered Faro instance, so the Faro
// packages stay out of the main bundle (057). The fallback never shows the error: its message
// can carry model or WCL text.

interface Props {
  /** The boundary's name on the report: shell, sidebar, messages, composer. */
  name: string;
  /** The panel starts clean when this changes (the chat panels pass the conversation id). */
  resetKey?: string | null;
  children: ReactNode;
}

interface State {
  failed: boolean;
}

function withComponentStack(error: unknown, info: ErrorInfo): Error {
  const original = error instanceof Error ? error : new Error(String(error));
  if (!info.componentStack) return original;
  const report = new Error(original.message);
  report.name = `React ErrorBoundary ${original.name}`;
  report.stack = info.componentStack;
  return report;
}

export class TelemetryBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    reportError(withComponentStack(error, info), { boundary: this.props.name });
  }

  componentDidUpdate(prev: Props): void {
    if (this.state.failed && prev.resetKey !== this.props.resetKey) this.setState({ failed: false });
  }

  private retry = () => this.setState({ failed: false });

  render() {
    if (!this.state.failed) return this.props.children;
    return <PanelFallback onRetry={this.retry} />;
  }
}

/**
 * The route tree's errorElement. A data router catches route render errors itself, before
 * the shell boundary around RouterProvider ever sees them, and its default page prints the
 * message and stack. This reports like the shell boundary and shows the same plain fallback.
 */
export function RouteErrorFallback() {
  const error = useRouteError();
  useEffect(() => {
    reportError(error instanceof Error ? error : new Error(String(error)), { boundary: "shell" });
  }, [error]);
  return <PanelFallback onRetry={() => window.location.reload()} />;
}

export function PanelFallback({ onRetry }: { onRetry: () => void }) {
  return (
    <Alert className="m-3 items-center border-border">
      <AlertDescription className="flex flex-wrap items-center gap-3 text-foreground">
        Something went wrong in this part of the page.
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      </AlertDescription>
    </Alert>
  );
}
