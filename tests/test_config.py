"""Protect the documented empty-storage default and class-only port routing."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from ai_jukebox import config, http


def test_blank_storage_uses_gitignored_data_directory():
    env = dict(os.environ, AIJ_DATA_DIR='')
    result = subprocess.check_output(
        [sys.executable, '-c', 'import json; from ai_jukebox import config; print(json.dumps(config.DATA_DIR))'],
        env=env, text=True,
    )
    assert Path(json.loads(result)) == Path(config.__file__).resolve().parents[1] / 'data'


def test_reserved_agent_port_is_rejected():
    with pytest.raises(ValueError, match='reserved'):
        config.base_url('9000')


def test_example_key_is_rejected_before_network_request(monkeypatch):
    monkeypatch.setattr(config, 'API_KEY', '<your-class-key>')
    with pytest.raises(http.ServiceError, match='AIJ_API_KEY'):
        http._headers()
