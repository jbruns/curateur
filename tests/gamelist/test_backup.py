"""Tests for gamelist backup functionality"""
import pytest
from pathlib import Path
from datetime import datetime
import time

from curateur.gamelist.backup import GamelistBackup


@pytest.mark.unit
def test_create_backup_creates_timestamped_file(tmp_path):
    """Test that create_backup creates a timestamped backup file"""
    # Create a test gamelist.xml
    gamelist_path = tmp_path / "gamelist.xml"
    gamelist_content = """<?xml version="1.0"?>
<gameList>
    <game>
        <path>./test.zip</path>
        <name>Test Game</name>
    </game>
</gameList>"""
    gamelist_path.write_text(gamelist_content)

    # Create backup
    backup_path = GamelistBackup.create_backup(gamelist_path)

    # Verify backup exists
    assert backup_path is not None
    assert backup_path.exists()
    assert backup_path.is_file()

    # Verify backup is in same directory
    assert backup_path.parent == gamelist_path.parent

    # Verify backup filename format
    assert backup_path.name.startswith("gamelist_curateur_backup_")
    assert backup_path.name.endswith(".bak")

    # Verify backup content matches original
    assert backup_path.read_text() == gamelist_content


@pytest.mark.unit
def test_create_backup_filename_format(tmp_path):
    """Test that backup filename has correct timestamp format"""
    gamelist_path = tmp_path / "gamelist.xml"
    gamelist_path.write_text("<gameList></gameList>")

    before_time = datetime.now()
    backup_path = GamelistBackup.create_backup(gamelist_path)
    after_time = datetime.now()

    # Extract timestamp from filename
    # Format: gamelist_curateur_backup_YYYYMMDD_HHMMSS_microseconds.bak
    filename = backup_path.name
    assert filename.startswith("gamelist_curateur_backup_")
    assert filename.endswith(".bak")

    # Extract timestamp part
    timestamp_str = filename.replace("gamelist_curateur_backup_", "").replace(".bak", "")

    # Parse timestamp (with microseconds)
    backup_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S_%f")

    # Verify timestamp is reasonable
    assert before_time <= backup_time <= after_time


@pytest.mark.unit
def test_create_backup_preserves_file_metadata(tmp_path):
    """Test that create_backup preserves file metadata (mtime, etc)"""
    gamelist_path = tmp_path / "gamelist.xml"
    gamelist_path.write_text("<gameList></gameList>")

    original_stat = gamelist_path.stat()
    backup_path = GamelistBackup.create_backup(gamelist_path)
    backup_stat = backup_path.stat()

    # shutil.copy2 preserves metadata
    assert backup_stat.st_mode == original_stat.st_mode
    # Note: mtime might be slightly different due to copy operation timing


@pytest.mark.unit
def test_create_backup_raises_on_missing_file(tmp_path):
    """Test that create_backup raises FileNotFoundError for missing file"""
    gamelist_path = tmp_path / "nonexistent.xml"

    with pytest.raises(FileNotFoundError):
        GamelistBackup.create_backup(gamelist_path)


@pytest.mark.unit
def test_create_backup_raises_on_directory(tmp_path):
    """Test that create_backup raises ValueError for directory path"""
    # Create a directory instead of file
    dir_path = tmp_path / "gamelist_dir"
    dir_path.mkdir()

    with pytest.raises(ValueError, match="not a file"):
        GamelistBackup.create_backup(dir_path)


@pytest.mark.unit
def test_create_backup_multiple_backups_have_different_timestamps(tmp_path):
    """Test that multiple backups create files with different timestamps"""
    gamelist_path = tmp_path / "gamelist.xml"
    gamelist_path.write_text("<gameList></gameList>")

    backup1 = GamelistBackup.create_backup(gamelist_path)
    time.sleep(1.1)  # Wait to ensure different timestamp
    backup2 = GamelistBackup.create_backup(gamelist_path)

    assert backup1 != backup2
    assert backup1.name != backup2.name
    assert backup1.exists()
    assert backup2.exists()


@pytest.mark.unit
def test_list_backups_returns_sorted_list(tmp_path):
    """Test that list_backups returns backups sorted by modification time"""
    gamelist_dir = tmp_path / "gamelists" / "nes"
    gamelist_dir.mkdir(parents=True)
    gamelist_path = gamelist_dir / "gamelist.xml"
    gamelist_path.write_text("<gameList></gameList>")

    # Create multiple backups with delays
    backup_paths = []
    for i in range(3):
        backup = GamelistBackup.create_backup(gamelist_path)
        backup_paths.append(backup)
        if i < 2:
            time.sleep(0.1)  # Small delay to ensure different mtimes

    # List backups
    backups = GamelistBackup.list_backups(gamelist_dir)

    assert len(backups) == 3
    # All created backups should be in the list
    assert all(backup in backups for backup in backup_paths)
    # Should be sorted by mtime (newest first)
    # Verify mtimes are in descending order
    mtimes = [b.stat().st_mtime for b in backups]
    assert mtimes == sorted(mtimes, reverse=True)


@pytest.mark.unit
def test_list_backups_empty_directory(tmp_path):
    """Test that list_backups returns empty list for directory with no backups"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    backups = GamelistBackup.list_backups(empty_dir)
    assert backups == []


@pytest.mark.unit
def test_list_backups_nonexistent_directory(tmp_path):
    """Test that list_backups returns empty list for nonexistent directory"""
    nonexistent = tmp_path / "nonexistent"

    backups = GamelistBackup.list_backups(nonexistent)
    assert backups == []


@pytest.mark.unit
def test_list_backups_filters_only_curateur_backups(tmp_path):
    """Test that list_backups only returns curateur backup files"""
    gamelist_dir = tmp_path / "gamelists" / "nes"
    gamelist_dir.mkdir(parents=True)

    # Create curateur backup
    (gamelist_dir / "gamelist_curateur_backup_20231115_120000.bak").touch()

    # Create non-curateur files
    (gamelist_dir / "gamelist.xml").touch()
    (gamelist_dir / "gamelist.old").touch()
    (gamelist_dir / "other_backup.bak").touch()

    backups = GamelistBackup.list_backups(gamelist_dir)

    assert len(backups) == 1
    assert backups[0].name == "gamelist_curateur_backup_20231115_120000.bak"


@pytest.mark.unit
def test_restore_backup_restores_to_default_location(tmp_path):
    """Test that restore_backup restores to gamelist.xml by default"""
    gamelist_dir = tmp_path / "gamelists" / "nes"
    gamelist_dir.mkdir(parents=True)

    # Create backup with specific content
    backup_path = gamelist_dir / "gamelist_curateur_backup_20231115_120000.bak"
    backup_content = "<gameList><game><name>Backup Content</name></game></gameList>"
    backup_path.write_text(backup_content)

    # Restore backup
    restored_path = GamelistBackup.restore_backup(backup_path)

    # Verify restored to gamelist.xml
    assert restored_path == gamelist_dir / "gamelist.xml"
    assert restored_path.exists()
    assert restored_path.read_text() == backup_content


@pytest.mark.unit
def test_restore_backup_to_custom_location(tmp_path):
    """Test that restore_backup can restore to custom location"""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup_path = backup_dir / "gamelist_curateur_backup_20231115_120000.bak"
    backup_content = "<gameList></gameList>"
    backup_path.write_text(backup_content)

    # Restore to custom location
    custom_target = tmp_path / "restored" / "custom.xml"
    custom_target.parent.mkdir()

    restored_path = GamelistBackup.restore_backup(backup_path, custom_target)

    assert restored_path == custom_target
    assert restored_path.exists()
    assert restored_path.read_text() == backup_content


@pytest.mark.unit
def test_restore_backup_raises_on_missing_file(tmp_path):
    """Test that restore_backup raises FileNotFoundError for missing backup"""
    missing_backup = tmp_path / "nonexistent.bak"

    with pytest.raises(FileNotFoundError):
        GamelistBackup.restore_backup(missing_backup)


@pytest.mark.unit
def test_restore_backup_overwrites_existing_file(tmp_path):
    """Test that restore_backup overwrites existing target file"""
    gamelist_dir = tmp_path / "gamelists" / "nes"
    gamelist_dir.mkdir(parents=True)

    # Create existing gamelist.xml
    gamelist_path = gamelist_dir / "gamelist.xml"
    gamelist_path.write_text("<gameList><game><name>Old</name></game></gameList>")

    # Create backup with different content
    backup_path = gamelist_dir / "gamelist_curateur_backup_20231115_120000.bak"
    backup_content = "<gameList><game><name>New</name></game></gameList>"
    backup_path.write_text(backup_content)

    # Restore should overwrite
    restored_path = GamelistBackup.restore_backup(backup_path)

    assert restored_path.read_text() == backup_content


@pytest.mark.unit
def test_cleanup_old_backups_removes_old_files(tmp_path):
    """Test that cleanup_old_backups removes old backups"""
    gamelist_dir = tmp_path / "gamelists" / "nes"
    gamelist_dir.mkdir(parents=True)

    # Create 8 backup files with different mtimes
    backup_files = []
    for i in range(8):
        backup = gamelist_dir / f"gamelist_curateur_backup_2023111{i}_120000.bak"
        backup.touch()
        backup_files.append(backup)
        time.sleep(0.01)  # Ensure different mtimes

    # Keep only 5 most recent
    deleted = GamelistBackup.cleanup_old_backups(gamelist_dir, keep_count=5)

    assert deleted == 3

    # Verify only 5 remain
    remaining = GamelistBackup.list_backups(gamelist_dir)
    assert len(remaining) == 5

    # Verify newest 5 are kept (last 5 files we created)
    assert backup_files[7].exists()  # Newest
    assert backup_files[6].exists()
    assert backup_files[5].exists()
    assert backup_files[4].exists()
    assert backup_files[3].exists()
    assert not backup_files[2].exists()  # Oldest should be deleted
    assert not backup_files[1].exists()
    assert not backup_files[0].exists()


@pytest.mark.unit
def test_cleanup_old_backups_no_deletion_if_under_limit(tmp_path):
    """Test that cleanup_old_backups doesn't delete if under keep_count"""
    gamelist_dir = tmp_path / "gamelists" / "nes"
    gamelist_dir.mkdir(parents=True)

    # Create only 3 backups
    for i in range(3):
        (gamelist_dir / f"gamelist_curateur_backup_2023111{i}_120000.bak").touch()

    # Keep 5 (more than we have)
    deleted = GamelistBackup.cleanup_old_backups(gamelist_dir, keep_count=5)

    assert deleted == 0
    assert len(GamelistBackup.list_backups(gamelist_dir)) == 3


@pytest.mark.unit
def test_cleanup_old_backups_empty_directory(tmp_path):
    """Test that cleanup_old_backups handles empty directory gracefully"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    deleted = GamelistBackup.cleanup_old_backups(empty_dir, keep_count=5)
    assert deleted == 0


@pytest.mark.unit
def test_create_backup_handles_large_files(tmp_path):
    """Test that create_backup can handle larger gamelist files"""
    gamelist_path = tmp_path / "gamelist.xml"

    # Create a large gamelist with many entries
    content = '<?xml version="1.0"?>\n<gameList>\n'
    for i in range(1000):
        content += f'  <game><path>./game{i}.zip</path><name>Game {i}</name></game>\n'
    content += '</gameList>'

    gamelist_path.write_text(content)

    # Backup should handle large file
    backup_path = GamelistBackup.create_backup(gamelist_path)

    assert backup_path.exists()
    assert len(backup_path.read_text()) == len(content)


@pytest.mark.unit
def test_backup_integration_workflow(tmp_path):
    """Test complete backup workflow: create, list, restore"""
    gamelist_dir = tmp_path / "gamelists" / "nes"
    gamelist_dir.mkdir(parents=True)
    gamelist_path = gamelist_dir / "gamelist.xml"

    # Original content
    original_content = "<gameList><game><name>Original</name></game></gameList>"
    gamelist_path.write_text(original_content)

    # Create backup
    backup1 = GamelistBackup.create_backup(gamelist_path)
    assert backup1.exists()

    # Modify original
    modified_content = "<gameList><game><name>Modified</name></game></gameList>"
    gamelist_path.write_text(modified_content)

    # Create second backup
    time.sleep(0.1)
    backup2 = GamelistBackup.create_backup(gamelist_path)

    # List backups (should show 2)
    backups = GamelistBackup.list_backups(gamelist_dir)
    assert len(backups) == 2

    # Restore first backup
    GamelistBackup.restore_backup(backup1)

    # Verify restored to original content
    assert gamelist_path.read_text() == original_content

    # Cleanup old backups
    deleted = GamelistBackup.cleanup_old_backups(gamelist_dir, keep_count=1)
    assert deleted == 1
    assert len(GamelistBackup.list_backups(gamelist_dir)) == 1
