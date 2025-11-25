# Contributing to Hephaestus

Thank you for your interest in contributing to Hephaestus! We welcome contributions from the community.

## 🚀 Getting Started

### Prerequisites

- Python 3.12 (Required for SQLAlchemy compatibility)
- Node.js 20+ and npm
- Docker (for Qdrant)
- tmux
- Git
- Claude Code (for testing agent functionality)

### Development Setup

1. **Clone and setup the repository**
   ```bash
   git clone https://github.com/Ido-Levi/Hephaestus.git
   cd Hephaestus
   ```

2. **Set up Python environment**
   We recommend a **Hybrid Approach**: use `micromamba` to manage the Python environment (ensuring a clean Python 3.12) and `poetry` to manage project dependencies.

   > **Note:** The instructions below are provided as a convenience. For up-to-date instructions, refer to the [Micromamba docs](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html) and [Poetry docs](https://python-poetry.org/docs/).

   **macOS / Linux:**
   ```bash
   # 1. Install micromamba (if not already installed)
   "${SHELL}" <(curl -L micro.mamba.pm/install.sh)

   # 2. Create and activate environment
   micromamba create -n hephaestus-env python=3.12 -y
   micromamba activate hephaestus-env

   # 3. Install Poetry and Dependencies
   pip install poetry
   poetry install
   ```

   **Windows (PowerShell):**
   ```powershell
   # 1. Install micromamba
   Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://micro.mamba.pm/install.ps1'))

   # 2. Create and activate environment
   micromamba create -n hephaestus-env python=3.12 -y
   micromamba activate hephaestus-env

   # 3. Install Poetry and Dependencies
   pip install poetry
   poetry install
   ```

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

4. **Start required services**
   ```bash
   # Terminal 1: Qdrant
   docker run -d -p 6333:6333 qdrant/qdrant

   # Terminal 2: Frontend
   cd frontend
   npm install
   npm run dev
   ```

5. **Initialize databases**
   ```bash
   python scripts/init_db.py
   python scripts/init_qdrant.py
   ```

6. **Run the server**
   ```bash
   python run_server.py
   ```

## 📋 How to Contribute

### Reporting Bugs

Found a bug? Please open an issue using the **Bug Report** template. Include:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, etc.)
- Relevant logs or error messages

### Suggesting Features

Have an idea? Open a **Feature Request** issue with:
- Clear use case description
- Why this feature would be valuable
- Proposed implementation approach (if you have one)

### Submitting Code

1. **Fork the repository**

2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```

3. **Make your changes**
   - Write clear, documented code
   - Follow existing code style
   - Add tests for new functionality
   - Update documentation as needed

4. **Test your changes**
   ```bash
   # Run the full integration test suite (Recommended)
   python tests/run_all_tests.py

   # Run specific tests with pytest
   pytest tests/unit
   pytest tests/integration
   ```

5. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: Add clear description of your changes"
   ```

   Follow conventional commit format:
   - `feat:` New features
   - `fix:` Bug fixes
   - `docs:` Documentation changes
   - `test:` Test additions/changes
   - `refactor:` Code refactoring
   - `chore:` Maintenance tasks

6. **Push and create a Pull Request**
   ```bash
   git push origin feature/your-feature-name
   ```

   Then create a PR on GitHub with:
   - Clear title and description
   - Link to related issues
   - Screenshots/videos if UI changes
   - Test results

## 🎨 Code Style Guidelines

### Python

- Follow PEP 8
- Use type hints for function parameters and returns
- Write docstrings for classes and functions
- Maximum line length: 100 characters
- Use `black` for formatting

**Example:**
```python
def create_task(
    description: str,
    phase_id: int,
    agent_id: str,
    priority: str = "medium"
) -> str:
    """
    Create a new task for an agent.

    Args:
        description: Task description
        phase_id: Phase ID (1, 2, 3, etc.)
        agent_id: ID of the agent to assign
        priority: Task priority (low, medium, high, critical)

    Returns:
        Task ID string
    """
    # Implementation
    pass
```

### TypeScript/React

- Use TypeScript for all frontend code
- Functional components with hooks
- Use TanStack Query for API calls
- Follow existing component structure

### Documentation

- Update README.md for user-facing changes
- Update relevant docs in `website/docs/` for new features
- Add JSDoc/docstrings for new functions
- Include examples in documentation

### Frontend Development

The frontend codebase enforces strict TypeScript checks to prevent runtime errors.

- **Strict Mode**: `strict: true` is enabled in `tsconfig.json`.
- **Build Checks**: `npm run build` includes a `tsc` check. Ensure no type errors exist before committing.
- **Unused Code**: `noUnusedLocals` and `noUnusedParameters` are enabled. Remove any unused imports or variables.

To verify your changes:
```bash
cd frontend
npm run type-check
npm run build
```

## 🧪 Testing Guidelines

### Writing Tests

- Write tests for new features
- Maintain or improve code coverage
- Use pytest fixtures for common setup
- Mock external services (LLM APIs, Qdrant)

**Example:**
```python
def test_create_task(mock_db, mock_llm):
    """Test task creation with mocked dependencies."""
    result = create_task(
        description="Test task",
        phase_id=1,
        agent_id="test-agent"
    )
    assert result.startswith("task-")
```

### Running Tests

The primary way to run tests is via the test runner script, which handles environment checks and service dependencies:

```bash
# Run all tests
python tests/run_all_tests.py

# Run quick smoke tests
python tests/run_all_tests.py --quick

# Run specific test module
python tests/run_all_tests.py --module tests/test_mcp_server.py
```

You can also run pytest directly if you prefer:

```bash
# Unit tests
pytest tests/unit

# Integration tests (requires services running)
pytest tests/integration

# End-to-End tests (requires Docker & Stub LLM)
# This runs the full ticket lifecycle using a stubbed LLM provider
python tests/run_all_tests.py --e2e
```

## 📚 Documentation

### Adding Documentation

New features should include:
1. Code documentation (docstrings/comments)
2. User-facing documentation in `website/docs/`
3. Update to README.md if applicable
4. Example usage in appropriate guide

### Building Documentation Locally

```bash
cd website
npm install
npm start
```

Documentation will be available at `http://localhost:3000/Hephaestus/`

## 🤝 Community Guidelines

- Be respectful and inclusive
- Help others learn and grow
- Provide constructive feedback
- Follow the Code of Conduct (when added)

## 🐛 Common Issues

### Tests Failing

- Ensure Qdrant is running: `docker ps`
- Check database is initialized: `ls hephaestus.db`
- Verify API keys in `.env` for integration tests

### Import Errors

- Activate virtual environment: `source venv/bin/activate`
- Reinstall dependencies: `pip install -r requirements.txt`

### Frontend Issues

- Clear node_modules: `rm -rf node_modules && npm install`
- Check ports: Make sure 3000 and 8000 are available

## 💡 Areas We Need Help

- **Documentation**: Improving guides and examples
- **Testing**: Increasing test coverage
- **Bug Fixes**: Check open issues labeled `good first issue`
- **Performance**: Optimizing agent coordination
- **Features**: See issues labeled `enhancement`

## 📞 Questions?

- Open a **Question** issue
- Check existing [GitHub Discussions](https://github.com/Ido-Levi/Hephaestus/discussions)
- Review the [documentation](https://ido-levi.github.io/Hephaestus/)

## 🎉 Thank You!

Every contribution helps make Hephaestus better. We appreciate your time and effort!
