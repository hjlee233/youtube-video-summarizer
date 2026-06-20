"""파일 기반 JSON 저장 (기획안 5절: 단일 사용자 MVP에 DB 불필요)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .models import Job, Result


def _write_json(path: Path, model: BaseModel) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(model.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    return path


def result_dir_for(result_root: Path, video_id: str) -> Path:
    return result_root / video_id


def save_result(result_root: Path, result: Result) -> Path:
    """영상 ID별 디렉터리에 result.json 저장."""
    out_dir = result_dir_for(result_root, result.metadata.video_id)
    return _write_json(out_dir / "result.json", result)


def save_job(jobs_root: Path, job: Job) -> Path:
    """job_id별 상태 파일 저장 (재개에 활용)."""
    return _write_json(jobs_root / f"{job.job_id}.json", job)


def save_markdown(result_root: Path, video_id: str, markdown: str) -> Path:
    """영상 ID별 디렉터리에 summary.md 저장."""
    out_dir = result_dir_for(result_root, video_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "summary.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def clear_temp(temp_dir: Path) -> tuple[int, int]:
    """임시 폴더의 파일을 일괄 삭제한다 (기획안 12절).

    반환: (삭제한 파일 수, 확보한 바이트). 폴더 자체는 유지한다.
    """
    if not temp_dir.is_dir():
        return (0, 0)
    count = 0
    freed = 0
    for p in temp_dir.iterdir():
        if p.is_file():
            try:
                size = p.stat().st_size
                p.unlink()
                count += 1
                freed += size
            except OSError:
                pass
    return (count, freed)


def load_result(result_root: Path, video_id: str) -> Result | None:
    """동일 영상 재처리 시 기존 결과 감지 (기획안 4절)."""
    path = result_dir_for(result_root, video_id) / "result.json"
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as f:
        return Result.model_validate(json.load(f))
