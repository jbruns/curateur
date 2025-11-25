import pytest

from curateur.api.obfuscator import obfuscate, deobfuscate
from curateur.api import credentials


@pytest.mark.unit
def test_obfuscate_round_trip():
    secret = "supersecret"
    obf = obfuscate(secret)
    assert secret != obf.decode("latin1")  # not plaintext
    assert deobfuscate(obf) == secret


@pytest.mark.unit
def test_credentials_error_when_uninitialized(monkeypatch):
    monkeypatch.setattr(credentials, "_DEV_ID_OBFUSCATED", bytearray())
    monkeypatch.setattr(credentials, "_DEV_PASSWORD_OBFUSCATED", bytearray())
    with pytest.raises(ValueError):
        credentials.get_dev_credentials()
