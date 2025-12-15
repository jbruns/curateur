"""Parser for MAME history.xml file.

Extracts game descriptions and historical information.
"""

import logging
from pathlib import Path
from typing import Dict, Optional
from lxml import etree

logger = logging.getLogger(__name__)


class HistoryParser:
    """Parser for history.xml file."""

    def __init__(self, history_path: Path):
        """Initialize parser with path to history.xml file.

        Args:
            history_path: Path to history.xml file
        """
        self.history_path = history_path
        self.descriptions: Dict[str, str] = {}

    def parse(self) -> Dict[str, str]:
        """Parse history.xml and return descriptions keyed by shortname.

        Returns:
            Dictionary mapping shortname to description text

        Raises:
            FileNotFoundError: If history.xml doesn't exist
            etree.XMLSyntaxError: If XML is malformed
        """
        if not self.history_path.exists():
            raise FileNotFoundError(f"History XML file not found: {self.history_path}")

        logger.info(f"Parsing history XML: {self.history_path}")
        logger.info("This may take 30-60 seconds for large files (50MB+)...")

        file_size_mb = self.history_path.stat().st_size / (1024 * 1024)
        logger.info(f"File size: {file_size_mb:.1f} MB")

        # Parse XML in-memory
        tree = etree.parse(str(self.history_path))
        root = tree.getroot()

        # Find all entry elements
        entry_elements = root.findall(".//entry")

        if not entry_elements:
            # Maybe entries are direct children
            entry_elements = list(root)

        logger.debug(f"Found {len(entry_elements)} entry elements to process")

        parsed_count = 0
        for entry_elem in entry_elements:
            # Look for <text> child for description
            text_elem = entry_elem.find("text")
            if text_elem is None:
                continue

            text = self._get_element_text(text_elem)
            if not text:
                continue

            # Look for <systems> child element containing <system> elements
            systems_elem = entry_elem.find("systems")
            if systems_elem is not None:
                # Find all <system> child elements with name attribute
                for system_elem in systems_elem.findall("system"):
                    shortname = system_elem.get("name")
                    if shortname:
                        # Store description for this ROM name (normalized to lowercase)
                        self.descriptions[shortname.lower()] = text.strip()
                        parsed_count += 1

        logger.info(f"Parsed {len(self.descriptions)} history entries")

        return self.descriptions

    def _get_element_text(self, element) -> str:
        """Extract all text content from an element and its children.

        Args:
            element: XML element

        Returns:
            Concatenated text content
        """
        # Get direct text
        text_parts = []

        if element.text:
            text_parts.append(element.text)

        # Get text from child elements
        for child in element:
            child_text = self._get_element_text(child)
            if child_text:
                text_parts.append(child_text)

            # Include tail text after child element
            if child.tail:
                text_parts.append(child.tail)

        return "".join(text_parts)

    def get_description(self, shortname: str) -> Optional[str]:
        """Get history description for a game.

        Args:
            shortname: Game shortname

        Returns:
            Description text or None if not found
        """
        return self.descriptions.get(shortname.lower())

    def has_description(self, shortname: str) -> bool:
        """Check if a description exists for a game.

        Args:
            shortname: Game shortname

        Returns:
            True if description exists, False otherwise
        """
        return shortname.lower() in self.descriptions
