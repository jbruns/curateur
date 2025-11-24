# Makefile for curateur development tasks

.PHONY: help check-quality check-corruption lint test

help:
	@echo "Available targets:"
	@echo "  check-corruption  - Quick scan for file corruption (syntax errors, etc.)"
	@echo "  check-quality     - Full CI-style quality checks"
	@echo "  lint              - Run quality checks with strict mode (fails on any issue)"
	@echo "  test              - Run pytest test suite"

# Quick corruption check - only fails on syntax errors
check-corruption:
	@echo "Checking for file corruption..."
	@python3 curateur/tools/code_quality_check.py curateur/

# Full quality check - reports all issues but doesn't fail
check-quality:
	@echo "Running CI quality checks..."
	@python3 curateur/tools/code_quality_check.py --ci curateur/ || true

# Strict mode - fails on any quality issue
lint:
	@echo "Running strict quality checks..."
	@python3 curateur/tools/code_quality_check.py --strict --ci curateur/

# Run tests
test:
	@pytest tests/ -v
