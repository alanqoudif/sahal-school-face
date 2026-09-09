import pytest

from app.cameras import validate_camera_host, validate_camera_url


def test_rejects_metadata_url():
    with pytest.raises(ValueError):
        validate_camera_url("http://169.254.169.254/latest/meta-data")


def test_rejects_file_scheme():
    with pytest.raises(ValueError):
        validate_camera_url("file:///etc/passwd")


def test_accepts_lan_snapshot():
    assert validate_camera_url("http://192.168.1.20/cgi-bin/snapshot.cgi").startswith("http://")


def test_rejects_slash_in_ip():
    with pytest.raises(ValueError):
        validate_camera_host("127.0.0.1/cgi-bin")
