"""개인정보·보안 유틸 (기획안 12절).

- 민감 정보(API 키) 마스킹: 로그/오류 메시지에 키가 노출되지 않게 한다.
- 요약 전송 목적지 판별: 클라우드 LLM 사용 시 대본 전송 안내를 위해 사용.
"""

from __future__ import annotations

from urllib.parse import urlparse

REDACTED = "***REDACTED***"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def mask_text(text: object, *secrets: str) -> str:
    """text 안의 secret 값들을 마스킹한다. 4자 미만 비밀은 무시(오탐 방지)."""
    out = str(text) if text is not None else ""
    for s in secrets:
        if s and len(s) >= 4:
            out = out.replace(s, REDACTED)
    return out


def secret_values(config) -> list[str]:
    """마스킹 대상 비밀 값 목록 (현재는 API 키)."""
    return [v for v in (config.secrets.openai_api_key,) if v]


def summary_destination(config) -> tuple[str, str]:
    """요약 호출이 향하는 곳을 ("local"|"cloud", host)로 반환.

    - ollama: 로컬
    - openai_compatible: base_url 비어 있으면 OpenAI 클라우드,
      localhost류면 로컬, 그 외 호스트면 클라우드로 본다.
    """
    if config.summary.provider == "ollama":
        base = config.secrets.openai_base_url or "http://localhost:11434"
        host = urlparse(base if "://" in base else "http://" + base).hostname or "localhost"
        return ("local", host)

    base = (config.secrets.openai_base_url or "").strip()
    if not base:
        return ("cloud", "api.openai.com")
    host = urlparse(base if "://" in base else "http://" + base).hostname or base
    if host in _LOCAL_HOSTS:
        return ("local", host)
    return ("cloud", host)


def cloud_transfer_notice(config) -> str | None:
    """클라우드 요약이면 대본 전송 안내 문구를, 로컬이면 None을 반환."""
    kind, host = summary_destination(config)
    if kind == "cloud":
        return (
            f"클라우드 LLM 사용: 요약을 위해 대본이 {host}(으)로 전송됩니다. "
            "완전 로컬 처리가 필요하면 Ollama 또는 로컬 서버를 사용하세요."
        )
    return None
