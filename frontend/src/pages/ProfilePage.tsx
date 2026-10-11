import { useState } from "react";
import { Link } from "react-router-dom";
import { CharactersTab } from "../components/profile/CharactersTab";
import { ClassGuidesTab } from "../components/profile/ClassGuidesTab";
import { Button } from "../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";

// Dedicated, Warcraft-themed profile page (feature 008 / US1): promotes the former in-chat
// profile modal to a routed page with two tabs — Characters and Class Guides. Feature 010:
// the tabs are the shared Radix-based Tabs (arrow keys, aria-selected); both panels are
// `forceMount`ed and hidden via data-state so switching preserves in-progress state (FR-007).

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
        <Button asChild variant="secondary">
          <Link to="/app">← Back to chat</Link>
        </Button>
      </header>

      <div className="profile-page-body">
        <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
          <TabsList aria-label="Profile sections" className="mb-3">
            <TabsTrigger value="characters">Characters</TabsTrigger>
            <TabsTrigger value="guides">Class Guides</TabsTrigger>
          </TabsList>
          <TabsContent value="characters" forceMount className="data-[state=inactive]:hidden">
            <CharactersTab />
          </TabsContent>
          <TabsContent value="guides" forceMount className="data-[state=inactive]:hidden">
            <ClassGuidesTab active={tab === "guides"} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
