"""ES-DE system configuration parsing."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from lxml import etree


@dataclass
class SystemDefinition:
    """Represents a system defined in es_systems.xml."""
    name: str
    fullname: str
    path: str
    extensions: List[str]
    platform: str
    
    def supports_m3u(self) -> bool:
        """Check if system supports M3U playlists."""
        return '.m3u' in self.extensions
    
    def resolve_rom_path(self, rom_root: Path) -> Path:
        """
        Resolve ROM path by replacing %ROMPATH% placeholder.
        
        Args:
            rom_root: Root ROM directory from config
            
        Returns:
            Resolved path
            
        Examples:
            - "%ROMPATH%/nes" with rom_root="/roms" -> "/roms/nes"
            - "/absolute/path" -> "/absolute/path" (unchanged)
            - "~/my/roms/nes" -> "/Users/user/my/roms/nes" (expanded)
        """
        path_str = self.path
        
        # Replace %ROMPATH% placeholder (case-insensitive, handle both / and \)
        if '%ROMPATH%' in path_str.upper():
            # Find the actual case-sensitive match
            import re
            path_str = re.sub(
                r'%ROMPATH%[/\\]?',
                str(rom_root) + '/',
                path_str,
                flags=re.IGNORECASE
            )
        
        # Expand user home directory and resolve
        return Path(path_str).expanduser().resolve()


class ESSystemsError(Exception):
    """ES systems parsing errors."""
    pass


def parse_es_systems(xml_path: Path) -> List[SystemDefinition]:
    """
    Parse ES-DE es_systems.xml file.
    
    Args:
        xml_path: Path to es_systems.xml file
        
    Returns:
        List of SystemDefinition objects
        
    Raises:
        ESSystemsError: If XML cannot be parsed or is invalid
    """
    try:
        tree = etree.parse(str(xml_path))
        root = tree.getroot()
    except etree.XMLSyntaxError as e:
        raise ESSystemsError(f"Invalid XML in es_systems.xml: {e}")
    except Exception as e:
        raise ESSystemsError(f"Failed to read es_systems.xml: {e}")
    
    if root.tag != 'systemList':
        raise ESSystemsError(
            f"Invalid root element: expected 'systemList', got '{root.tag}'"
        )
    
    systems = []
    
    for system_elem in root.findall('system'):
        try:
            system = _parse_system_element(system_elem)
            systems.append(system)
        except ValueError as e:
            # Log warning but continue
            print(f"Warning: Skipping invalid system: {e}")
            continue
    
    if not systems:
        raise ESSystemsError("No valid systems found in es_systems.xml")
    
    return systems


def _parse_system_element(elem: etree.Element) -> SystemDefinition:
    """
    Parse a single <system> element.
    
    Args:
        elem: <system> XML element
        
    Returns:
        SystemDefinition object
        
    Raises:
        ValueError: If required fields are missing
    """
    # Extract required fields
    name = _get_element_text(elem, 'name')
    fullname = _get_element_text(elem, 'fullname')
    path = _get_element_text(elem, 'path')
    extension_str = _get_element_text(elem, 'extension')
    
    # Platform can be in <platformid> or <platform> (handle both)
    platform = _get_platform_id(elem)
    
    if not all([name, fullname, path, extension_str, platform]):
        raise ValueError(
            f"System missing required fields (name: {name}, platform: {platform})"
        )
    
    # Parse extensions (space-separated, can contain ".zip .7z" format)
    extensions = [
        ext.strip().lower() 
        for ext in extension_str.split() 
        if ext.strip()
    ]
    
    return SystemDefinition(
        name=name,
        fullname=fullname,
        path=path,
        extensions=extensions,
        platform=platform
    )


def _get_element_text(parent: etree.Element, tag: str) -> Optional[str]:
    """Get text content of child element."""
    elem = parent.find(tag)
    if elem is not None and elem.text:
        return elem.text.strip()
    return None


def _get_platform_id(system_elem: etree.Element) -> Optional[str]:
    """
    Extract platform ID from <platform> element.
    
    Args:
        system_elem: <system> element
        
    Returns:
        Platform ID string or None
    """
    # Get <platform> element (ES-DE standard)
    platform_elem = system_elem.find('platform')
    
    if platform_elem is not None and platform_elem.text:
        text = platform_elem.text.strip()
        # Return text only if not empty after stripping
        if text:
            return text
    
    return None


def get_systems_by_name(
    systems: List[SystemDefinition], 
    names: Optional[List[str]] = None
) -> List[SystemDefinition]:
    """
    Filter systems by name.
    
    Args:
        systems: List of all system definitions
        names: List of system names to include, or None for all
        
    Returns:
        Filtered list of systems
        
    Raises:
        ValueError: If requested system name not found
    """
    if not names:
        return systems
    
    filtered = []
    name_set = set(n.lower() for n in names)
    found_names = set()
    
    for system in systems:
        if system.name.lower() in name_set:
            filtered.append(system)
            found_names.add(system.name.lower())
    
    # Check for missing systems
    missing = name_set - found_names
    if missing:
        raise ValueError(
            f"Systems not found in es_systems.xml: {', '.join(sorted(missing))}"
        )
    
    return filtered
