# Repository Guidelines

## Project Structure & Module Organization

- `src/` holds the orchestration stack: `agents/` (lifecycle), `memory/` (Qdrant RAG), `mcp/` (FastAPI MCP server), `core/` (Supervision, Policy, Models), and `interfaces/` (LLM, Tools).
- `frontend/` is the Vite + React dashboard; run UI tooling from that directory.
- `tests/` contains integration suites and `run_all_tests.py`.
- `scripts/` provides setup and deployment helpers.

## Build, Test, and Development Commands

- **Setup**: Use `micromamba` to create the env, then `poetry` for deps: `micromamba create -n hephaestus-env python=3.12 -y && micromamba activate hephaestus-env && pip install poetry && poetry install`.
- **Services**: Start Qdrant with `docker run -p 6333:6333 qdrant/qdrant` or `docker-compose up -d`.
- `python scripts/init_db.py` and `python scripts/init_qdrant.py` initialize SQLite tables and vector collections.
- `python run_server.py` exposes the MCP API on port 8000.
- `python run_supervisor.py` starts the Work-Centric Supervision service.
- `cd frontend && npm install && npm run dev` serves the UI; `npm run build` produces production assets.

## Coding Style & Naming Conventions

- Format Python with Black (line length 88), lint via `flake8`, and type-check with `mypy`; use snake_case modules/functions, PascalCase classes, verb-first async names, and explicit type hints.
- Frontend code relies on functional components, camelCase hooks/utilities, Tailwind classes, and `npm run type-check` before review.

## Documentation-First Workflow

- Consult `README.md` for architecture overview.
- Update or add documentation when behavior changes, keeping `prompts/` and `templates/` aligned with code updates.

## Task Artifacts & History

- **Archival**: Upon completing a complex task, archive key artifacts (plans, walkthroughs, logs) to `docs/task_history/YYYY-MM-DD_task_name/`.
- **Workflow**: Use the `.agent/workflows/archive_task_artifacts.md` workflow to automate this process.
- **Cleanup**: Do not leave `task.md` or `implementation_plan.md` in the root or brain directory indefinitely; archive and clear them to maintain a clean context.

## Testing Guidelines

- Default to `python tests/run_all_tests.py`; use `--quick` for a smoke pass or run suites directly (e.g., `python tests/test_vector_store.py`). `pytest` and `pytest --cov=src` remain available for targeted coverage.
- Tests assume live Qdrant and valid API keys; note prerequisites in docstrings, guard optional integrations with `pytest.importorskip`, and clean up agent data deterministically.

## Commit & Pull Request Guidelines

- Match the repo history with `feat:`, `fix:`, `chore:` prefixes and <72 character subjects.
- PRs should state scope, configuration or credential assumptions, and linked issues/design docs; attach UI screenshots and paste key command outputs when relevant.
- Run backend suites plus `npm run type-check` before requesting review, calling out any skipped checks with rationale.

## Security & Configuration Tips

- Store secrets in `.env`; use `hephaestus_config.yaml` or `config/agent_config.yaml` for overrides and never commit credentials.
- **Automated Cleanup**: The system automatically cleans up `agent-*` branches and worktrees upon agent termination or server startup. This prevents "dangling branches" from cluttering the repo.
    - **Startup Sweeper**: `server.py` runs a cleanup routine on startup to remove any stale worktrees from previous crashed sessions.
    - **Termination Cleanup**: `AgentManager` ensures worktrees are removed when an agent finishes its task.
- **Manual Reset**: Reset SQLite/Qdrant state through `scripts/` helpers if deep cleaning is required.
