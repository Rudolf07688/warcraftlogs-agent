import { Link } from "react-router-dom";
import { AuthShell } from "../components/AuthShell";
import { Button } from "../components/ui/button";

export default function ForbiddenPage() {
  return (
    <AuthShell>
      <div className="space-y-3 text-center">
        <h1 className="text-2xl font-semibold">Forbidden</h1>
        <p className="text-sm text-muted-foreground">You don’t have access to this page.</p>
        <Button asChild variant="secondary">
          <Link to="/app">Back to the app</Link>
        </Button>
      </div>
    </AuthShell>
  );
}
