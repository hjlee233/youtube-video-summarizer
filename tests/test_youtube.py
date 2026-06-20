"""URL 파싱과 타임스탬프 링크 단위 테스트 (기획안 17절)."""

import pytest

from tubenote.errors import InvalidURLError
from tubenote.youtube import extract_video_id, timestamp_url

VIDEO_ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtube.com/watch?v={VIDEO_ID}",
        f"http://www.youtube.com/watch?v={VIDEO_ID}&t=30s",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"https://music.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}?t=42",
        f"https://www.youtube.com/live/{VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"www.youtube.com/watch?v={VIDEO_ID}",  # 스킴 없음
        f"  https://youtu.be/{VIDEO_ID}  ",       # 공백
        # 재생목록 파라미터가 붙어도 영상 ID는 추출
        f"https://www.youtube.com/watch?v={VIDEO_ID}&list=PLxxxx&index=2",
    ],
)
def test_extract_video_id_valid(url):
    assert extract_video_id(url) == VIDEO_ID


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://example.com/watch?v=abcdefghijk",
        "https://www.youtube.com/watch?v=tooShort",
        "https://www.youtube.com/playlist?list=PLxxxx",
        "not a url",
    ],
)
def test_extract_video_id_invalid(url):
    with pytest.raises(InvalidURLError):
        extract_video_id(url)


def test_timestamp_url():
    assert (
        timestamp_url(VIDEO_ID, 754.6)
        == f"https://www.youtube.com/watch?v={VIDEO_ID}&t=754s"
    )
    assert timestamp_url(VIDEO_ID, 0) == f"https://www.youtube.com/watch?v={VIDEO_ID}&t=0s"
