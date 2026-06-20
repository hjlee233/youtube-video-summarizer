"""설정 로딩 (기획안 13절).

- 비밀 정보는 `.env` (OPENAI_API_KEY 등) — pydantic-settings로 로드
- 일반 설정은 `config.yaml` (없으면 config.example.yaml 또는 내장 기본값)

API 키는 UI/로그/결과에 절대 기록하지 않는다 (기획안 12절).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Paths(BaseModel):
    data_dir: Path = Path("data")
    temp_dir: Path = Path("data/temp")
    result_dir: Path = Path("data/results")

    def ensure(self) -> None:
        for p in (self.data_dir, self.temp_dir, self.result_dir):
            p.mkdir(parents=True, exist_ok=True)


class TranscriptionConfig(BaseModel):
    model: str = "medium"
    device: str = "auto"
    # auto | int8 | int8_float16 | float16 | float32
    # auto: GPU -> int8_float16, CPU -> int8 (기획안 8.5)
    compute_type: str = "auto"
    language: str = "auto"
    vad_filter: bool = True
    beam_size: int = 5


class SummaryConfig(BaseModel):
    provider: str = "openai_compatible"
    model: str = ""
    detail: str = "standard"
    chunk_chars: int = 7000
    max_retries: int = 3
    # 0 = 결정적(greedy). 충실 요약·재현성을 위해 기본 0.
    temperature: float = 0.0


class YoutubeConfig(BaseModel):
    # 로그인/비공개 영상용 쿠키를 가져올 기본 브라우저 ("" = 사용 안 함).
    # chrome | edge | firefox. CLI --cookies-from-browser가 우선한다.
    cookies_from_browser: str = ""
    # 멤버십/보호 영상의 JS 서명 챌린지를 풀기 위해 yt-dlp가 외부 JS 솔버
    # 스크립트(yt-dlp-ejs)를 GitHub에서 받아 Deno로 실행하도록 허용한다.
    # 외부 코드 다운로드·실행이므로 기본 False. Deno 설치 필요.
    allow_remote_components: bool = False


class DiarizationConfig(BaseModel):
    # 화자 분리 (pyannote.audio). 무거운 선택 기능이라 기본 False.
    # 사용하려면 `uv sync --extra diarization` + .env의 HF_TOKEN + 모델 라이선스 동의 필요.
    enabled: bool = False
    device: str = "auto"  # auto | cpu | cuda
    min_speakers: int | None = None
    max_speakers: int | None = None


class PrivacyConfig(BaseModel):
    keep_audio: bool = False
    # 요약 Markdown에 전체 대본 포함 여부. 기본 False (대본은 result.json에 보존).
    include_full_transcript: bool = False


class Secrets(BaseSettings):
    """`.env`에서 로드하는 비밀 정보."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="", alias="OPENAI_BASE_URL")
    hf_token: str = Field(default="", alias="HF_TOKEN")  # pyannote 화자 분리용


class Config(BaseModel):
    paths: Paths = Field(default_factory=Paths)
    transcription: TranscriptionConfig = Field(default_factory=TranscriptionConfig)
    summary: SummaryConfig = Field(default_factory=SummaryConfig)
    youtube: YoutubeConfig = Field(default_factory=YoutubeConfig)
    diarization: DiarizationConfig = Field(default_factory=DiarizationConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    secrets: Secrets = Field(default_factory=Secrets)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "Config":
        """config.yaml을 우선 사용하고, 없으면 example/내장 기본값으로 폴백."""
        candidates: list[Path] = []
        if config_path is not None:
            candidates.append(Path(config_path))
        candidates += [Path("config.yaml"), Path("config.example.yaml")]

        data: dict = {}
        for path in candidates:
            if path.is_file():
                with path.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                break

        # secrets는 yaml이 아니라 .env에서 로드
        data.pop("secrets", None)
        cfg = cls.model_validate(data)
        return cfg
