"""CLI 진입점.

다운로드 → STT → 청크 분할 → LLM 요약 → Markdown/JSON 저장 파이프라인을 실행한다.
`--clean-temp`로 임시 폴더만 비울 수도 있다.

    uv run python -m tubenote.cli "<YOUTUBE_URL>"
또는
    uv run tubenote "<YOUTUBE_URL>"
"""

from __future__ import annotations

import argparse
import sys

from . import security, storage
from .config import Config
from .errors import TubeNoteError
from .pipeline import run_transcription_pipeline


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tubenote",
        description="YouTube 영상을 대본화하고 AI로 요약해 Markdown/JSON으로 저장합니다.",
    )
    parser.add_argument("url", nargs="?", help="YouTube 영상 URL")
    parser.add_argument("--config", help="config.yaml 경로", default=None)
    parser.add_argument(
        "--clean-temp",
        action="store_true",
        help="임시 폴더(data/temp)의 파일을 모두 삭제하고 종료합니다.",
    )
    parser.add_argument(
        "--model",
        help="STT 모델 (small | medium | large-v3). 설정값을 덮어씁니다.",
        default=None,
    )
    parser.add_argument(
        "--language",
        help="영상 언어 (auto | ko | en | ja). 설정값을 덮어씁니다.",
        default=None,
    )
    parser.add_argument(
        "--device",
        help="실행 장치 (auto | cpu | cuda). 설정값을 덮어씁니다.",
        default=None,
    )
    parser.add_argument(
        "--compute-type",
        help="연산 정밀도 (auto | int8 | int8_float16 | float16 | float32). 설정값을 덮어씁니다.",
        default=None,
    )
    parser.add_argument(
        "--cookies-from-browser",
        help="로그인 영상용 브라우저 (chrome | edge | firefox).",
        default=None,
    )
    parser.add_argument(
        "--allow-remote-components",
        action="store_true",
        help="멤버십/보호 영상의 JS 챌린지 해석을 위해 yt-dlp가 외부 JS 솔버(yt-dlp-ejs)를 "
        "GitHub에서 받아 Deno로 실행하도록 허용합니다 (Deno 설치 필요).",
    )
    parser.add_argument(
        "--keep-audio",
        action="store_true",
        help="처리 후 임시 오디오를 삭제하지 않습니다.",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="LLM 요약을 건너뛰고 대본만 생성합니다.",
    )
    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="기존 결과(캐시)를 무시하고 다운로드·STT부터 강제로 다시 처리합니다.",
    )
    parser.add_argument(
        "--provider",
        help="요약 제공자 (openai_compatible | ollama). 설정값을 덮어씁니다.",
        default=None,
    )
    parser.add_argument(
        "--summary-model",
        help="요약 LLM 모델명. 설정값을 덮어씁니다.",
        default=None,
    )
    parser.add_argument(
        "--detail",
        help="요약 상세도 (simple | standard | detailed). 설정값을 덮어씁니다.",
        default=None,
    )
    return parser


def _log(step: str, message: str) -> None:
    print(f"[{step}] {message}", flush=True)


def _force_utf8_output() -> None:
    """Windows 콘솔/파이프에서 한국어 출력 시 UnicodeEncodeError 방지."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):  # pragma: no cover
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = _build_parser().parse_args(argv)

    config = Config.load(args.config)

    # 임시 폴더 정리 모드 (기획안 12절)
    if args.clean_temp:
        count, freed = storage.clear_temp(config.paths.temp_dir)
        print(f"임시 파일 {count}개 삭제, {freed / 1024 / 1024:.1f} MB 확보 ({config.paths.temp_dir})")
        return 0

    if not args.url:
        print("오류: URL을 입력하거나 --clean-temp를 사용하세요.", file=sys.stderr)
        return 2

    if args.model:
        config.transcription.model = args.model
    if args.language:
        config.transcription.language = args.language
    if args.device:
        config.transcription.device = args.device
    if args.compute_type:
        config.transcription.compute_type = args.compute_type
    if args.keep_audio:
        config.privacy.keep_audio = True
    if args.provider:
        config.summary.provider = args.provider
    if args.summary_model:
        config.summary.model = args.summary_model
    if args.detail:
        config.summary.detail = args.detail
    if args.allow_remote_components:
        config.youtube.allow_remote_components = True

    # --cookies-from-browser가 우선, 없으면 config의 기본 브라우저 사용
    cookies = args.cookies_from_browser or config.youtube.cookies_from_browser or None

    try:
        outcome = run_transcription_pipeline(
            args.url,
            config,
            cookies_from_browser=cookies,
            summarize_enabled=not args.no_summary,
            force_reprocess=args.reprocess,
            log=_log,
        )
    except TubeNoteError as exc:
        secrets = security.secret_values(config)
        print(f"\n오류: {exc.user_message}", file=sys.stderr)
        if str(exc) != exc.user_message:
            print(f"상세: {security.mask_text(exc, *secrets)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("\n사용자에 의해 중단되었습니다.", file=sys.stderr)
        return 130

    print(f"\n완료: {outcome.result_path}")
    if outcome.from_cache:
        print("(기존 대본 재사용 — 다운로드·STT 건너뜀)")
    print(f"세그먼트 {len(outcome.result.transcript)}개")
    if outcome.markdown_path is not None:
        print(f"Markdown: {outcome.markdown_path}")
    print("요약: 생성됨" if outcome.summarized else "요약: 건너뜀 (대본만)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
