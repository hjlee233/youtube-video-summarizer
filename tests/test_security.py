"""보안 유틸 단위 테스트 (기획안 12절)."""

from pathlib import Path

from tubenote.config import Config
from tubenote.security import (
    REDACTED,
    cloud_transfer_notice,
    mask_text,
    secret_values,
    summary_destination,
)
from tubenote.storage import clear_temp


def _config(provider="openai_compatible", base_url="", api_key="sk-secret-1234567890"):
    c = Config()
    c.summary.provider = provider
    c.secrets.openai_base_url = base_url
    c.secrets.openai_api_key = api_key
    return c


def test_mask_text_redacts_secret():
    out = mask_text("Authorization: Bearer sk-secret-1234567890 failed", "sk-secret-1234567890")
    assert "sk-secret-1234567890" not in out
    assert REDACTED in out


def test_mask_text_ignores_short_and_empty():
    assert mask_text("abc def", "", "ab") == "abc def"  # 빈 값/4자 미만 무시
    assert mask_text(None) == ""


def test_secret_values():
    c = _config(api_key="sk-xyz12345")
    assert "sk-xyz12345" in secret_values(c)
    c2 = _config(api_key="")
    assert secret_values(c2) == []


def test_summary_destination_openai_cloud():
    c = _config(base_url="")  # 기본 OpenAI
    assert summary_destination(c) == ("cloud", "api.openai.com")


def test_summary_destination_local_base_url():
    c = _config(base_url="http://localhost:8000/v1")
    kind, host = summary_destination(c)
    assert kind == "local" and host == "localhost"


def test_summary_destination_remote_base_url():
    c = _config(base_url="https://api.example.com/v1")
    kind, host = summary_destination(c)
    assert kind == "cloud" and host == "api.example.com"


def test_summary_destination_ollama_is_local():
    c = _config(provider="ollama")
    assert summary_destination(c)[0] == "local"


def test_cloud_transfer_notice():
    assert cloud_transfer_notice(_config(base_url="")) is not None  # 클라우드
    assert cloud_transfer_notice(_config(base_url="http://localhost:8000/v1")) is None
    assert cloud_transfer_notice(_config(provider="ollama")) is None


def test_clear_temp(tmp_path: Path):
    temp = tmp_path / "temp"
    temp.mkdir()
    (temp / "a.wav").write_bytes(b"x" * 100)
    (temp / "b.m4a").write_bytes(b"y" * 50)
    sub = temp / "keep_dir"
    sub.mkdir()  # 디렉터리는 건드리지 않음

    count, freed = clear_temp(temp)
    assert count == 2
    assert freed == 150
    assert temp.is_dir()  # 폴더 자체는 유지
    assert sub.is_dir()
    assert not (temp / "a.wav").exists()


def test_clear_temp_missing_dir(tmp_path: Path):
    assert clear_temp(tmp_path / "nope") == (0, 0)
