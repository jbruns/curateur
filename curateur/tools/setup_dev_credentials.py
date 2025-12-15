#!/usr/bin/env python3
"""
Developer Credential Setup Utility

This tool is used by the project maintainer to generate obfuscated
credential constants for inclusion in releases.

Usage:
    # Generate obfuscated constants
    python -m curateur.tools.setup_dev_credentials

    # Verify existing constants
    python -m curateur.tools.setup_dev_credentials --verify

SECURITY NOTE: This tool should only be run by the project maintainer
with access to the developer credentials. The output constants are
obfuscated but NOT cryptographically secure.
"""

import sys
from pathlib import Path
from getpass import getpass

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from curateur.api.obfuscator import obfuscate, deobfuscate


def format_bytearray(data: bytearray, indent: int = 4) -> str:
    """Format bytearray as Python code with proper line wrapping."""
    bytes_per_line = 12
    lines = []

    for i in range(0, len(data), bytes_per_line):
        chunk = data[i : i + bytes_per_line]
        byte_str = ", ".join(f"{b}" for b in chunk)
        lines.append(" " * indent + byte_str + ",")

    return "\n".join(lines)


def generate_constants():
    """Interactive credential input and constant generation."""
    print("Developer Credential Setup")
    print("=" * 50)
    print()
    print("This will generate obfuscated constants for curateur/api/credentials.py")
    print("The credentials will be XOR obfuscated (not cryptographically secure).")
    print()

    # Get credentials
    devid = input("Enter Developer ID: ").strip()
    devpassword = getpass("Enter Developer Password: ").strip()

    if not devid or not devpassword:
        print("\nError: Both devid and devpassword are required.")
        sys.exit(1)

    # Obfuscate
    devid_obf = obfuscate(devid)
    devpass_obf = obfuscate(devpassword)

    # Generate Python code
    print("\n" + "=" * 50)
    print("Generated Constants (copy to curateur/api/credentials.py):")
    print("=" * 50)
    print()
    print("_DEV_ID_OBFUSCATED = bytearray([")
    print(format_bytearray(devid_obf))
    print("])")
    print()
    print("_DEV_PASSWORD_OBFUSCATED = bytearray([")
    print(format_bytearray(devpass_obf))
    print("])")
    print()
    print("=" * 50)

    # Verify
    print("\nVerification:")
    print(f"  devid: {deobfuscate(devid_obf)}")
    print(f"  devpassword: {'*' * len(devpassword)}")
    print()


def verify_existing():
    """Verify existing credentials can be deobfuscated."""
    try:
        from curateur.api.credentials import get_dev_credentials

        print("Verifying existing credentials...")
        creds = get_dev_credentials()

        print("✓ Credentials successfully deobfuscated:")
        print(f"  devid: {creds['devid']}")
        print(f"  devpassword: {'*' * len(creds['devpassword'])}")
        print(f"  softname: {creds['softname']}")

    except ValueError as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Setup or verify developer credentials"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify existing credentials instead of generating new ones",
    )

    args = parser.parse_args()

    if args.verify:
        verify_existing()
    else:
        generate_constants()
