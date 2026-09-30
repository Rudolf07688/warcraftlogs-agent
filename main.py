"""Convenience launcher: `uv run python main.py`.

The real logic lives in `wcl_agent.cli`, which also backs the `wcl` command.
"""

from wcl_agent.cli import run

if __name__ == "__main__":
    run()
