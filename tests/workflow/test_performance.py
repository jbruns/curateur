import pytest

from curateur.workflow.performance import PerformanceMonitor


@pytest.mark.unit
def test_performance_monitor_metrics_and_eta(monkeypatch):
    monitor = PerformanceMonitor(total_roms=4)

    # Avoid real CPU/memory sampling variance
    class FakeProcess:
        def memory_info(self):
            from types import SimpleNamespace

            return SimpleNamespace(rss=100 * 1024 * 1024)

        def cpu_percent(self, interval=None):
            return 10.0

    monkeypatch.setattr(monitor, "process", FakeProcess())

    monitor.record_api_call(duration=0.2)
    monitor.record_api_call(duration=0.3)
    monitor.record_rom_processing(duration=0.5)
    monitor.record_download()
    monitor.record_rom_processed()

    metrics = monitor.get_metrics()

    assert metrics.roms_processed == 2  # record_rom_processing increments, record_rom_processed increments
    assert metrics.api_calls == 2
    assert metrics.downloads == 1
    assert metrics.avg_api_time > 0
    assert metrics.avg_rom_time > 0
    assert metrics.percent_complete > 0


@pytest.mark.unit
def test_performance_monitor_eta_caching(monkeypatch):
    monitor = PerformanceMonitor(total_roms=2)

    class FakeProcess:
        def memory_info(self):
            from types import SimpleNamespace

            return SimpleNamespace(rss=0)

        def cpu_percent(self, interval=None):
            return 0.0

    monkeypatch.setattr(monitor, "process", FakeProcess())

    # No timings -> zero eta
    metrics1 = monitor.get_metrics()
    assert metrics1.eta_seconds == 0

    # Provide timing to set ETA cache
    monitor.record_rom_processing(duration=1.0)
    metrics2 = monitor.get_metrics()
    cached_eta = metrics2.eta_seconds
    # No new ROMs processed; eta should stay cached
    metrics3 = monitor.get_metrics()
    assert metrics3.eta_seconds == cached_eta
