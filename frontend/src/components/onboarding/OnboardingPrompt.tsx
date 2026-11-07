import { useState } from "react";
import { LuSparkles } from "react-icons/lu";
import { ApiError, skipOnboarding } from "../../api/restClient";
import type { ProfileSettings } from "../../types";
import { Button } from "../ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { FieldError } from "../ui/field";
import { MainSelector } from "./MainSelector";

// Feature 074 (sc-166): the welcome prompt on the profile page while the workspace's
// onboarding is pending (the server decides: never skipped and no own character). It asks
// for at least one character and offers the main selector; nothing here blocks the app, and
// "Skip for now" is stored on the server so the prompt never comes back.

export function OnboardingPrompt({
  settings,
  onChange,
}: {
  settings: ProfileSettings;
  onChange: (settings: ProfileSettings) => void;
}) {
  const [skipping, setSkipping] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function skip() {
    setSkipping(true);
    setError(null);
    try {
      onChange(await skipOnboarding());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't skip. Please try again.");
      setSkipping(false);
    }
  }

  return (
    <Card aria-label="Welcome" className="border-primary/40">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <LuSparkles className="text-primary" />
          Welcome! Tell us who you play
        </CardTitle>
        <CardDescription>
          Add at least one of your characters under Characters below, and pick your main class
          and content, so answers and guides fit what you play. You can do this later.
        </CardDescription>
        <CardAction>
          <Button variant="ghost" size="sm" onClick={skip} disabled={skipping}>
            Skip for now
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <MainSelector value={settings} onSaved={onChange} />
        <FieldError>{error}</FieldError>
      </CardContent>
    </Card>
  );
}
