# Developer team prompt

- **Updated last: 2026-10-25**

```
Create an agent team to take control of this shortcut board and complete more or less 21 points worth of work.

We need a:
  - product owner (planner, final reviewer and ultimately just team lead - responsible for the success of the project)
    - Orders the backlog in a manner that optimizes developer path, minimizing cost-of-change for the known future tasks
    - Runs the final agent /qa-sweep command, reads the reports, and decides which of the reported items are crucial to fix now before delivery of feature
  - scrum master
    - manages communication between all agents
    - Developers can speak to each other, but not to product owner directly
    - product owner may also not communicate to devs directly
  - responsible to make sure developers get sole ownership of the specific files they need to touch.
  - leads the "speckit" process with the devs (/speckit-speckit-plan; \/speckit-tasks; \/compact;
      \/speckit-implement)
  - responsible to clarify and sign-off on specs generate
  - 2x agentic developers
    - They should have access to all the mcps and skills
    - They should be able to spin up their own sub-agentssible.
      - Ultimately scrum master must confirm that even sub-agent tasks don't touch the same files.
    - They run through the speckit workflow initiated by the scrum master
    - Must use tools like the gitnexus mcps to traverse tius etc. Use shadcn when building frontend elements


Also, then agents must use a mixture of sonnet and opus models advised by the scrum master based on the complexity of the task (including effort levels)

One detail on the shortcut board: Any deferred item from the qa-sweep that lands on the shortcut board must be clearly
labelled to separate them from the rest of tickets as lower priority. Every qa-sweep that lands must first compare to
previously created tickets and either merged, updated (latest date of finding, any new details found that can be added to 
the context as a breadcrumb) or cleaned up so that no duplicate qa tasks on the backlog.
```

Added:

```
Also, then agents must use a mixture of sonnet and opus models advised by the scrum master based on the complexity of the task (includingeffort levels)
``

```
One detail on the shortcut board: Any deferred item from the qa-sweep that lands on the shortcut board must be clearly
labelled to separate them from the rest of tickets as lower priority. Every qa-sweep that lands must first compare to
previously created tickets and either merged, updated (latest date of finding, any new details found that can be added to 
the context as a breadcrumb) or cleaned up so that no duplicate qa tasks on the backlog.
```