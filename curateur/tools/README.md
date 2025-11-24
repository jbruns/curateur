# Development Tools

This directory contains development and CI/CD utility scripts for the curateur project.

## code_quality_check.py

A comprehensive code quality checker designed for both local development and CI/CD pipelines.

### Features

**Corruption Detection:**
- Syntax errors in Python files
- Escaped newlines (`\n`) that should be actual newlines
- Escaped quotes (`\"`) in corrupted strings
- Split string literals across lines

**CI Mode Quality Checks:**
- Trailing whitespace
- Mixed line endings (CRLF/LF/CR)
- Tab characters (PEP 8 compliance)
- Lines exceeding 120 characters
- Debug print statements (optional)
- TODO/FIXME comments tracking (optional)
- Potentially unused imports (optional)

### Usage

```bash
# Quick corruption scan (only fails on syntax errors)
python3 curateur/tools/code_quality_check.py curateur/

# Full CI quality checks
python3 curateur/tools/code_quality_check.py --ci curateur/

# Strict mode - fail on any quality issue
python3 curateur/tools/code_quality_check.py --strict --ci curateur/

# Using make targets
make check-corruption  # Quick scan
make check-quality     # Full scan (informational)
make lint             # Strict scan (fails on issues)
```

### CI Integration

See `.github/workflows/code-quality.yml.example` for GitHub Actions integration.

The tool returns appropriate exit codes:
- **Exit 0**: No critical issues (or no issues in strict mode)
- **Exit 1**: Critical issues found (syntax errors) or any issues in strict mode

### Pre-commit Hook

Install the pre-commit hook to run checks before each commit:

```bash
cp .git-hooks/pre-commit.example .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Other Tools

### generate_system_map.py

Generates the ScreenScraper platform ID mapping from `es_systems.xml`.

### setup_dev_credentials.py

Interactive setup tool for configuring ScreenScraper API credentials during development.
