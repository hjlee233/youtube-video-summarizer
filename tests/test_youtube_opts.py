"""yt-dlp 접근 옵션(_apply_access_opts) 단위 테스트."""

from tubenote.youtube import _apply_access_opts


def test_no_options_by_default():
    opts = _apply_access_opts({}, cookies_from_browser=None, allow_remote_components=False)
    assert "cookiesfrombrowser" not in opts
    assert "remote_components" not in opts


def test_cookies_from_browser_applied():
    opts = _apply_access_opts({}, cookies_from_browser="firefox", allow_remote_components=False)
    assert opts["cookiesfrombrowser"] == ("firefox",)
    assert "remote_components" not in opts


def test_remote_components_applied():
    opts = _apply_access_opts({}, cookies_from_browser=None, allow_remote_components=True)
    assert opts["remote_components"] == ["ejs:github"]


def test_both_applied():
    opts = _apply_access_opts({}, cookies_from_browser="chrome", allow_remote_components=True)
    assert opts["cookiesfrombrowser"] == ("chrome",)
    assert opts["remote_components"] == ["ejs:github"]
