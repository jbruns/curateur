"""Parser for MAME XML files.

Extracts machine definitions including metadata, ROM requirements, CHD dependencies,
and clone/parent relationships from MAME's XML output.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from lxml import etree

logger = logging.getLogger(__name__)


@dataclass
class MAMEDisk:
    """Represents a CHD disk requirement."""
    name: str
    sha1: Optional[str] = None
    merge: Optional[str] = None
    region: Optional[str] = None


@dataclass
class MAMEROM:
    """Represents a ROM file requirement."""
    name: str
    size: Optional[int] = None
    crc: Optional[str] = None
    sha1: Optional[str] = None
    merge: Optional[str] = None


@dataclass
class MAMEMachine:
    """Represents a MAME machine definition."""
    name: str  # shortname
    description: str
    year: Optional[str] = None
    manufacturer: Optional[str] = None
    cloneof: Optional[str] = None
    romof: Optional[str] = None
    runnable: str = "yes"
    isbios: str = "no"
    isdevice: str = "no"
    ismechanical: str = "no"
    roms: List[MAMEROM] = field(default_factory=list)
    disks: List[MAMEDisk] = field(default_factory=list)

    def is_game(self) -> bool:
        """Check if this machine is a playable game."""
        return (
            self.isbios != "yes" and
            self.isdevice != "yes" and
            self.runnable == "yes"
        )

    def has_chd_requirement(self) -> bool:
        """Check if this machine requires CHD files."""
        return len(self.disks) > 0

    def get_required_chd_names(self) -> List[str]:
        """Get list of required CHD names."""
        return [disk.name for disk in self.disks]


class MAMEXMLParser:
    """Parser for MAME XML files."""

    def __init__(self, xml_path: Path):
        """Initialize parser with path to MAME XML file.
        
        Args:
            xml_path: Path to mame XML file (e.g., mame0283.xml)
        """
        self.xml_path = xml_path
        self.machines: Dict[str, MAMEMachine] = {}

    def parse(self) -> Dict[str, MAMEMachine]:
        """Parse MAME XML file and return machine definitions.
        
        Returns:
            Dictionary mapping machine shortname to MAMEMachine object
            
        Raises:
            FileNotFoundError: If XML file doesn't exist
            etree.XMLSyntaxError: If XML is malformed
        """
        if not self.xml_path.exists():
            raise FileNotFoundError(f"MAME XML file not found: {self.xml_path}")

        logger.info(f"Parsing MAME XML: {self.xml_path}")
        logger.info("This may take 30-60 seconds for large files (50MB+)...")
        
        file_size_mb = self.xml_path.stat().st_size / (1024 * 1024)
        logger.info(f"File size: {file_size_mb:.1f} MB")

        # Parse XML in-memory
        tree = etree.parse(str(self.xml_path))
        root = tree.getroot()

        # Iterate through machine elements
        for machine_elem in root.findall("machine"):
            machine = self._parse_machine(machine_elem)
            self.machines[machine.name] = machine

        logger.info(f"Parsed {len(self.machines)} machines from MAME XML")
        
        # Log statistics
        games = sum(1 for m in self.machines.values() if m.is_game())
        with_chds = sum(1 for m in self.machines.values() if m.has_chd_requirement())
        clones = sum(1 for m in self.machines.values() if m.cloneof)
        
        logger.info(f"  - {games} playable games (runnable, non-BIOS, non-device)")
        logger.info(f"  - {with_chds} machines require CHDs")
        logger.info(f"  - {clones} clones (have parent machines)")

        return self.machines

    def _parse_machine(self, machine_elem) -> MAMEMachine:
        """Parse a single machine element.
        
        Args:
            machine_elem: XML element for machine
            
        Returns:
            MAMEMachine object
        """
        name = machine_elem.get("name")
        
        # Get description
        desc_elem = machine_elem.find("description")
        description = desc_elem.text if desc_elem is not None else name
        
        # Get year
        year_elem = machine_elem.find("year")
        year = year_elem.text if year_elem is not None else None
        
        # Get manufacturer
        mfr_elem = machine_elem.find("manufacturer")
        manufacturer = mfr_elem.text if mfr_elem is not None else None
        
        # Get attributes
        cloneof = machine_elem.get("cloneof")
        romof = machine_elem.get("romof")
        runnable = machine_elem.get("runnable", "yes")
        isbios = machine_elem.get("isbios", "no")
        isdevice = machine_elem.get("isdevice", "no")
        ismechanical = machine_elem.get("ismechanical", "no")
        
        # Parse ROMs
        roms = []
        for rom_elem in machine_elem.findall("rom"):
            rom = MAMEROM(
                name=rom_elem.get("name"),
                size=int(rom_elem.get("size")) if rom_elem.get("size") else None,
                crc=rom_elem.get("crc"),
                sha1=rom_elem.get("sha1"),
                merge=rom_elem.get("merge")
            )
            roms.append(rom)
        
        # Parse disks (CHDs)
        disks = []
        for disk_elem in machine_elem.findall("disk"):
            disk = MAMEDisk(
                name=disk_elem.get("name"),
                sha1=disk_elem.get("sha1"),
                merge=disk_elem.get("merge"),
                region=disk_elem.get("region")
            )
            disks.append(disk)
        
        return MAMEMachine(
            name=name,
            description=description,
            year=year,
            manufacturer=manufacturer,
            cloneof=cloneof,
            romof=romof,
            runnable=runnable,
            isbios=isbios,
            isdevice=isdevice,
            ismechanical=ismechanical,
            roms=roms,
            disks=disks
        )

    def get_machine(self, shortname: str) -> Optional[MAMEMachine]:
        """Get machine definition by shortname.
        
        Args:
            shortname: MAME machine shortname
            
        Returns:
            MAMEMachine object or None if not found
        """
        return self.machines.get(shortname.lower())

    def get_parent_machine(self, machine: MAMEMachine) -> Optional[MAMEMachine]:
        """Get parent machine for a clone.
        
        Args:
            machine: Clone machine
            
        Returns:
            Parent MAMEMachine or None if not a clone or parent not found
        """
        if not machine.cloneof:
            return None
        return self.machines.get(machine.cloneof)
