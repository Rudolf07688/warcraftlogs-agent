import { type CSSProperties, useState } from "react";
import { classColor, initials } from "../../lib/classColors";
import { cn } from "../../lib/utils";
import { Avatar, AvatarFallback } from "../ui/avatar";

// Feature 075: only Blizzard's render host is ever put in <img src> (the server checks too).
const PORTRAIT_PREFIX = "https://render.worldofwarcraft.com/";

// A round avatar with the character's initials, ringed and tinted in their class colour. Shared
// by the profile's character list and the chat's confirmation card (feature 031), so a friend
// looks the same in both; its own module keeps the lazy profile page out of the chat bundle.
// Feature 075: with a `portrait_url` the Battle.net portrait covers the initials once it has
// loaded, in the same box (no layout shift); until then, or if it fails, the initials show. A
// plain lazy <img>, because the registry's AvatarImage preloads eagerly with `new Image()`.
export function ClassAvatar({
  char,
  className,
}: {
  char: { name: string; class_name: string | null; portrait_url?: string | null };
  className?: string;
}) {
  const [loaded, setLoaded] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const color = classColor(char.class_name);
  const style: CSSProperties | undefined = color
    ? { borderColor: color, color, background: `color-mix(in oklch, ${color} 16%, transparent)` }
    : undefined;
  const url = char.portrait_url?.startsWith(PORTRAIT_PREFIX) ? char.portrait_url : null;
  return (
    <Avatar className={cn("border-2 border-border", className)} aria-hidden="true">
      <AvatarFallback className="bg-muted font-display font-semibold text-glow" style={style}>
        {initials(char.name)}
      </AvatarFallback>
      {url && failed !== url && (
        <img
          src={url}
          alt=""
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          className={cn(
            "absolute inset-0 size-full rounded-full object-cover transition-opacity",
            loaded === url ? "opacity-100" : "opacity-0",
          )}
          onLoad={() => setLoaded(url)}
          onError={() => setFailed(url)}
        />
      )}
    </Avatar>
  );
}
