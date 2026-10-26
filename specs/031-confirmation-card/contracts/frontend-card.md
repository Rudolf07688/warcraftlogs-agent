# Contract: ProposalCard, profileEvents, App wiring

Design: `participants-and-confirmation.html#card`, `#refresh`, `#edges`.

## `ProposalCard` (`frontend/src/components/ProposalCard.tsx`)

```ts
interface Props {
  proposal: ProfileProposal;
  onFollowUp?: (conversationId: string, message: Message) => void;
}
```

- Parts: `Card` (+ Header/Title/Description/Action/Content/Footer), `ItemGroup`/`Item variant="outline"
  size="sm"` with `ItemMedia` (`ClassAvatar`), `ItemContent`/`ItemTitle`/`ItemDescription`,
  `ItemActions` (`Badge`), `Button` (default "Approve N" + outline "Cancel") with `Spinner`, and
  `Alert` (error / expired).
- Title: "Proposed profile changes". Description: "Nothing changes until you approve · Expires HH:MM"
  (pending), "Nothing to apply" (N = 0), and the end-state text: "Applied: 3 added, 1 skipped" /
  "Cancelled. Your profile is unchanged." / "This proposal expired. Ask Barnaby again.". The status
  badge sits in `CardAction`.
- Busy: the first click disables both buttons and shows the spinner in the clicked one until the
  answer arrives.
- Expired check at render and before any request (`Date.now() >= Date.parse(expires_at)`).
- `role="group"` + `aria-labelledby` the title id; a visually hidden `aria-live="polite"` region holds
  the last state text; the card root (`tabIndex={-1}`) gets focus after an action.
- Names and realms are plain text nodes.
- After approve: `onFollowUp(proposal.conversation_id, follow_up)` when `follow_up` isn't null, and
  `notifyProfileChanged({proposal, targets})` when any item was applied.
- `useProfileChanged`: a broadcast for the same `proposal.id` replaces the card's state.
- A new `proposal` prop (reload) replaces the state.

## `profileEvents` (`frontend/src/lib/profileEvents.ts`)

```ts
export function notifyProfileChanged(change: ProfileChange): void;     // other tabs + this tab
export function useProfileChanged(cb: (change: ProfileChange) => void): void;  // subscribe while mounted
```

## Subscribers

- `CharactersTab`: any change → `refresh()`.
- `WelcomePanel`: `targets.includes("own")` → `load()`.
- `ProposalCard`: the same id → take `change.proposal`.

## App / MessageList

- `case "proposal"`: push into `pendingProposalsRef`. `done`: attach as `message.proposals`. `error`:
  move them to `looseProposals`. `sendText`/`newChat`: reset. `selectConversation`: `looseProposals =
  detail.proposals.filter(p => p.message_seq == null)`.
- `MessageList` props gain `looseProposals: ProfileProposal[]` and `onFollowUp`. Cards render after
  the message's charts. Standalone cards render after the messages, before the live message.
