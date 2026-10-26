import type { CSSProperties } from "react";
import { classColor, initials } from "../../lib/classColors";
import { cn } from "../../lib/utils";
import { Avatar, AvatarFallback } from "../ui/avatar";

// A round avatar with the character's initials, ringed and tinted in their class colour. Shared
// by the profile's character list and the chat's confirmation card (feature 031), so a friend
// looks the same in both; its own module keeps the lazy profile page out of the chat bundle.
export function ClassAvatar({
  char,
  className,
}: {
  char: { name: string; class_name: string | null };
  className?: string;
}) {
  const color = classColor(char.class_name);
  const style: CSSProperties | undefined = color
    ? { borderColor: color, color, background: `color-mix(in oklch, ${color} 16%, transparent)` }
    : undefined;
  return (
    <Avatar className={cn("border-2 border-border", className)} aria-hidden="true">
      <AvatarFallback className="bg-muted font-display font-semibold text-glow" style={style}>
        {initials(char.name)}
      </AvatarFallback>
    </Avatar>
  );
}
