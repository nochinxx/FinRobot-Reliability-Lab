# AGENTS.md

Rules for AI agents working in this repo:

- You may read and edit files in this repo.
- Never push directly to main.
- Never force push.
- Always create a feature branch.
- Use branch names like: agent/short-task-name.
- Make small, reviewable commits.
- Run tests when possible.
- Do not commit .env files, secrets, tokens, SSH keys, or private config.
- Ask Mario before installing dependencies.
- Open PRs instead of merging.
- Consider product, UX, safety, and marketing impact.

Python environment rules:

- Use project-specific Conda environments for Python programs.
- Do not install Python packages globally.
- Do not use global pip installs.
- Ask Mario before changing Python versions.
- Ask Mario before installing new dependencies.
- Prefer `conda create -n <project-name> python=<version>` for Python app environments.
- Activate the correct Conda environment before running Python commands.
- If this repo already has environment instructions, follow them.
- If no Python environment exists, propose one before creating it.
- Document environment setup in README.md, AGENTS.md, or docs/dev-setup.md when relevant.
- Use `uv` only for lightweight scripts or when Mario approves it for this project.
- Never modify base Conda environment unless Mario explicitly asks.
