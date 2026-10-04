import { useState } from "react";
import { Link } from "react-router-dom";
import { CharactersTab } from "../components/profile/CharactersTab";
import { ClassGuidesTab } from "../components/profile/ClassGuidesTab";

// Dedicated, Warcraft-themed profile page (feature 008 / US1): promotes the former in-chat
// profile modal to a routed page with two tabs — Characters and Class Guides. Both tabs stay
// mounted and are toggled with `hidden`, so switching tabs preserves each tab's in-progress
// state (quickstart US1 step 3).

type Tab = "characters" | "guides";

export default function ProfilePage() {
  const [tab, setTab] = useState<Tab>("characters");

  return (
    <div className="profile-page">
      <header className="profile-page-header">
        <div className="profile-page-title">
          <h1>Your Profile</h1>
          <p className="profile-page-sub">Characters, raid roles, and the class-guide library.</p>
        </div>
        <Link className="profile-back" to="/app">
          ← Back to chat
        </Link>
      </header>

      <nav className="profile-tabs" role="tablist" aria-label="Profile sections">
        <button
          role="tab"
          aria-selected={tab === "characters"}
          className={`profile-tab${tab === "characters" ? " is-active" : ""}`}
          onClick={() => setTab("characters")}
        >
          Characters
        </button>
        <button
          role="tab"
          aria-selected={tab === "guides"}
          className={`profile-tab${tab === "guides" ? " is-active" : ""}`}
          onClick={() => setTab("guides")}
        >
          Class Guides
        </button>
      </nav>

      <div className="profile-page-body">
        <div hidden={tab !== "characters"}>
          <CharactersTab />
        </div>
        <div hidden={tab !== "guides"}>
          <ClassGuidesTab active={tab === "guides"} />
        </div>
      </div>
    </div>
  );
}
