"""파이프라인 단계별 오류 정의.

각 단계에서 발생하는 예외를 명확히 구분해 CLI/UI가 사용자에게
적절한 메시지를 보여주고 재시도 가능 여부를 판단할 수 있게 한다.
"""

from __future__ import annotations


class TubeNoteError(Exception):
    """모든 TubeNote 오류의 기본 클래스."""

    #: 사용자에게 보여줄 한국어 메시지
    user_message: str = "처리 중 오류가 발생했습니다."

    def __init__(self, message: str | None = None, *, user_message: str | None = None):
        super().__init__(message or self.user_message)
        if user_message is not None:
            self.user_message = user_message
        elif message is not None and type(self).user_message == TubeNoteError.user_message:
            self.user_message = message


class InvalidURLError(TubeNoteError):
    """지원하지 않거나 영상 ID를 추출할 수 없는 URL."""

    user_message = "지원하지 않는 YouTube 주소입니다."


class LiveVideoError(TubeNoteError):
    """생방송 중인 영상은 처리하지 않는다."""

    user_message = "생방송 중인 영상은 처리할 수 없습니다. 방송 종료 후 다시 시도하세요."


class MetadataError(TubeNoteError):
    """yt-dlp 메타데이터 조회 실패 (비공개/삭제/네트워크 등)."""

    user_message = "영상 정보를 가져오지 못했습니다."


class DownloadError(TubeNoteError):
    """오디오 다운로드 실패."""

    user_message = "오디오 다운로드에 실패했습니다."


class FFmpegNotFoundError(TubeNoteError):
    """FFmpeg 실행 파일을 찾을 수 없음."""

    user_message = "FFmpeg 설치 또는 경로 설정이 필요합니다."


class AudioProcessingError(TubeNoteError):
    """FFmpeg 전처리(WAV 변환) 실패."""

    user_message = "오디오 전처리에 실패했습니다."


class TranscriptionError(TubeNoteError):
    """음성 인식(STT) 실패."""

    user_message = "음성 인식 단계에서 실패했습니다."


class SummaryNotConfiguredError(TubeNoteError):
    """요약 제공자/모델/키 등이 설정되지 않음 — 대본까지만 저장한다."""

    user_message = "요약 API 설정이 필요합니다. 대본까지만 저장합니다."


class SummaryError(TubeNoteError):
    """LLM 요약 호출 실패."""

    user_message = "요약 호출에 실패했습니다."
