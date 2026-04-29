# Agent skills framework (Task 4.4)

Planned location for reusable **skills** (prompt fragments + tool policies) shared
across OpenHands, Goose, and opencode images.

**MVP:** skills live as versioned files under `agentic/skills/` (to be added) and
are bind-mounted or copied into images at build time. No runtime registry yet.

**Next steps:** define `skill.toml` schema, loader in agent launchers.
