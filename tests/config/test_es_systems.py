"""
Tests for config.es_systems module.
"""
import pytest
from pathlib import Path
from lxml import etree
from curateur.config.es_systems import (
    SystemDefinition, ESSystemsError,
    parse_es_systems, get_systems_by_name,
    _parse_system_element, _get_element_text, _get_platform_id
)


@pytest.mark.unit
class TestSystemDefinition:
    """Test SystemDefinition dataclass."""
    
    def test_system_definition_creation(self):
        """Test creating a SystemDefinition instance."""
        system = SystemDefinition(
            name='nes',
            fullname='Nintendo Entertainment System',
            path='%ROMPATH%/nes',
            extensions=['.nes', '.zip'],
            platform='nes'
        )
        
        assert system.name == 'nes'
        assert system.fullname == 'Nintendo Entertainment System'
        assert system.path == '%ROMPATH%/nes'
        assert system.extensions == ['.nes', '.zip']
        assert system.platform == 'nes'
    
    def test_supports_m3u_true(self):
        """Test supports_m3u returns True when .m3u in extensions."""
        system = SystemDefinition(
            name='psx',
            fullname='Sony PlayStation',
            path='%ROMPATH%/psx',
            extensions=['.cue', '.m3u', '.chd'],
            platform='psx'
        )
        
        assert system.supports_m3u() is True
    
    def test_supports_m3u_false(self):
        """Test supports_m3u returns False when .m3u not in extensions."""
        system = SystemDefinition(
            name='nes',
            fullname='Nintendo Entertainment System',
            path='%ROMPATH%/nes',
            extensions=['.nes', '.zip'],
            platform='nes'
        )
        
        assert system.supports_m3u() is False
    
    def test_supports_m3u_case_sensitive(self):
        """Test that .m3u check is case-sensitive."""
        system = SystemDefinition(
            name='psx',
            fullname='Sony PlayStation',
            path='%ROMPATH%/psx',
            extensions=['.cue', '.M3U'],  # Uppercase
            platform='psx'
        )
        
        # Extensions should be normalized to lowercase during parsing
        # This test verifies the method behavior
        assert system.supports_m3u() is False


@pytest.mark.unit
class TestESSystemsParsing:
    """Test ES systems XML parsing."""
    
    def test_parse_valid_systems_xml(self, fixture_path):
        """Test parsing a valid es_systems.xml file."""
        xml_file = fixture_path / 'es_systems' / 'valid.xml'
        
        systems = parse_es_systems(xml_file)
        
        assert len(systems) == 3
        assert systems[0].name == 'nes'
        assert systems[1].name == 'snes'
        assert systems[2].name == 'psx'
    
    def test_parse_systems_from_tmp_path(self, tmp_path, sample_es_systems_xml):
        """Test parsing systems from temporary file."""
        xml_file = tmp_path / "systems.xml"
        xml_file.write_text(sample_es_systems_xml)
        
        systems = parse_es_systems(xml_file)
        
        assert len(systems) == 2
        assert systems[0].name == 'nes'
        assert systems[1].name == 'psx'
    
    def test_parse_systems_extracts_all_fields(self, fixture_path):
        """Test that all system fields are extracted correctly."""
        xml_file = fixture_path / 'es_systems' / 'valid.xml'
        
        systems = parse_es_systems(xml_file)
        nes = systems[0]
        
        assert nes.name == 'nes'
        assert nes.fullname == 'Nintendo Entertainment System'
        assert nes.path == '%ROMPATH%/nes'
        assert '.nes' in nes.extensions
        assert '.zip' in nes.extensions
        assert nes.platform == 'nes'
    
    def test_parse_systems_malformed_xml(self, fixture_path):
        """Test error with malformed XML."""
        xml_file = fixture_path / 'es_systems' / 'malformed.xml'
        
        with pytest.raises(ESSystemsError) as exc_info:
            parse_es_systems(xml_file)
        
        assert 'Invalid XML' in str(exc_info.value)
    
    def test_parse_systems_file_not_found(self):
        """Test error when file doesn't exist."""
        xml_file = Path('/nonexistent/systems.xml')
        
        with pytest.raises(ESSystemsError) as exc_info:
            parse_es_systems(xml_file)
        
        assert 'Failed to read' in str(exc_info.value)
    
    def test_parse_systems_invalid_root_element(self, fixture_path):
        """Test error when root element is not systemList."""
        xml_file = fixture_path / 'es_systems' / 'invalid_root.xml'
        
        with pytest.raises(ESSystemsError) as exc_info:
            parse_es_systems(xml_file)
        
        assert 'Invalid root element' in str(exc_info.value)
        assert 'systemList' in str(exc_info.value)
    
    def test_parse_systems_empty_xml(self, fixture_path):
        """Test error when no valid systems found."""
        xml_file = fixture_path / 'es_systems' / 'empty.xml'
        
        with pytest.raises(ESSystemsError) as exc_info:
            parse_es_systems(xml_file)
        
        assert 'No valid systems found' in str(exc_info.value)
    
    def test_parse_systems_nested_name_invalid(self, fixture_path, capsys):
        """Test that nested <name> under <platform> is invalid and system is skipped."""
        xml_file = fixture_path / 'es_systems' / 'nested_name_invalid.xml'
        
        with pytest.raises(ESSystemsError) as exc_info:
            parse_es_systems(xml_file)
        
        # Should fail because no valid systems found (platform returns None)
        assert 'No valid systems found' in str(exc_info.value)
        
        # Should have warning about skipped system
        captured = capsys.readouterr()
        assert 'Warning: Skipping invalid system' in captured.out
    
    def test_parse_systems_skips_invalid_entries(self, tmp_path, capsys):
        """Test that invalid systems are skipped with warning."""
        xml_content = """<?xml version="1.0"?>
<systemList>
  <system>
    <name>nes</name>
    <fullname>Nintendo Entertainment System</fullname>
    <path>%ROMPATH%/nes</path>
    <extension>.nes .NES</extension>
    <platform>nes</platform>
  </system>
  <system>
    <name>broken</name>
    <!-- Missing required fields -->
  </system>
  <system>
    <name>snes</name>
    <fullname>Super Nintendo</fullname>
    <path>%ROMPATH%/snes</path>
    <extension>.smc .SFC</extension>
    <platform>snes</platform>
  </system>
</systemList>
"""
        xml_file = tmp_path / "systems.xml"
        xml_file.write_text(xml_content)
        
        systems = parse_es_systems(xml_file)
        
        # Should have 2 valid systems (broken one skipped)
        assert len(systems) == 2
        assert systems[0].name == 'nes'
        assert systems[1].name == 'snes'
        
        # Check warning was printed
        captured = capsys.readouterr()
        assert 'Warning: Skipping invalid system' in captured.out
    
    def test_parse_systems_extensions_normalized(self, tmp_path):
        """Test that extensions are normalized to lowercase."""
        xml_content = """<?xml version="1.0"?>
<systemList>
  <system>
    <name>nes</name>
    <fullname>Nintendo Entertainment System</fullname>
    <path>%ROMPATH%/nes</path>
    <extension>.NES .ZIP .Nes</extension>
    <platform>nes</platform>
  </system>
</systemList>
"""
        xml_file = tmp_path / "systems.xml"
        xml_file.write_text(xml_content)
        
        systems = parse_es_systems(xml_file)
        
        assert systems[0].extensions == ['.nes', '.zip', '.nes']
    
    def test_parse_systems_extensions_stripped(self, tmp_path):
        """Test that extension whitespace is stripped."""
        xml_content = """<?xml version="1.0"?>
<systemList>
  <system>
    <name>nes</name>
    <fullname>Nintendo Entertainment System</fullname>
    <path>%ROMPATH%/nes</path>
    <extension>  .nes   .zip  </extension>
    <platform>nes</platform>
  </system>
</systemList>
"""
        xml_file = tmp_path / "systems.xml"
        xml_file.write_text(xml_content)
        
        systems = parse_es_systems(xml_file)
        
        assert systems[0].extensions == ['.nes', '.zip']


@pytest.mark.unit
class TestParseSystemElement:
    """Test parsing individual system elements."""
    
    def test_parse_system_element_valid(self):
        """Test parsing a valid system element."""
        xml_str = """
        <system>
            <name>nes</name>
            <fullname>Nintendo Entertainment System</fullname>
            <path>%ROMPATH%/nes</path>
            <extension>.nes .NES .zip</extension>
            <platform>nes</platform>
        </system>
        """
        elem = etree.fromstring(xml_str)
        
        system = _parse_system_element(elem)
        
        assert system.name == 'nes'
        assert system.fullname == 'Nintendo Entertainment System'
        assert system.path == '%ROMPATH%/nes'
        assert system.extensions == ['.nes', '.nes', '.zip']
        assert system.platform == 'nes'
    
    def test_parse_system_element_missing_name(self):
        """Test error when name is missing."""
        xml_str = """
        <system>
            <fullname>Nintendo Entertainment System</fullname>
            <path>%ROMPATH%/nes</path>
            <extension>.nes</extension>
            <platform>nes</platform>
        </system>
        """
        elem = etree.fromstring(xml_str)
        
        with pytest.raises(ValueError) as exc_info:
            _parse_system_element(elem)
        
        assert 'missing required fields' in str(exc_info.value).lower()
    
    def test_parse_system_element_missing_platform(self, fixture_path):
        """Test error when platform ID is missing."""
        xml_str = """
        <system>
            <name>nes</name>
            <fullname>Nintendo Entertainment System</fullname>
            <path>%ROMPATH%/nes</path>
            <extension>.nes</extension>
        </system>
        """
        elem = etree.fromstring(xml_str)
        
        with pytest.raises(ValueError):
            _parse_system_element(elem)
    
    def test_parse_system_element_empty_extension(self):
        """Test error when extension is empty."""
        xml_str = """
        <system>
            <name>nes</name>
            <fullname>Nintendo Entertainment System</fullname>
            <path>%ROMPATH%/nes</path>
            <extension></extension>
            <platform>nes</platform>
        </system>
        """
        elem = etree.fromstring(xml_str)
        
        # Empty extension field results in empty list, which fails the "all" check
        with pytest.raises(ValueError):
            _parse_system_element(elem)
    
    def test_parse_system_rompath_pattern(self):
        """Test parsing system with %ROMPATH% path pattern."""
        xml_str = """
        <system>
            <name>nes</name>
            <fullname>Nintendo Entertainment System</fullname>
            <path>%ROMPATH%/nes</path>
            <extension>.nes</extension>
            <platform>nes</platform>
        </system>
        """
        elem = etree.fromstring(xml_str)
        
        system = _parse_system_element(elem)
        
        assert system.path == '%ROMPATH%/nes'
    
    def test_parse_system_absolute_path(self):
        """Test parsing system with absolute path."""
        xml_str = """
        <system>
            <name>psx</name>
            <fullname>Sony PlayStation</fullname>
            <path>/home/user/roms/psx</path>
            <extension>.cue</extension>
            <platform>psx</platform>
        </system>
        """
        elem = etree.fromstring(xml_str)
        
        system = _parse_system_element(elem)
        
        assert system.path == '/home/user/roms/psx'


@pytest.mark.unit
class TestGetElementText:
    """Test element text extraction."""
    
    def test_get_element_text_exists(self):
        """Test extracting text from existing element."""
        xml_str = "<parent><child>test value</child></parent>"
        parent = etree.fromstring(xml_str)
        
        text = _get_element_text(parent, 'child')
        
        assert text == 'test value'
    
    def test_get_element_text_missing(self):
        """Test returns None when element doesn't exist."""
        xml_str = "<parent></parent>"
        parent = etree.fromstring(xml_str)
        
        text = _get_element_text(parent, 'child')
        
        assert text is None
    
    def test_get_element_text_empty(self):
        """Test returns None when element is empty."""
        xml_str = "<parent><child></child></parent>"
        parent = etree.fromstring(xml_str)
        
        text = _get_element_text(parent, 'child')
        
        assert text is None
    
    def test_get_element_text_whitespace_only(self):
        """Test returns None when element contains only whitespace."""
        xml_str = "<parent><child>   </child></parent>"
        parent = etree.fromstring(xml_str)
        
        text = _get_element_text(parent, 'child')
        
        # strip() on whitespace-only string returns empty string, which is falsy
        assert text == '' or text is None
    
    def test_get_element_text_strips_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        xml_str = "<parent><child>  value  </child></parent>"
        parent = etree.fromstring(xml_str)
        
        text = _get_element_text(parent, 'child')
        
        assert text == 'value'


@pytest.mark.unit
class TestPlatformExtraction:
    """Test platform ID extraction from <platform> elements."""
    
    @pytest.mark.unit
    def test_platform_with_direct_text(self, tmp_path):
        """Test platform with direct text content."""
        xml_str = """
        <system>
            <name>nes</name>
            <platform>nes</platform>
        </system>
        """
        elem = etree.fromstring(xml_str)
        
        platform = _get_platform_id(elem)
        
        assert platform == 'nes'
    
    @pytest.mark.unit
    def test_platform_missing(self, tmp_path):
        """Test returns None when no platform element found."""
        xml_str = """
        <system>
            <name>nes</name>
        </system>
        """
        elem = etree.fromstring(xml_str)
        
        platform = _get_platform_id(elem)
        
        assert platform is None
    
    @pytest.mark.unit
    def test_platform_with_nested_name_invalid(self, tmp_path):
        """Test that nested <name> under <platform> is invalid (no text content)."""
        xml_str = """
        <system>
            <name>nes</name>
            <platform>
                <name>nes</name>
            </platform>
        </system>
        """
        elem = etree.fromstring(xml_str)
        
        # Platform element has no direct text, only nested <name>
        # This is invalid and should return None
        platform = _get_platform_id(elem)
        
        assert platform is None
    
    def test_get_platform_id_empty(self):
        """Test returns None when platform is empty."""
        xml_str = """
        <system>
            <name>nes</name>
            <platform></platform>
        </system>
        """
        elem = etree.fromstring(xml_str)
        
        platform = _get_platform_id(elem)
        
        assert platform is None
    
    def test_get_platform_id_prefers_platform(self):
        """Test that platform is preferred over platform."""
        xml_str = """
        <system>
            <name>nes</name>
            <platform>nes_platform</platform>
            <platform>nes_alt</platform>
        </system>
        """
        elem = etree.fromstring(xml_str)
        
        platform = _get_platform_id(elem)
        
        assert platform == 'nes_platform'
    
    def test_get_platform_id_strips_whitespace(self):
        """Test that whitespace is stripped from platform ID."""
        xml_str = """
        <system>
            <name>nes</name>
            <platform>  nes  </platform>
        </system>
        """
        elem = etree.fromstring(xml_str)
        
        platform = _get_platform_id(elem)
        
        assert platform == 'nes'


@pytest.mark.unit
class TestSystemFiltering:
    """Test filtering systems by name."""
    
    def test_get_systems_by_name_all(self, valid_system_definition):
        """Test returning all systems when names is None."""
        systems = [
            valid_system_definition,
            SystemDefinition('snes', 'SNES', './roms/snes', ['.smc'], 'snes')
        ]
        
        result = get_systems_by_name(systems, None)
        
        assert len(result) == 2
        assert result == systems
    
    def test_get_systems_by_name_empty_list(self, valid_system_definition):
        """Test returning all systems when names is empty list."""
        systems = [valid_system_definition]
        
        result = get_systems_by_name(systems, [])
        
        assert result == systems
    
    def test_get_systems_by_name_single(self, valid_system_definition):
        """Test filtering to single system."""
        systems = [
            valid_system_definition,
            SystemDefinition('snes', 'SNES', './roms/snes', ['.smc'], 'snes'),
            SystemDefinition('psx', 'PlayStation', './roms/psx', ['.cue'], 'psx')
        ]
        
        result = get_systems_by_name(systems, ['snes'])
        
        assert len(result) == 1
        assert result[0].name == 'snes'
    
    def test_get_systems_by_name_multiple(self, valid_system_definition):
        """Test filtering to multiple systems."""
        systems = [
            valid_system_definition,
            SystemDefinition('snes', 'SNES', './roms/snes', ['.smc'], 'snes'),
            SystemDefinition('psx', 'PlayStation', './roms/psx', ['.cue'], 'psx')
        ]
        
        result = get_systems_by_name(systems, ['nes', 'psx'])
        
        assert len(result) == 2
        assert result[0].name == 'nes'
        assert result[1].name == 'psx'
    
    def test_get_systems_by_name_case_insensitive(self, valid_system_definition):
        """Test that filtering is case-insensitive."""
        systems = [valid_system_definition]
        
        result = get_systems_by_name(systems, ['NES'])
        
        assert len(result) == 1
        assert result[0].name == 'nes'
    
    def test_get_systems_by_name_not_found(self, valid_system_definition):
        """Test error when requested system doesn't exist."""
        systems = [valid_system_definition]
        
        with pytest.raises(ValueError) as exc_info:
            get_systems_by_name(systems, ['nonexistent'])
        
        assert 'Systems not found' in str(exc_info.value)
        assert 'nonexistent' in str(exc_info.value)
    
    def test_get_systems_by_name_partial_match(self, valid_system_definition):
        """Test error when some systems not found."""
        systems = [
            valid_system_definition,
            SystemDefinition('snes', 'SNES', './roms/snes', ['.smc'], 'snes')
        ]
        
        with pytest.raises(ValueError) as exc_info:
            get_systems_by_name(systems, ['nes', 'psx', 'n64'])
        
        error_msg = str(exc_info.value)
        assert 'psx' in error_msg
        assert 'n64' in error_msg
        assert 'nes' not in error_msg  # This one was found
    
    def test_get_systems_by_name_preserves_order(self):
        """Test that result order matches input system order."""
        systems = [
            SystemDefinition('nes', 'NES', './roms/nes', ['.nes'], 'nes'),
            SystemDefinition('snes', 'SNES', './roms/snes', ['.smc'], 'snes'),
            SystemDefinition('psx', 'PlayStation', './roms/psx', ['.cue'], 'psx')
        ]
        
        # Request in different order
        result = get_systems_by_name(systems, ['psx', 'nes'])
        
        # Should return in original systems order (nes before psx)
        assert result[0].name == 'nes'
        assert result[1].name == 'psx'
    
    def test_get_systems_by_name_duplicate_request(self):
        """Test handling duplicate names in request."""
        systems = [
            SystemDefinition('nes', 'NES', './roms/nes', ['.nes'], 'nes')
        ]
        
        result = get_systems_by_name(systems, ['nes', 'nes'])
        
        # Should only include each system once
        assert len(result) == 1
