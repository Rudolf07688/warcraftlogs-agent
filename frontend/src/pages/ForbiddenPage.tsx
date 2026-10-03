import { Link } from "react-router-dom";

export default function ForbiddenPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-neutral-950 text-neutral-100 p-4">
      <div className="max-w-sm space-y-3 text-center">
        <h1 className="text-2xl font-semibold">Forbidden</h1>
        <p className="text-sm text-neutral-400">
          You don’t have access to this page.
        </p>
        <Link to="/app" className="inline-block text-indigo-400 hover:text-indigo-300">
          Back to the app
        </Link>
      </div>
    </div>
  );
}
