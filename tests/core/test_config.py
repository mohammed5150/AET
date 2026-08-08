"""Tests for configuration resolution (SDS-002 §6.1, §12.2)."""

import os
from pathlib import Path

import pytest

from app.core.config import PLUGIN_API_VERSION, AppConfig
from app.core.errors import InfrastructureError


def test_defaults_match_the_documented_layout():
    config = AppConfig()
    assert config.data_dir == Path("output")
    assert config.log_dir == Path("logs")
    assert config.log_level == "INFO"
    assert config.plugin_dirs == ()
    assert config.plugin_api_version == PLUGIN_API_VERSION


def test_from_mapping_rejects_unknown_keys():
    with pytest.raises(InfrastructureError) as raised:
        AppConfig.from_mapping({"log_level": "DEBUG", "colour": "blue"})
    assert "colour" in str(raised.value)
    assert raised.value.code == "INFRASTRUCTURE_ERROR"
    assert raised.value.remediation


def test_invalid_log_level_fails_eagerly():
    with pytest.raises(InfrastructureError) as raised:
        AppConfig(log_level="CHATTY")
    assert "CHATTY" in str(raised.value)
    assert "TRACE" in (raised.value.remediation or "")


def test_custom_levels_are_accepted():
    assert AppConfig(log_level="TRACE").log_level == "TRACE"
    assert AppConfig(log_level="FATAL").log_level == "FATAL"


def test_from_env_reads_prefixed_variables():
    config = AppConfig.from_env(
        {
            "AET_DATA_DIR": "/srv/artifacts",
            "AET_LOG_DIR": "/var/log/aet",
            "AET_LOG_LEVEL": "debug",
            "AET_PLUGIN_DIRS": os.pathsep.join(["/opt/a", "/opt/b"]),
            "UNRELATED": "ignored",
        }
    )
    assert config.data_dir == Path("/srv/artifacts")
    assert config.log_dir == Path("/var/log/aet")
    assert config.log_level == "DEBUG"
    assert config.plugin_dirs == (Path("/opt/a"), Path("/opt/b"))


def test_from_env_falls_back_to_defaults():
    assert AppConfig.from_env({}) == AppConfig()


def test_with_overrides_ignores_unsupplied_values():
    base = AppConfig.from_env({"AET_LOG_LEVEL": "DEBUG"})
    overridden = base.with_overrides(log_level=None, data_dir=Path("/tmp/out"))
    assert overridden.log_level == "DEBUG"
    assert overridden.data_dir == Path("/tmp/out")
    assert base.data_dir == Path("output")


def test_with_overrides_rejects_unknown_keys():
    with pytest.raises(InfrastructureError):
        AppConfig().with_overrides(colour="blue")


def test_with_overrides_validates_the_result():
    with pytest.raises(InfrastructureError):
        AppConfig().with_overrides(log_level="CHATTY")
