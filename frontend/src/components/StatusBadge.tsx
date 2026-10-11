import type { ComponentProps, ReactNode } from "react";
import type { GuideStatus } from "../types";
import { Badge } from "./ui/badge";

// Feature 010: one place for "what colour is this status" (spec FR-009 / FR-010).
// Tones are semantic; the Badge variant is an implementation detail of this module.

export type Tone = "ok" | "pending" | "failed" | "warn" | "neutral";

type BadgeVariant = NonNullable<ComponentProps<typeof Badge>["variant"]>;

const TONE_VARIANT: Record<Tone, BadgeVariant> = {
  ok: "success",
  pending: "secondary",
  failed: "destructive",
  warn: "warning",
  neutral: "outline",
};

export const GUIDE_TONE: Record<GuideStatus, Tone> = {
  ready: "ok",
  pending: "pending",
  failed: "failed",
  none: "neutral",
};

// AdminUser.status / Invitation.status are server-defined strings; unknown → neutral.
export const USER_TONE: Record<string, Tone> = { active: "ok", disabled: "failed" };
export const INVITE_TONE: Record<string, Tone> = {
  open: "pending",
  accepted: "ok",
  revoked: "neutral",
  expired: "warn",
};

export function toneFor(map: Record<string, Tone>, status: string): Tone {
  return map[status] ?? "neutral";
}

// Guide-status wording: short form beside a character, library form in the roster.
export const GUIDE_LABEL_SHORT: Record<GuideStatus, string> = {
  none: "",
  pending: "guide loading…",
  ready: "guide ready",
  failed: "guide unavailable",
};
export const GUIDE_LABEL_LIBRARY: Record<GuideStatus, string> = {
  none: "Not downloaded",
  pending: "Generating…",
  ready: "Downloaded",
  failed: "Failed",
};

export interface StatusBadgeProps {
  tone: Tone;
  title?: string;
  className?: string;
  children: ReactNode;
}

export function StatusBadge({ tone, title, className, children }: StatusBadgeProps) {
  return (
    <Badge variant={TONE_VARIANT[tone]} title={title} className={className}>
      {children}
    </Badge>
  );
}
