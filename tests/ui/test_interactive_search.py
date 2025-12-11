"""Unit tests for interactive search functionality."""

import asyncio
import uuid
from datetime import datetime
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch

from curateur.ui.event_bus import EventBus
from curateur.ui.events import SearchRequestEvent, SearchResponseEvent
from curateur.ui.textual_ui import CurateurUI
from curateur.workflow.orchestrator import WorkflowOrchestrator
from curateur.scanner.rom_types import ROMInfo, ROMType
from pathlib import Path


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def event_bus():
    """Create an event bus for testing."""
    return EventBus()


@pytest.fixture
def config():
    """Create a dummy config for testing."""
    return {
        'scraping': {
            'systems': ['nes'],
            'preferred_regions': ['us', 'wor', 'eu']
        },
        'runtime': {
            'enable_cache': False
        },
        'paths': {},
        'media': {}
    }


@pytest.fixture
def mock_api_client():
    """Create a mock API client."""
    client = Mock()
    client.cache = None
    return client


@pytest.fixture
def mock_work_queue():
    """Create a mock work queue."""
    queue = Mock()
    queue.reset_for_new_system = Mock()
    queue.get_stats = Mock(return_value={'processed': 0, 'failed': 0, 'pending': 0, 'max_retries': 3})
    queue.get_failed_items = Mock(return_value=[])
    return queue


@pytest.fixture
def orchestrator(config, mock_api_client, mock_work_queue, event_bus, tmp_path):
    """Create an orchestrator instance for testing."""
    return WorkflowOrchestrator(
        api_client=mock_api_client,
        rom_directory=tmp_path / "roms",
        media_directory=tmp_path / "media",
        gamelist_directory=tmp_path / "gamelists",
        work_queue=mock_work_queue,
        config=config,
        dry_run=True,
        enable_search_fallback=True,
        search_confidence_threshold=0.7,
        search_max_results=5,
        interactive_search=True,
        event_bus=event_bus,
    )


@pytest.fixture
def sample_rom_info():
    """Create a sample ROM info object."""
    return type('ROMInfo', (), {
        'filename': 'Super Mario Bros.nes',
        'path': Path('/roms/nes/Super Mario Bros.nes'),
        'system': 'nes',
        'file_size': 40960,
        'hash_type': 'crc32',
        'hash_value': 'ABCD1234',
        'query_filename': 'Super Mario Bros',
        'basename': 'Super Mario Bros',
        'rom_type': ROMType.STANDARD,
        'crc_size_limit': 1073741824,
        'disc_files': None,
        'contained_file': None
    })()


@pytest.fixture
def sample_search_results():
    """Create sample search results with different confidence scores."""
    return [
        {
            "game_data": {
                "id": "12345",
                "names": {"en": "Super Mario Bros.", "us": "Super Mario Bros."},
                "dates": {"us": "1985"},
                "regions": ["us", "wor"],
                "publisher": "Nintendo",
                "developer": "Nintendo EAD",
                "players": "1-2"
            },
            "confidence": 0.95
        },
        {
            "game_data": {
                "id": "67890",
                "names": {"en": "Super Mario Bros. 2"},
                "dates": {"us": "1988"},
                "regions": ["us"],
                "publisher": "Nintendo",
                "developer": "Nintendo EAD",
                "players": "1-2"
            },
            "confidence": 0.65
        },
        {
            "game_data": {
                "id": "11111",
                "names": {"jp": "スーパーマリオブラザーズ"},
                "dates": {"jp": "1985"},
                "regions": ["jp"],
                "publisher": "Nintendo",
                "developer": "Nintendo EAD",
                "players": "1-2"
            },
            "confidence": 0.50
        }
    ]


# ============================================================================
# Test SearchRequestEvent and SearchResponseEvent
# ============================================================================

class TestSearchEvents:
    """Test search event creation and properties."""

    def test_search_request_event_creation(self, sample_search_results):
        """Test creating a SearchRequestEvent."""
        event = SearchRequestEvent(
            request_id="test-uuid-123",
            rom_name="Super Mario Bros.nes",
            rom_path="/roms/nes/Super Mario Bros.nes",
            system="nes",
            search_results=sample_search_results
        )

        assert event.request_id == "test-uuid-123"
        assert event.rom_name == "Super Mario Bros.nes"
        assert event.rom_path == "/roms/nes/Super Mario Bros.nes"
        assert event.system == "nes"
        assert len(event.search_results) == 3
        assert event.search_results[0]["confidence"] == 0.95

    def test_search_request_event_frozen(self, sample_search_results):
        """Test that SearchRequestEvent is immutable."""
        event = SearchRequestEvent(
            request_id="test-123",
            rom_name="Test.nes",
            rom_path="/test.nes",
            system="nes",
            search_results=sample_search_results
        )

        with pytest.raises(AttributeError):
            event.request_id = "new-id"

    def test_search_response_event_selected(self):
        """Test creating a SearchResponseEvent with selection."""
        game_data = {"id": "12345", "names": {"en": "Test Game"}}
        event = SearchResponseEvent(
            request_id="test-123",
            action="selected",
            selected_game=game_data
        )

        assert event.request_id == "test-123"
        assert event.action == "selected"
        assert event.selected_game == game_data

    def test_search_response_event_skip(self):
        """Test creating a SearchResponseEvent with skip."""
        event = SearchResponseEvent(
            request_id="test-123",
            action="skip",
            selected_game=None
        )

        assert event.action == "skip"
        assert event.selected_game is None

    def test_search_response_event_cancel(self):
        """Test creating a SearchResponseEvent with cancel."""
        event = SearchResponseEvent(
            request_id="test-123",
            action="cancel"
        )

        assert event.action == "cancel"
        assert event.selected_game is None


# ============================================================================
# Test Orchestrator Search Response Handling
# ============================================================================

class TestOrchestratorSearchHandling:
    """Test orchestrator's search response handling methods."""

    @pytest.mark.asyncio
    async def test_handle_search_response_delivery(self, orchestrator):
        """Test that search responses are delivered to the correct queue."""
        request_id = "test-request-123"

        # Create a response queue manually
        response_queue = asyncio.Queue()
        async with orchestrator.search_response_lock:
            orchestrator.search_response_queues[request_id] = response_queue

        # Create and handle a response
        response = SearchResponseEvent(
            request_id=request_id,
            action="selected",
            selected_game={"id": "12345", "names": {"en": "Test Game"}}
        )

        await orchestrator.handle_search_response(response)

        # Verify response was delivered to queue
        delivered_response = await asyncio.wait_for(response_queue.get(), timeout=1.0)
        assert delivered_response.request_id == request_id
        assert delivered_response.action == "selected"
        assert delivered_response.selected_game["id"] == "12345"

    @pytest.mark.asyncio
    async def test_handle_search_response_unknown_request_id(self, orchestrator, caplog):
        """Test handling response for unknown request ID."""
        response = SearchResponseEvent(
            request_id="unknown-id",
            action="skip"
        )

        await orchestrator.handle_search_response(response)

        # Should log a warning
        assert "unknown request_id" in caplog.text

    @pytest.mark.asyncio
    async def test_wait_for_search_response_selected(
        self, orchestrator, sample_rom_info, sample_search_results, event_bus
    ):
        """Test waiting for user to select a game."""
        request_id = str(uuid.uuid4())
        scored_candidates = [
            (result["game_data"], result["confidence"])
            for result in sample_search_results
        ]

        # Start event processing
        event_task = asyncio.create_task(event_bus.process_events())

        try:
            # Create a task to wait for response
            wait_task = asyncio.create_task(
                orchestrator._wait_for_search_response(
                    request_id, sample_rom_info, scored_candidates
                )
            )

            # Give it time to emit event and wait
            await asyncio.sleep(0.1)

            # Simulate user response
            response = SearchResponseEvent(
                request_id=request_id,
                action="selected",
                selected_game=sample_search_results[0]["game_data"]
            )
            await orchestrator.handle_search_response(response)

            # Wait for result
            selected_game = await asyncio.wait_for(wait_task, timeout=2.0)

            # Verify result
            assert selected_game is not None
            assert selected_game["id"] == "12345"
            assert selected_game["names"]["en"] == "Super Mario Bros."
        finally:
            # Cleanup
            await event_bus.stop()
            try:
                await asyncio.wait_for(event_task, timeout=0.5)
            except asyncio.TimeoutError:
                event_task.cancel()
                try:
                    await event_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_wait_for_search_response_skip(
        self, orchestrator, sample_rom_info, sample_search_results, event_bus
    ):
        """Test waiting for user to skip a ROM."""
        request_id = str(uuid.uuid4())
        scored_candidates = [
            (result["game_data"], result["confidence"])
            for result in sample_search_results
        ]

        # Start event processing
        event_task = asyncio.create_task(event_bus.process_events())

        # Create a task to wait for response
        wait_task = asyncio.create_task(
            orchestrator._wait_for_search_response(
                request_id, sample_rom_info, scored_candidates
            )
        )

        # Give it time to emit event
        await asyncio.sleep(0.1)

        # Simulate user skipping
        response = SearchResponseEvent(
            request_id=request_id,
            action="skip",
            selected_game=None
        )
        await orchestrator.handle_search_response(response)

        # Wait for result
        selected_game = await asyncio.wait_for(wait_task, timeout=1.0)

        # Cleanup
        await event_bus.stop()
        event_task.cancel()

        # Verify result
        assert selected_game is None

    @pytest.mark.asyncio
    async def test_wait_for_search_response_emits_event(
        self, orchestrator, sample_rom_info, sample_search_results, event_bus
    ):
        """Test that _wait_for_search_response emits SearchRequestEvent."""
        received_events = []

        def capture_event(event):
            received_events.append(event)

        event_bus.subscribe(SearchRequestEvent, capture_event)

        request_id = str(uuid.uuid4())
        scored_candidates = [
            (result["game_data"], result["confidence"])
            for result in sample_search_results
        ]

        # Start event processing
        event_task = asyncio.create_task(event_bus.process_events())

        # Create task to wait (we'll cancel it)
        wait_task = asyncio.create_task(
            orchestrator._wait_for_search_response(
                request_id, sample_rom_info, scored_candidates
            )
        )

        # Give time for event to be processed
        await asyncio.sleep(0.2)

        # Cancel wait task and cleanup
        wait_task.cancel()
        await event_bus.stop()
        event_task.cancel()

        # Verify event was emitted
        assert len(received_events) == 1
        event = received_events[0]
        assert isinstance(event, SearchRequestEvent)
        assert event.request_id == request_id
        assert event.rom_name == "Super Mario Bros.nes"
        assert event.system == "nes"
        assert len(event.search_results) == 3

    @pytest.mark.asyncio
    async def test_wait_for_search_response_cleans_up_queue(
        self, orchestrator, sample_rom_info, sample_search_results
    ):
        """Test that response queue is cleaned up after response."""
        request_id = str(uuid.uuid4())
        scored_candidates = [
            (result["game_data"], result["confidence"])
            for result in sample_search_results
        ]

        # Create task to wait
        wait_task = asyncio.create_task(
            orchestrator._wait_for_search_response(
                request_id, sample_rom_info, scored_candidates
            )
        )

        # Give it time to create queue
        await asyncio.sleep(0.1)

        # Verify queue exists
        async with orchestrator.search_response_lock:
            assert request_id in orchestrator.search_response_queues

        # Send response
        response = SearchResponseEvent(
            request_id=request_id,
            action="cancel"
        )
        await orchestrator.handle_search_response(response)

        # Wait for completion
        await asyncio.wait_for(wait_task, timeout=1.0)

        # Verify queue was cleaned up
        async with orchestrator.search_response_lock:
            assert request_id not in orchestrator.search_response_queues


# ============================================================================
# Test UI Search Queue Processing
# ============================================================================

class TestUISearchQueue:
    """Test UI's search queue processing."""

    @pytest.mark.asyncio
    async def test_ui_search_queue_initialization(self, config, event_bus):
        """Test that UI initializes with search queue."""
        ui = CurateurUI(config, event_bus)

        assert hasattr(ui, 'search_queue')
        assert isinstance(ui.search_queue, asyncio.Queue)
        assert ui.current_search_dialog is None
        assert ui.search_processor_running is False

    @pytest.mark.asyncio
    async def test_on_search_request_queues_event(self, config, event_bus, sample_search_results):
        """Test that on_search_request queues the event."""
        ui = CurateurUI(config, event_bus)

        event = SearchRequestEvent(
            request_id="test-123",
            rom_name="Test.nes",
            rom_path="/test.nes",
            system="nes",
            search_results=sample_search_results
        )

        await ui.on_search_request(event)

        # Verify event was queued
        queued_event = await asyncio.wait_for(ui.search_queue.get(), timeout=1.0)
        assert queued_event.request_id == "test-123"
        assert queued_event.rom_name == "Test.nes"

    @pytest.mark.asyncio
    async def test_on_search_request_starts_processor_once(self, config, event_bus, sample_search_results):
        """Test that search processor only starts once."""
        ui = CurateurUI(config, event_bus)

        event1 = SearchRequestEvent(
            request_id="test-1",
            rom_name="Test1.nes",
            rom_path="/test1.nes",
            system="nes",
            search_results=sample_search_results
        )

        event2 = SearchRequestEvent(
            request_id="test-2",
            rom_name="Test2.nes",
            rom_path="/test2.nes",
            system="nes",
            search_results=sample_search_results
        )

        # Queue multiple events
        await ui.on_search_request(event1)
        initial_state = ui.search_processor_running

        await ui.on_search_request(event2)
        final_state = ui.search_processor_running

        # Processor should only start once
        assert initial_state == final_state

    @pytest.mark.asyncio
    async def test_show_search_dialog_data_conversion(self, config, event_bus, sample_search_results):
        """Test that _show_search_dialog converts data correctly."""
        ui = CurateurUI(config, event_bus)

        request = SearchRequestEvent(
            request_id="test-123",
            rom_name="Test.nes",
            rom_path="/test.nes",
            system="nes",
            search_results=sample_search_results
        )

        # Mock push_screen_wait to capture converted data
        converted_results = []

        async def mock_push_screen_wait(dialog):
            converted_results.extend(dialog.search_results)
            return ("skip", None)

        ui.push_screen_wait = mock_push_screen_wait

        # Call _show_search_dialog
        await ui._show_search_dialog(request)

        # Verify conversion
        assert len(converted_results) == 3
        assert converted_results[0]["name"] == "Super Mario Bros."
        assert converted_results[0]["year"] == "1985"
        assert converted_results[0]["region"] == "us"
        assert converted_results[0]["confidence"] == 0.95
        assert "_full_data" in converted_results[0]

    @pytest.mark.asyncio
    async def test_show_search_dialog_emits_selected_response(
        self, config, event_bus, sample_search_results
    ):
        """Test that selecting a game emits SearchResponseEvent."""
        ui = CurateurUI(config, event_bus)
        received_events = []

        def capture_event(event):
            received_events.append(event)

        event_bus.subscribe(SearchResponseEvent, capture_event)

        request = SearchRequestEvent(
            request_id="test-123",
            rom_name="Test.nes",
            rom_path="/test.nes",
            system="nes",
            search_results=sample_search_results
        )

        # Mock dialog to return selection
        selected_result = {
            "name": "Super Mario Bros.",
            "confidence": 0.95,
            "_full_data": sample_search_results[0]["game_data"]
        }

        async def mock_push_screen_wait(dialog):
            return ("selected", selected_result)

        ui.push_screen_wait = mock_push_screen_wait

        # Start event processing
        event_task = asyncio.create_task(event_bus.process_events())

        # Show dialog
        await ui._show_search_dialog(request)

        # Wait for event processing
        await asyncio.sleep(0.1)

        # Cleanup
        await event_bus.stop()
        event_task.cancel()

        # Verify event was emitted
        assert len(received_events) == 1
        response = received_events[0]
        assert isinstance(response, SearchResponseEvent)
        assert response.request_id == "test-123"
        assert response.action == "selected"
        assert response.selected_game["id"] == "12345"

    @pytest.mark.asyncio
    async def test_show_search_dialog_emits_skip_response(
        self, config, event_bus, sample_search_results
    ):
        """Test that skipping emits SearchResponseEvent with skip action."""
        ui = CurateurUI(config, event_bus)
        received_events = []

        def capture_event(event):
            received_events.append(event)

        event_bus.subscribe(SearchResponseEvent, capture_event)

        request = SearchRequestEvent(
            request_id="test-456",
            rom_name="Test.nes",
            rom_path="/test.nes",
            system="nes",
            search_results=sample_search_results
        )

        # Mock dialog to return skip
        async def mock_push_screen_wait(dialog):
            return ("skip", None)

        ui.push_screen_wait = mock_push_screen_wait

        # Start event processing
        event_task = asyncio.create_task(event_bus.process_events())

        # Show dialog
        await ui._show_search_dialog(request)

        # Wait for event processing
        await asyncio.sleep(0.1)

        # Cleanup
        await event_bus.stop()
        event_task.cancel()

        # Verify event
        assert len(received_events) == 1
        response = received_events[0]
        assert response.request_id == "test-456"
        assert response.action == "skip"
        assert response.selected_game is None


# ============================================================================
# Integration Tests
# ============================================================================

class TestInteractiveSearchIntegration:
    """Integration tests for complete search flow."""

    @pytest.mark.asyncio
    async def test_complete_search_flow_with_selection(
        self, config, event_bus, mock_api_client, mock_work_queue,
        sample_rom_info, sample_search_results, tmp_path
    ):
        """Test complete flow from search request to user selection."""
        # Create orchestrator with textual UI
        orchestrator = WorkflowOrchestrator(
            api_client=mock_api_client,
            rom_directory=tmp_path / "roms",
            media_directory=tmp_path / "media",
            gamelist_directory=tmp_path / "gamelists",
            work_queue=mock_work_queue,
            config=config,
            dry_run=True,
            enable_search_fallback=True,
            interactive_search=True,
            event_bus=event_bus,
        )

        # Create UI
        ui = CurateurUI(config, event_bus)
        ui.orchestrator = orchestrator

        # Subscribe UI to search requests
        event_bus.subscribe(SearchRequestEvent, ui.on_search_request)

        # Subscribe orchestrator to search responses
        event_bus.subscribe(SearchResponseEvent, orchestrator.handle_search_response)

        # Mock UI dialog to auto-select first result
        selected_result = {
            "name": "Super Mario Bros.",
            "confidence": 0.95,
            "_full_data": sample_search_results[0]["game_data"]
        }

        async def mock_push_screen_wait(dialog):
            return ("selected", selected_result)

        ui.push_screen_wait = mock_push_screen_wait

        # Start event processing
        event_task = asyncio.create_task(event_bus.process_events())

        # Start UI search processor (manually for test)
        processor_task = asyncio.create_task(ui._process_search_queue())

        # Simulate search fallback
        request_id = str(uuid.uuid4())
        scored_candidates = [
            (result["game_data"], result["confidence"])
            for result in sample_search_results
        ]

        # Call wait_for_search_response
        result_task = asyncio.create_task(
            orchestrator._wait_for_search_response(
                request_id, sample_rom_info, scored_candidates
            )
        )

        # Wait for result
        selected_game = await asyncio.wait_for(result_task, timeout=2.0)

        # Cleanup
        ui.should_quit = True
        await asyncio.sleep(0.5)  # Let processor exit
        await event_bus.stop()
        event_task.cancel()
        processor_task.cancel()

        # Verify result
        assert selected_game is not None
        assert selected_game["id"] == "12345"
        assert selected_game["names"]["en"] == "Super Mario Bros."

    @pytest.mark.asyncio
    async def test_multiple_search_requests_queued(
        self, config, event_bus, sample_search_results
    ):
        """Test that multiple search requests are queued and processed sequentially."""
        ui = CurateurUI(config, event_bus)

        # Track dialog displays
        displayed_requests = []

        async def mock_push_screen_wait(dialog):
            displayed_requests.append(dialog.rom_name)
            return ("skip", None)

        ui.push_screen_wait = mock_push_screen_wait

        # Create multiple requests
        requests = [
            SearchRequestEvent(
                request_id=f"test-{i}",
                rom_name=f"Test{i}.nes",
                rom_path=f"/test{i}.nes",
                system="nes",
                search_results=sample_search_results
            )
            for i in range(3)
        ]

        # Start event processing
        event_task = asyncio.create_task(event_bus.process_events())

        # Queue all requests
        for request in requests:
            await ui.on_search_request(request)

        # Start processor
        processor_task = asyncio.create_task(ui._process_search_queue())

        # Wait for all to be processed
        await asyncio.sleep(0.5)

        # Cleanup
        ui.should_quit = True
        await asyncio.sleep(0.5)
        await event_bus.stop()
        event_task.cancel()
        processor_task.cancel()

        # Verify all were displayed in order
        assert len(displayed_requests) == 3
        assert displayed_requests == ["Test0.nes", "Test1.nes", "Test2.nes"]
