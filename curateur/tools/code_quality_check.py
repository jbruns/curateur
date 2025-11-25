#!/usr/bin/env python3
"""
Code quality and corruption checker for CI/CD pipelines.

This script identifies potential code issues suitable for CI validation:
- File corruption (escaped newlines, quotes)
- Syntax errors
- Code quality issues (trailing whitespace, mixed line endings, etc.)
- Import organization problems
- Common anti-patterns

Designed to run in CI to catch issues before they reach production.
"""

import ast
import re
from pathlib import Path
from typing import List, Tuple, Dict, Set
import sys


def check_syntax_errors(file_path: Path) -> List[str]:
    """Check if file has Python syntax errors."""
    errors = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        ast.parse(content, filename=str(file_path))
    except SyntaxError as e:
        errors.append(f"Syntax error at line {e.lineno}: {e.msg}")
    except Exception as e:
        errors.append(f"Parse error: {str(e)}")
    return errors


def check_escaped_newlines(file_path: Path) -> List[Tuple[int, str]]:
    """Find lines with literal \\n that might be corrupted newlines."""
    issues = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.splitlines()

        for line_num, line in enumerate(lines, 1):
            # Look for patterns that indicate corruption, not intentional escapes:
            # 1. String ending with literal \n followed by actual newline
            # 2. Code statement ending with \n (not in a string)
            # 3. Multiple \n with whitespace between them

            # Skip if it's in a comment
            if '#' in line:
                code_part = line.split('#')[0]
            else:
                code_part = line

            # Pattern 1: Ends with \n and next line continues the statement
                if code_part.rstrip().endswith('\\n') and not code_part.strip().startswith(('r"', "r'")):
                    # Check if this looks like a corrupted continuation
                    if line_num < len(lines):
                        next_line = lines[line_num] if line_num < len(lines) else ""
                        # If next line is indented at same level and doesn't start a new statement
                        if next_line and not next_line.lstrip().startswith(
                            ('def ', 'class ', 'if ', 'for ', 'while ', '@')
                        ):
                            issues.append((line_num, line.rstrip()))

            # Pattern 2: \n followed by whitespace and more code on same line
            if re.search(r'\\n\s+\w', code_part):
                issues.append((line_num, line.rstrip()))

    except Exception as e:
        issues.append((0, f"Error reading file: {str(e)}"))
    return issues


def check_escaped_quotes(file_path: Path) -> List[Tuple[int, str]]:
    """Find lines with literal \\" that might be corrupted quotes."""
    issues = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # Look for \\" that's NOT in a raw string or intentional escape
                if '\\"' in line:
                    # Skip if it's in a comment
                    code_part = line.split('#')[0]
                    if '\\"' in code_part:
                        # Check for corruption patterns:
                        # 1. f\\" instead of f"
                        # 2. Line starting with \\" (corrupted string start)
                        # 3. Multiple \\" in sequence
                        if (re.search(r'f\\"', code_part) or
                            re.search(r'^\s+\\"', code_part) or
                            re.search(r'\\".*\\".*\\"', code_part)):
                            issues.append((line_num, line.rstrip()))
    except Exception as e:
        issues.append((0, f"Error reading file: {str(e)}"))
    return issues


def check_string_literal_newlines(file_path: Path) -> List[Tuple[int, str]]:
    """Find string literals that contain actual newlines (often corruption)."""
    issues = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.splitlines()

        # Look for non-triple-quoted strings split across lines
        for line_num, line in enumerate(lines, 1):
            # Skip docstrings and intentional multi-line strings
            if '"""' in line or "'''" in line:
                continue

            # Skip comments
            if line.strip().startswith('#'):
                continue

            # Look for unclosed string at end of line (corruption indicator)
            # Pattern: string starts but doesn't end, and line doesn't end with \
            stripped = line.rstrip()

            # Count unescaped quotes
            single_quotes = 0
            double_quotes = 0
            i = 0
            while i < len(stripped):
                if i > 0 and stripped[i-1] == '\\':
                    i += 1
                    continue
                if stripped[i] == '"':
                    double_quotes += 1
                elif stripped[i] == "'":
                    single_quotes += 1
                i += 1

            # If odd number of quotes and doesn't end with continuation
            if ((single_quotes % 2 == 1 or double_quotes % 2 == 1) and
                not stripped.endswith('\\') and
                not stripped.endswith(',') and
                stripped):  # non-empty line
                # Check if next line continues (indication of corruption)
                if line_num < len(lines):
                    next_line = lines[line_num].strip()
                    # If next line exists and doesn't start new statement
                    if (next_line and
                        not next_line.startswith(('def ', 'class ', '@', '#')) and
                        not re.match(r'^\s*[)}\]]', next_line)):
                        issues.append((line_num, line.rstrip()[:100]))

    except Exception as e:
        issues.append((0, f"Error reading file: {str(e)}"))
    return issues


def check_trailing_whitespace(file_path: Path) -> List[Tuple[int, str]]:
    """Find lines with trailing whitespace (CI quality issue)."""
    issues = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # Check if line has trailing whitespace (spaces/tabs after last non-whitespace char)
                # line.rstrip() removes trailing whitespace, line.rstrip('\n') removes only newline
                stripped_no_newline = line.rstrip('\n\r')
                stripped_all = line.rstrip()

                # If they differ, there's trailing whitespace
                if stripped_no_newline != stripped_all and stripped_all:
                    # Show the issue
                    issues.append((line_num, f"Line ends with whitespace"))
    except Exception as e:
        issues.append((0, f"Error reading file: {str(e)}"))
    return issues


def check_mixed_line_endings(file_path: Path) -> List[str]:
    """Detect mixed line endings (CR, LF, CRLF)."""
    issues = []
    try:
        with open(file_path, 'rb') as f:
            content = f.read()

        has_crlf = b'\r\n' in content
        has_lf = b'\n' in content.replace(b'\r\n', b'')
        has_cr = b'\r' in content.replace(b'\r\n', b'')

        endings = []
        if has_crlf:
            endings.append('CRLF')
        if has_lf:
            endings.append('LF')
        if has_cr:
            endings.append('CR')

        if len(endings) > 1:
            issues.append(f"Mixed line endings detected: {', '.join(endings)}")

    except Exception as e:
        issues.append(f"Error reading file: {str(e)}")
    return issues


def check_tab_indentation(file_path: Path) -> List[Tuple[int, str]]:
    """Find lines using tabs instead of spaces (Python PEP 8 violation)."""
    issues = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if '\t' in line and not line.strip().startswith('#'):
                    issues.append((line_num, "Tab character found (use 4 spaces)"))
    except Exception as e:
        issues.append((0, f"Error reading file: {str(e)}"))
    return issues


def check_print_statements(file_path: Path) -> List[Tuple[int, str]]:
    """Find print() statements that might be debug leftovers."""
    issues = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # Skip comments and intentional prints (cli.py, etc.)
                if line.strip().startswith('#'):
                    continue

                # Look for print() not in test files or CLI
                if 'print(' in line and 'file=' not in line:
                    # Allow prints in specific contexts
                    if not any(x in str(file_path) for x in ['cli.py', 'test_', 'conftest.py']):
                        issues.append((line_num, line.strip()[:80]))
    except Exception as e:
        issues.append((0, f"Error reading file: {str(e)}"))
    return issues


def check_todo_comments(file_path: Path) -> List[Tuple[int, str]]:
    """Find TODO/FIXME comments for tracking."""
    issues = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if re.search(r'#\s*(TODO|FIXME|XXX|HACK)', line, re.IGNORECASE):
                    issues.append((line_num, line.strip()[:100]))
    except Exception as e:
        issues.append((0, f"Error reading file: {str(e)}"))
    return issues


def check_long_lines(file_path: Path, max_length: int = 120) -> List[Tuple[int, int]]:
    """Find lines exceeding maximum length (PEP 8 recommends 79, we allow 120)."""
    issues = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # Don't count the newline
                line_len = len(line.rstrip())
                if line_len > max_length:
                    issues.append((line_num, line_len))
    except Exception as e:
        issues.append((0, f"Error reading file: {str(e)}"))
    return issues


def check_unused_imports(file_path: Path) -> List[str]:
    """Detect potentially unused imports (basic heuristic)."""
    issues = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse to find imports
        try:
            tree = ast.parse(content, filename=str(file_path))
            imports = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        imports.add(name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name != '*':
                            name = alias.asname if alias.asname else alias.name
                            imports.add(name)

            # Simple check: see if imported name appears in code
            for imp in imports:
                # Skip common false positives
                if imp in ['logging', 'typing', 'dataclass', 'field', 'Optional', 'List', 'Dict', 'Any']:
                    continue
                # Check if import name appears outside import statements
                pattern = rf'\b{re.escape(imp)}\b'
                matches = list(re.finditer(pattern, content))
                # If only appears in import line, might be unused
                if len(matches) <= 1:
                    issues.append(f"Potentially unused import: {imp}")

        except SyntaxError:
            pass  # Already caught by syntax check

    except Exception as e:
        issues.append(f"Error reading file: {str(e)}")
    return issues


def scan_directory(root_path: Path, pattern: str = "**/*.py", ci_mode: bool = False) -> Dict[str, Dict[str, List]]:
    """Scan directory for Python files with corruption issues."""
    results = {}

    for file_path in root_path.glob(pattern):
        # Skip __pycache__ and hidden files
        if '__pycache__' in str(file_path) or file_path.name.startswith('.'):
            continue

        file_results = {
            'syntax_errors': check_syntax_errors(file_path),
            # Only report other issues if there are syntax errors
            # (reduces false positives from intentional escape sequences)
        }

        # If there are syntax errors, also check for likely causes
        if file_results['syntax_errors']:
            file_results['escaped_newlines'] = check_escaped_newlines(file_path)
            file_results['escaped_quotes'] = check_escaped_quotes(file_path)
            file_results['split_strings'] = check_string_literal_newlines(file_path)

        # CI mode: run additional quality checks
        if ci_mode:
            file_results['trailing_whitespace'] = check_trailing_whitespace(file_path)
            file_results['mixed_line_endings'] = check_mixed_line_endings(file_path)
            file_results['tab_indentation'] = check_tab_indentation(file_path)
            file_results['long_lines'] = check_long_lines(file_path)
            # Optional: less critical checks
            # file_results['print_statements'] = check_print_statements(file_path)
            # file_results['todo_comments'] = check_todo_comments(file_path)
            # file_results['unused_imports'] = check_unused_imports(file_path)

        # Only include files with issues
        if any(file_results.values()):
            results[str(file_path)] = file_results

    return results


def print_results(results: Dict[str, Dict[str, List]], ci_mode: bool = False) -> int:
    """Print scan results and return count of files with issues."""
    if not results:
        print("✅ No corruption issues found!")
        return 0

    print(f"⚠️  Found potential issues in {len(results)} file(s):\n")

    for file_path, issues in results.items():
        print(f"{'=' * 80}")
        print(f"📁 {file_path}")
        print(f"{'=' * 80}\n")

        if issues.get('syntax_errors'):
            print("🔴 SYNTAX ERRORS:")
            for error in issues['syntax_errors']:
                print(f"   {error}")
            print()

        if issues.get('escaped_newlines'):
            print("⚠️  ESCAPED NEWLINES (\\n):")
            for line_num, line in issues['escaped_newlines']:
                print(f"   Line {line_num}: {line[:100]}")
            print()

        if issues.get('escaped_quotes'):
            print("⚠️  ESCAPED QUOTES (\\):")
            for line_num, line in issues['escaped_quotes']:
                print(f"   Line {line_num}: {line[:100]}")
            print()

        if issues.get('split_strings'):
            print("⚠️  SPLIT STRING LITERALS:")
            for line_num, line in issues['split_strings']:
                print(f"   Line {line_num}: {line[:100]}")
            print()

        # CI mode checks
        if ci_mode:
            if issues.get('trailing_whitespace'):
                print("🔧 TRAILING WHITESPACE:")
                for line_num, msg in issues['trailing_whitespace']:
                    print(f"   Line {line_num}: {msg}")
                print()

            if issues.get('mixed_line_endings'):
                print("🔧 MIXED LINE ENDINGS:")
                for msg in issues['mixed_line_endings']:
                    print(f"   {msg}")
                print()

            if issues.get('tab_indentation'):
                print("🔧 TAB CHARACTERS:")
                for line_num, msg in issues['tab_indentation']:
                    print(f"   Line {line_num}: {msg}")
                print()

            if issues.get('long_lines'):
                print("📏 LONG LINES (>120 chars):")
                for line_num, length in issues['long_lines'][:10]:  # Show first 10
                    print(f"   Line {line_num}: {length} characters")
                if len(issues['long_lines']) > 10:
                    print(f"   ... and {len(issues['long_lines']) - 10} more")
                print()

            if issues.get('print_statements'):
                print("🐛 DEBUG PRINT STATEMENTS:")
                for line_num, line in issues['print_statements'][:5]:
                    print(f"   Line {line_num}: {line}")
                if len(issues['print_statements']) > 5:
                    print(f"   ... and {len(issues['print_statements']) - 5} more")
                print()

            if issues.get('todo_comments'):
                print("📝 TODO/FIXME COMMENTS:")
                for line_num, line in issues['todo_comments'][:5]:
                    print(f"   Line {line_num}: {line}")
                if len(issues['todo_comments']) > 5:
                    print(f"   ... and {len(issues['todo_comments']) - 5} more")
                print()

            if issues.get('unused_imports'):
                print("🗑️  POTENTIALLY UNUSED IMPORTS:")
                for msg in issues['unused_imports'][:10]:
                    print(f"   {msg}")
                if len(issues['unused_imports']) > 10:
                    print(f"   ... and {len(issues['unused_imports']) - 10} more")
                print()

    return len(results)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Code quality and corruption checker for Python files',
        epilog='Examples:\n'
               '  %(prog)s curateur/           # Quick corruption scan\n'
               '  %(prog)s --ci curateur/      # Full CI quality checks\n'
               '  %(prog)s --strict curateur/  # Fail on any issues',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'path',
        type=Path,
        nargs='?',
        default=Path.cwd(),
        help='Directory to scan (default: current directory)'
    )
    parser.add_argument(
        '--pattern',
        default='**/*.py',
        help='File pattern to match (default: **/*.py)'
    )
    parser.add_argument(
        '--ci',
        action='store_true',
        help='Enable CI mode with additional quality checks'
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Treat all issues as failures (exit code 1)'
    )
    parser.add_argument(
        '--exclude',
        action='append',
        default=[],
        help='Paths to exclude (can be specified multiple times)'
    )

    args = parser.parse_args()

    if not args.path.exists():
        print(f"❌ Error: Path does not exist: {args.path}")
        return 1

    mode_str = "CI quality checks" if args.ci else "corruption checks"
    print(f"🔍 Scanning {args.path} for {mode_str}...\n")

    results = scan_directory(args.path, args.pattern, ci_mode=args.ci)
    issue_count = print_results(results, ci_mode=args.ci)

    # In CI mode or strict mode, fail on any issues
    # Otherwise, only fail on syntax errors
    if args.strict or args.ci:
        return 1 if issue_count > 0 else 0
    else:
        # Only fail on critical issues (syntax errors)
        has_critical = any(
            bool(issues.get('syntax_errors'))
            for issues in results.values()
        )
        return 1 if has_critical else 0


if __name__ == '__main__':
    sys.exit(main())
