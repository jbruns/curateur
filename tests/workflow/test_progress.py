from curateur.workflow.progress import ProgressTracker, ErrorLogger


def test_progress_tracker_counts_and_summary(capsys):
    tracker = ProgressTracker()
    tracker.start_system("nes", total_roms=2)
    tracker.log_rom("Alpha", "success")
    tracker.log_rom("Beta", "skipped", detail="user skipped")
    tracker.finish_system()
    tracker.print_final_summary()

    captured = capsys.readouterr().out
    assert "Scraping nes" in captured
    assert "Alpha" in captured and "Beta" in captured
    assert "Skipped" in captured
    assert "Final Summary" in captured


def test_error_logger_accumulates_and_writes(tmp_path, capsys):
    logger = ErrorLogger()
    logger.log_error("Alpha.zip", "failed")
    logger.log_error("Beta.zip", "timeout")

    out_file = tmp_path / "errors.log"
    logger.write_summary(str(out_file))

    assert out_file.exists()
    content = out_file.read_text()
    assert "Alpha.zip" in content and "failed" in content
    assert "Beta.zip" in content and "timeout" in content


def test_progress_tracker_no_systems(capsys):
    tracker = ProgressTracker()
    tracker.print_final_summary()
    out = capsys.readouterr().out
    assert "No systems processed" in out
