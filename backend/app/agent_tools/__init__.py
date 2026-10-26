"""Backend-side agent tools: tools that need the database or the backend services (design C6).

They are registered through ``wcl_agent.agent.build_agent(extra_groups=…)`` so ``wcl_agent``
never imports the backend.
"""
