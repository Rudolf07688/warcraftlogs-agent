import type { ReactNode } from "react";
import { LuX } from "react-icons/lu";
import { cn } from "../lib/utils";
import { Alert, AlertDescription } from "./ui/alert";
import { Button } from "./ui/button";

// Feature 010: the one error / notice strip used by the admin and profile pages (FR-009).

export interface StatusAlertProps {
  tone: "error" | "notice";
  children: ReactNode;
  /** When given, renders a Dismiss button on the right. */
  onDismiss?: () => void;
  className?: string;
}

export function StatusAlert({ tone, children, onDismiss, className }: StatusAlertProps) {
  return (
    <Alert
      variant={tone === "error" ? "destructive" : "default"}
      className={cn(
        "items-center border-border",
        tone === "notice" && "border-primary/40 text-glow",
        onDismiss && "grid-cols-[0_1fr_auto]",
        className,
      )}
    >
      <AlertDescription className={cn("break-words", tone === "notice" && "text-foreground")}>
        {children}
      </AlertDescription>
      {onDismiss && (
        <Button
          variant="ghost"
          size="icon"
          className="col-start-3 -my-1 size-7"
          aria-label="Dismiss"
          title="Dismiss"
          onClick={onDismiss}
        >
          <LuX />
        </Button>
      )}
    </Alert>
  );
}
