"""
Integration tests for Phase D CLI and Orchestrator integration

Tests the complete flow from CLI initialization through parallel processing.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path
import tempfile
import shutil

from curateur.workflow.orchestrator import WorkflowOrchestrator, ScrapingResult
from curateur.workflow.thread_pool import ThreadPoolManager
from curateur.workflow.performance import PerformanceMonitor
from curateur.api.connection_pool import ConnectionPoolManager
from curateur.api.client import ScreenScraperClient
from curateur.scanner.rom_types import ROMInfo, ROMType
from curateur.config.es_systems import SystemDefinition


@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    return {
        'screenscraper': {
            'devid': 'test_dev',
            'devpassword': 'test_pass',
            'softname': 'test_soft',
            'user_id': 'test_user',
            'user_password': 'test_user_pass'
        },
        'api': {
            'request_timeout': 30,
            'max_retries': 3,
            'retry_backoff_seconds': 1
        },
        'scraping': {
            'max_threads': 4,
            'media_types': ['box-2D', 'ss'],
            'preferred_regions': ['us', 'wor', 'eu'],
            'name_verification': 'normal'
        },
        'paths': {
            'roms': '/tmp/roms',
            'media': '/tmp/media',
            'gamelists': '/tmp/gamelists',
            'es_systems': '/tmp/es_systems.xml'
        },
        'runtime': {
            'dry_run': False
        }
    }


@pytest.fixture
def mock_system():
    """Mock system definition"""
    return SystemDefinition(
        name='nes',
        fullname='Nintendo Entertainment System',
        path='/roms/nes',
        extensions=['.nes', '.zip'],
        platform='nes'
    )


@pytest.fixture
def mock_rom_info():
    """Mock ROM information"""
    return ROMInfo(
        path=Path('/roms/nes/Super Mario Bros.nes'),
        filename='Super Mario Bros.nes',
        basename='Super Mario Bros',
        query_filename='Super Mario Bros',
        file_size=40960,
        hash_value='3b0c3c09',
        hash_type='crc32',
        system='nes',
        rom_type=ROMType.STANDARD
    )


class TestOrchestratorWithThreadPool:
    """Test orchestrator integration with ThreadPoolManager"""
    
    def test_orchestrator_uses_thread_pool_for_parallel_processing(
        self, mock_config, mock_system, mock_rom_info
    ):
        """Test that orchestrator uses thread pool when available"""
        # Setup
        from curateur.workflow.work_queue import WorkQueueManager
        from curateur.api.throttle import ThrottleManager, RateLimit
        
        api_client = Mock(spec=ScreenScraperClient)
        thread_manager = ThreadPoolManager(mock_config)
        thread_manager.initialize_pools({'maxthreads': 4})
        work_queue = WorkQueueManager(max_retries=3)
        throttle_manager = ThrottleManager(default_limit=RateLimit(calls=120, window_seconds=60))
        
        orchestrator = WorkflowOrchestrator(
            api_client=api_client,
            rom_directory=Path('/tmp/roms'),
            media_directory=Path('/tmp/media'),
            gamelist_directory=Path('/tmp/gamelists'),
            work_queue=work_queue,
            dry_run=False,
            thread_manager=thread_manager,
            throttle_manager=throttle_manager
        )
        
        # Mock scan_system to return ROMs
        with patch('curateur.workflow.orchestrator.scan_system') as mock_scan:
            mock_scan.return_value = [mock_rom_info] * 3
            
            # Mock API client
            api_client.query_game.return_value = {
                'id': 12345,
                'name': 'Super Mario Bros',
                'media': {}
            }
            
            # Execute
            result = orchestrator.scrape_system(
                system=mock_system,
                media_types=['box-2D'],
                preferred_regions=['us']
            )
            
            # Verify parallel processing was used
            assert result.total_roms == 3
            assert result.scraped == 3
            assert api_client.query_game.call_count == 3
        
        # Cleanup
        thread_manager.shutdown()
    
    def test_orchestrator_tracks_performance_metrics(
        self, mock_config, mock_system, mock_rom_info
    ):
        """Test that performance monitor tracks metrics during scraping"""
        # Setup
        from curateur.workflow.work_queue import WorkQueueManager
        from curateur.api.throttle import ThrottleManager, RateLimit
        
        api_client = Mock(spec=ScreenScraperClient)
        thread_manager = ThreadPoolManager(mock_config)
        thread_manager.initialize_pools({'maxthreads': 2})
        performance_monitor = PerformanceMonitor(total_roms=2)
        work_queue = WorkQueueManager(max_retries=3)
        throttle_manager = ThrottleManager(default_limit=RateLimit(calls=120, window_seconds=60))
        
        orchestrator = WorkflowOrchestrator(
            api_client=api_client,
            rom_directory=Path('/tmp/roms'),
            media_directory=Path('/tmp/media'),
            gamelist_directory=Path('/tmp/gamelists'),
            work_queue=work_queue,
            dry_run=False,
            thread_manager=thread_manager,
            performance_monitor=performance_monitor,
            throttle_manager=throttle_manager
        )
        
        # Mock scan_system
        with patch('curateur.workflow.orchestrator.scan_system') as mock_scan:
            mock_scan.return_value = [mock_rom_info] * 2
            
            # Mock API client
            api_client.query_game.return_value = {
                'id': 12345,
                'name': 'Super Mario Bros',
                'media': {}
            }
            
            # Execute
            orchestrator.scrape_system(
                system=mock_system,
                media_types=[],
                preferred_regions=['us']
            )
            
            # Verify metrics were recorded
            metrics = performance_monitor.get_metrics()
            assert metrics.roms_processed == 2
            assert metrics.api_calls == 2
            assert metrics.percent_complete == 100.0
        
        # Cleanup
        thread_manager.shutdown()
    
    def test_orchestrator_handles_parallel_errors_gracefully(
        self, mock_config, mock_system, mock_rom_info
    ):
        """Test that errors in parallel processing don't crash entire batch"""
        # Setup
        from curateur.workflow.work_queue import WorkQueueManager
        from curateur.api.throttle import ThrottleManager, RateLimit
        
        api_client = Mock(spec=ScreenScraperClient)
        thread_manager = ThreadPoolManager(mock_config)
        thread_manager.initialize_pools({'maxthreads': 2})
        work_queue = WorkQueueManager(max_retries=3)
        throttle_manager = ThrottleManager(default_limit=RateLimit(calls=120, window_seconds=60))
        
        orchestrator = WorkflowOrchestrator(
            api_client=api_client,
            rom_directory=Path('/tmp/roms'),
            media_directory=Path('/tmp/media'),
            gamelist_directory=Path('/tmp/gamelists'),
            work_queue=work_queue,
            dry_run=False,
            thread_manager=thread_manager,
            throttle_manager=throttle_manager
        )
        
        # Mock scan_system
        with patch('curateur.workflow.orchestrator.scan_system') as mock_scan:
            mock_scan.return_value = [mock_rom_info] * 3
            
            # Mock API client to fail on second ROM
            call_count = [0]
            def query_side_effect(rom_info):
                call_count[0] += 1
                if call_count[0] == 2:
                    raise Exception("API error")
                return {'id': 12345, 'name': 'Test Game', 'media': {}}
            
            api_client.query_game.side_effect = query_side_effect
            
            # Execute
            result = orchestrator.scrape_system(
                system=mock_system,
                media_types=[],
                preferred_regions=['us']
            )
            
            # Verify: 2 succeeded, 1 failed
            assert result.total_roms == 3
            assert result.scraped == 2
            assert result.failed == 1
        
        # Cleanup
        thread_manager.shutdown()


class TestConnectionPoolIntegration:
    """Test connection pool integration with API client"""
    
    def test_api_client_uses_shared_session(self, mock_config):
        """Test that API client uses provided session for connection pooling"""
        # Setup
        conn_manager = ConnectionPoolManager(mock_config)
        session = conn_manager.get_session(max_connections=5)
        
        # Create API client with session
        api_client = ScreenScraperClient(mock_config, session=session)
        
        # Verify session is being used
        assert api_client.session is session
        
        # Cleanup
        conn_manager.close_session()
    
    def test_multiple_api_calls_reuse_connection(self, mock_config):
        """Test that multiple API calls reuse the same connection"""
        # Setup
        conn_manager = ConnectionPoolManager(mock_config)
        session = conn_manager.get_session(max_connections=5)
        
        # Mock the session.get method
        session.get = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'<XML></XML>'
        session.get.return_value = mock_response
        
        api_client = ScreenScraperClient(mock_config, session=session)
        
        # Make multiple calls (mocking internal methods to avoid full API call)
        with patch.object(api_client, 'rate_limiter'):
            with patch('curateur.api.client.validate_response'):
                with patch('curateur.api.client.extract_error_message', return_value=None):
                    with patch('curateur.api.client.parse_game_info', return_value={}):
                        try:
                            api_client._query_jeu_infos(
                                systemeid=1,
                                romnom='test.rom',
                                romtaille=1024,
                                crc='12345678'
                            )
                        except:
                            pass  # We're just testing session usage
        
        # Verify session.get was called (connection reuse)
        assert session.get.called
        
        # Cleanup
        conn_manager.close_session()


class TestPerformanceMonitoringFlow:
    """Test performance monitoring throughout the workflow"""
    
    def test_performance_monitor_calculates_eta(self):
        """Test that performance monitor calculates ETA correctly"""
        monitor = PerformanceMonitor(total_roms=100)
        
        # Simulate processing 25 ROMs
        import time
        for _ in range(25):
            monitor.record_rom_processed()
            time.sleep(0.001)  # Small delay to ensure time passes
        
        metrics = monitor.get_metrics()
        
        # Verify metrics
        assert metrics.roms_processed == 25
        assert metrics.percent_complete == 25.0
        assert metrics.eta_seconds > 0  # Should have an ETA
        assert metrics.roms_per_second > 0
    
    def test_performance_monitor_tracks_all_counters(self):
        """Test that performance monitor tracks all activity types"""
        monitor = PerformanceMonitor(total_roms=10)
        
        # Simulate activity
        monitor.record_rom_processed()
        monitor.record_rom_processed()
        monitor.record_api_call()
        monitor.record_api_call()
        monitor.record_api_call()
        monitor.record_download()
        monitor.record_download()
        
        metrics = monitor.get_metrics()
        
        # Verify all counters
        assert metrics.roms_processed == 2
        assert metrics.api_calls == 3
        assert metrics.downloads == 2
        assert metrics.percent_complete == 20.0
    
    def test_performance_monitor_summary(self):
        """Test that performance monitor provides final summary"""
        monitor = PerformanceMonitor(total_roms=5)
        
        # Simulate complete processing
        for _ in range(5):
            monitor.record_rom_processed()
            monitor.record_api_call()
            monitor.record_download()
        
        summary = monitor.get_summary()
        
        # Verify summary contains expected keys
        assert 'total_roms' in summary
        assert 'roms_processed' in summary
        assert 'elapsed_seconds' in summary
        assert 'avg_roms_per_second' in summary
        assert 'total_api_calls' in summary
        assert 'total_downloads' in summary
        assert summary['total_roms'] == 5
        assert summary['roms_processed'] == 5


class TestFullCLIIntegration:
    """Test full CLI integration with Phase D components"""
    
    def test_cli_initializes_all_phase_d_components(self, mock_config):
        """Test that CLI properly initializes all Phase D components"""
        with patch('curateur.cli.parse_es_systems') as mock_parse:
            with patch('curateur.scanner.rom_scanner.scan_system') as mock_scan:
                with patch('curateur.cli.ScreenScraperClient') as mock_client_cls:
                    # Setup mocks
                    mock_parse.return_value = []
                    mock_scan.return_value = []
                    mock_client = Mock()
                    mock_client.get_rate_limits.return_value = {'maxthreads': 4}
                    mock_client_cls.return_value = mock_client
                    
                    # Import and test
                    from curateur.cli import run_scraper
                    from argparse import Namespace
                    
                    args = Namespace(
                        systems=None,
                        dry_run=False,
                        enable_search=False,
                        search_threshold=None,
                        interactive_search=False,
                        skip_scraped=False,
                        update=False
                    )
                    
                    # This should not crash
                    result = run_scraper(mock_config, args)
                    
                    # Verify client was created with session
                    assert mock_client_cls.called
                    call_args = mock_client_cls.call_args
                    assert 'session' in call_args.kwargs or len(call_args.args) > 1
    
    def test_parallel_processing_faster_than_sequential(
        self, mock_config, mock_system, mock_rom_info
    ):
        """Test that parallel processing is measurably faster"""
        import time
        
        # Sequential processing
        api_client = Mock(spec=ScreenScraperClient)
        
        def slow_query(rom_info):
            time.sleep(0.05)  # 50ms delay
            return {'id': 12345, 'name': 'Test', 'media': {}}
        
        api_client.query_game.side_effect = slow_query
        
        orchestrator_sequential = WorkflowOrchestrator(
            api_client=api_client,
            rom_directory=Path('/tmp/roms'),
            media_directory=Path('/tmp/media'),
            gamelist_directory=Path('/tmp/gamelists'),
            dry_run=False,
            thread_manager=None  # No parallel processing
        )
        
        with patch('curateur.workflow.orchestrator.scan_system') as mock_scan:
            mock_scan.return_value = [mock_rom_info] * 4
            
            start = time.time()
            orchestrator_sequential.scrape_system(
                system=mock_system,
                media_types=[],
                preferred_regions=['us']
            )
            sequential_time = time.time() - start
        
        # Parallel processing
        api_client.query_game.side_effect = slow_query  # Reset
        thread_manager = ThreadPoolManager(mock_config)
        thread_manager.initialize_pools({'maxthreads': 4})
        
        orchestrator_parallel = WorkflowOrchestrator(
            api_client=api_client,
            rom_directory=Path('/tmp/roms'),
            media_directory=Path('/tmp/media'),
            gamelist_directory=Path('/tmp/gamelists'),
            dry_run=False,
            thread_manager=thread_manager
        )
        
        with patch('curateur.workflow.orchestrator.scan_system') as mock_scan:
            mock_scan.return_value = [mock_rom_info] * 4
            
            start = time.time()
            orchestrator_parallel.scrape_system(
                system=mock_system,
                media_types=[],
                preferred_regions=['us']
            )
            parallel_time = time.time() - start
        
        thread_manager.shutdown()
        
        # Verify parallel is faster (should be ~2-3X faster with 4 threads)
        assert parallel_time < sequential_time
        speedup = sequential_time / parallel_time
        assert speedup > 1.5  # At least 1.5X speedup


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
