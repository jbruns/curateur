"""ROM organizer for ES-DE/curateur layouts."""

import argparse
import logging
import shutil
import tempfile
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from curateur.config.es_systems import SystemDefinition, parse_es_systems
from curateur.scanner.disc_handler import is_disc_subdirectory, validate_disc_subdirectory

logger = logging.getLogger(__name__)

# Disc formats that typically indicate optical media
DISC_FORMATS = {".cue", ".gdi", ".iso", ".cdi", ".chd", ".mds", ".ccd", ".toc", ".m3u"}
# Formats that rely on companion files and benefit from a disc subdirectory
MULTI_FILE_DISC_FORMATS = {".cue", ".gdi"}
# Primary disc descriptors used for grouping multi-disc sets (ignore track files)
PRIMARY_DISC_EXTS = {".cue", ".gdi", ".iso", ".chd", ".cdi", ".mds", ".ccd", ".toc"}
# Archives we will attempt to unpack
ARCHIVE_FORMATS = {".zip", ".tar", ".gz", ".bz2", ".xz"}


@dataclass
class RomCandidate:
    """Represents a ROM file discovered for organization."""

    source_path: Path
    extension: str
    stem: str
    base_name: str
    disc_number: Optional[int] = None


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Organize ROMs for ES-DE/curateur expectations (disc layouts, .m3u playlists).",
    )
    parser.add_argument("source", type=Path, help="Directory containing ROM files/archives to organize")
    parser.add_argument("system", help="ES-DE system short name (from es_systems.xml)")
    parser.add_argument(
        "rom_root",
        type=Path,
        help="Top-level ROMs directory (used for %%ROMPATH%% substitution from es_systems.xml)",
    )
    parser.add_argument(
        "--es-systems",
        type=Path,
        default=Path("es_systems.xml"),
        help="Path to es_systems.xml (default: ./es_systems.xml)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing files/directories in the target if present",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move files instead of copying (extracted archives are always copied)",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Also process hidden files (default skips names starting with '.')",
    )
    return parser.parse_args(argv)


def load_system(es_systems_path: Path, system_name: str) -> SystemDefinition:
    systems = parse_es_systems(es_systems_path)
    for system in systems:
        if system.name.lower() == system_name.lower():
            return system
    raise SystemExit(f"System '{system_name}' not found in {es_systems_path}")


def is_disc_based_system(system: SystemDefinition) -> bool:
    return any(ext in DISC_FORMATS for ext in system.extensions)


def should_use_disc_subdir(extension: str) -> bool:
    return extension in MULTI_FILE_DISC_FORMATS


def split_base_and_disc(stem: str) -> Tuple[str, Optional[int]]:
    """
    Attempt to strip disc numbers from a filename stem.

    Returns the base name and any detected disc number.
    """
    disc_patterns = [
        r"[ _\-.]*\(disc\s*(\d+)\)",
        r"[ _\-.]*\[disc\s*(\d+)\]",
        r"[ _\-.]*\(disk\s*(\d+)\)",
        r"[ _\-.]*\(cd\s*(\d+)\)",
        r"[ _\-.]*cd\s*(\d+)$",
        r"[ _\-.]*disc\s*(\d+)$",
        r"[ _\-.]*disk\s*(\d+)$",
    ]

    for pattern in disc_patterns:
        match = re.search(pattern, stem, flags=re.IGNORECASE)
        if match:
            disc_number = int(match.group(1))
            base = (stem[: match.start()] + stem[match.end() :]).strip(" -._()[]")
            return (base or stem, disc_number)

    return stem, None


def extract_archive(archive_path: Path, temp_root: Path) -> List[Path]:
    """Extract archive contents into a temp directory and return extracted files."""
    extracted_dir = temp_root / archive_path.stem
    extracted_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.unpack_archive(str(archive_path), str(extracted_dir))
    except shutil.ReadError:
        print(f"Warning: Unsupported or unreadable archive format: {archive_path}")
        return []
    except Exception as exc:
        print(f"Warning: Failed to extract {archive_path}: {exc}")
        return []

    return [p for p in extracted_dir.rglob("*") if p.is_file()]


def gather_candidates(
    source_dir: Path,
    system: SystemDefinition,
    include_hidden: bool,
    temp_root: Path,
) -> List[RomCandidate]:
    candidates: List[RomCandidate] = []
    system_exts = set(system.extensions)

    def should_skip(path: Path) -> bool:
        return not include_hidden and path.name.startswith(".")

    for path in source_dir.rglob("*"):
        if should_skip(path):
            continue

        if path.is_dir() and _is_disc_subdir_path(path, system_exts):
            candidates.extend(_make_candidates_from_path(path, system_exts))
            continue

        if not path.is_file():
            continue

        ext = path.suffix.lower()
        if ext in ARCHIVE_FORMATS:
            extracted_files = extract_archive(path, temp_root)
            for extracted in extracted_files:
                if should_skip(extracted):
                    continue
                candidates.extend(_make_candidates_from_path(extracted, system_exts))
            continue

        candidates.extend(_make_candidates_from_path(path, system_exts))

    return candidates


def _make_candidates_from_path(path: Path, allowed_exts: set) -> List[RomCandidate]:
    ext = path.suffix.lower()
    if ext not in allowed_exts and not _is_disc_subdir_path(path, allowed_exts):
        return []

    if path.is_dir():
        # Already in disc-subdir layout; use contained cue/gdi as the candidate path
        contained = validate_disc_subdirectory(path, list(allowed_exts))
        target_path = contained
    else:
        target_path = path

    stem = target_path.stem
    base, disc_no = split_base_and_disc(stem)

    return [
        RomCandidate(
            source_path=target_path,
            extension=target_path.suffix.lower(),
            stem=stem,
            base_name=base,
            disc_number=disc_no,
        )
    ]


def _is_disc_subdir_path(path: Path, system_exts: set) -> bool:
    try:
        return is_disc_subdirectory(path, list(system_exts))
    except Exception:
        return False


def group_multi_disc(candidates: List[RomCandidate]) -> Dict[str, List[RomCandidate]]:
    groups: Dict[str, List[RomCandidate]] = {}
    for cand in candidates:
        if cand.disc_number is None:
            continue
        if cand.extension not in PRIMARY_DISC_EXTS:
            continue
        groups.setdefault(cand.base_name.lower(), []).append(cand)

    return {base: sorted(cands, key=lambda c: c.disc_number or 0) for base, cands in groups.items() if len(cands) > 1}


def cue_dependencies(cue_file: Path) -> List[Path]:
    deps: List[Path] = []
    try:
        for line in cue_file.read_text(errors="ignore").splitlines():
            line_strip = line.strip()
            if not line_strip.upper().startswith("FILE"):
                continue
            match = re.search(r'FILE\s+"([^"]+)"', line_strip, flags=re.IGNORECASE)
            if match:
                deps.append(Path(match.group(1)))
                continue
            parts = line_strip.split()
            if len(parts) >= 2:
                deps.append(Path(parts[1].strip('"')))
    except Exception as exc:
        print(f"Warning: Could not parse cue file {cue_file}: {exc}")
    return deps


def gdi_dependencies(gdi_file: Path) -> List[Path]:
    deps: List[Path] = []
    try:
        for line in gdi_file.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line or line.isdigit():
                continue
            parts = line.split()
            if parts:
                deps.append(Path(parts[-1]))
    except Exception as exc:
        print(f"Warning: Could not parse gdi file {gdi_file}: {exc}")
    return deps


def copy_with_companions(
    candidate: RomCandidate,
    destination_dir: Path,
    overwrite: bool,
    move: bool,
) -> Tuple[List[Path], List[Path]]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    dest_main = destination_dir / candidate.source_path.name

    written: List[Path] = []
    copied_sources: List[Path] = []
    if dest_main.exists() and not overwrite:
        print(f"Skip (exists): {dest_main}")
    else:
        _copy_or_move(candidate.source_path, dest_main, move and candidate.source_path.exists())
        written.append(dest_main)
        copied_sources.append(candidate.source_path)

    dependencies = []
    if candidate.extension == ".cue":
        dependencies = cue_dependencies(candidate.source_path)
    elif candidate.extension == ".gdi":
        dependencies = gdi_dependencies(candidate.source_path)

    for dep in dependencies:
        dep_source = (candidate.source_path.parent / dep).resolve()
        dep_dest = destination_dir / dep
        if dep_dest.exists() and not overwrite:
            print(f"Skip (exists): {dep_dest}")
            continue
        if not dep_source.exists():
            print(f"Warning: Companion file missing for {candidate.source_path}: {dep}")
            continue
        dep_dest.parent.mkdir(parents=True, exist_ok=True)
        _copy_or_move(dep_source, dep_dest, move and dep_source.exists())
        written.append(dep_dest)
        copied_sources.append(dep_source)

    return written, copied_sources


def _copy_or_move(src: Path, dest: Path, move: bool) -> None:
    if move:
        shutil.move(str(src), str(dest))
    else:
        shutil.copy2(src, dest)


def write_m3u(m3u_path: Path, disc_paths: List[str], overwrite: bool) -> None:
    if m3u_path.exists() and not overwrite:
        print(f"Skip m3u (exists): {m3u_path}")
        return

    m3u_path.parent.mkdir(parents=True, exist_ok=True)
    m3u_lines = [p for p in disc_paths]
    m3u_path.write_text("\n".join(m3u_lines) + "\n")
    print(f"Wrote playlist: {m3u_path}")


def organize(
    source_dir: Path,
    system: SystemDefinition,
    rom_root: Path,
    overwrite: bool = False,
    move: bool = False,
    include_hidden: bool = False,
) -> None:
    if not source_dir.exists():
        raise SystemExit(f"Source directory not found: {source_dir}")

    rom_root = rom_root.expanduser().resolve()
    target_system_dir = system.resolve_rom_path(rom_root)
    target_system_dir.mkdir(parents=True, exist_ok=True)
    multi_disc_dir = target_system_dir / ".multidisc"

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        candidates = gather_candidates(source_dir, system, include_hidden, tmp_dir)

        if not candidates:
            print("No ROM candidates found matching system extensions.")
            return

        multi_groups = group_multi_disc(candidates)
        handled_sources = set()

        if system.supports_m3u():
            for base_lower, group in multi_groups.items():
                base_name = group[0].base_name or base_lower
                print(f"Handling multi-disc title: {base_name} ({len(group)} discs)")

                disc_rel_paths: List[str] = []
                for cand in group:
                    if should_use_disc_subdir(cand.extension):
                        disc_dir = multi_disc_dir / cand.source_path.name
                        written, sources = copy_with_companions(cand, disc_dir, overwrite, move)
                        handled_sources.update(sources)
                        if written:
                            main_file = disc_dir / cand.source_path.name
                            rel = main_file.relative_to(target_system_dir)
                            disc_rel_paths.append(f"./{rel.as_posix()}")
                    else:
                        dest = multi_disc_dir / cand.source_path.name
                        if dest.exists() and not overwrite:
                            print(f"Skip (exists): {dest}")
                        else:
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            _copy_or_move(cand.source_path, dest, move)
                        rel = dest.relative_to(target_system_dir)
                        disc_rel_paths.append(f"./{rel.as_posix()}")
                        handled_sources.add(cand.source_path)

                m3u_path = target_system_dir / f"{base_name}.m3u"
                write_m3u(m3u_path, disc_rel_paths, overwrite)
        else:
            if multi_groups:
                print(f"Note: {system.name} does not list .m3u support; multi-disc playlists were skipped.")

        for cand in candidates:
            if cand.source_path in handled_sources:
                continue

            dest_parent = target_system_dir
            if should_use_disc_subdir(cand.extension) and is_disc_based_system(system):
                dest_parent = target_system_dir / cand.source_path.name

            _, sources = copy_with_companions(cand, dest_parent, overwrite, move)
            handled_sources.update(sources)

    print(f"Organization complete for system '{system.name}' in {target_system_dir}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        system = load_system(args.es_systems.expanduser(), args.system)
        if not is_disc_based_system(system):
            print(f"System '{system.name}' does not appear disc-based; disc layout features may be skipped.")

        organize(
            source_dir=args.source.expanduser(),
            system=system,
            rom_root=args.rom_root,
            overwrite=args.overwrite,
            move=args.move,
            include_hidden=args.include_hidden,
        )
        return 0
    except SystemExit as exc:
        print(exc)
        return 1
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
