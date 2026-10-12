import { useState } from "react";
import { LuArrowLeft, LuBookOpen, LuUsers } from "react-icons/lu";
import { Link } from "react-router-dom";
import { CharactersTab } from "../components/profile/CharactersTab";
import { ClassGuidesTab } from "../components/profile/ClassGuidesTab";
import { Button } from "../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";

// Dedicated, Warcraft-themed profile page (feature 008 / US1): promotes the former in-chat
// profile modal to a routed page with two tabs — Characters and Class Guides. Feature 010:
// the tabs are the shared Radix-based Tabs (arrow keys, aria-selected); both panels are
// `forceMount`ed and hidden via data-state so switching preserves in-progress state (FR-007).
// Profile revamp: card-based layout; the tabs use the underline ("line") variant.

type Tab = "characters" | "guides";

export default function ProfilePage() {
  const [tab, setTab] = useState<Tab>("characters");

  return (
    <div className="profile-page">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <header className="flex flex-col gap-4">
          <Button asChild variant="ghost" size="sm" className="-ml-2 w-fit text-muted-foreground">
            <Link to="/app">
              <LuArrowLeft />
              Back to chat
            </Link>
          </Button>
          <div>
            <h1 className="profile-page-title">Your Profile</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Your characters, raid roles, and the shared class-guide library.
            </p>
          </div>
        </header>

        <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="gap-6">
          <TabsList
            variant="line"
            aria-label="Profile sections"
            className="w-full justify-start border-b border-border pb-1"
          >
            <TabsTrigger value="characters" className="flex-none px-3 after:bg-primary dark:data-[state=active]:text-glow">
              <LuUsers />
              Characters
            </TabsTrigger>
            <TabsTrigger value="guides" className="flex-none px-3 after:bg-primary dark:data-[state=active]:text-glow">
              <LuBookOpen />
              Class Guides
            </TabsTrigger>
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
