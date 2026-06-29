"""Tests for video URL parsing and embed helpers."""
import video


class TestYouTubeVideoId:
    def test_watch_url(self):
        assert video.youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert video.youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        assert video.youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert video.youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"



class TestEmbedUrl:
    def test_youtube_embed(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert video.embed_url_for(url) == "https://www.youtube.com/embed/dQw4w9WgXcQ?autoplay=1"

    def test_vimeo_embed(self):
        url = "https://vimeo.com/123456789"
        assert video.embed_url_for(url) == "https://player.vimeo.com/video/123456789?autoplay=1"

    def test_direct_video_returns_none(self):
        assert video.embed_url_for("https://example.com/clip.mp4") is None


class TestDirectVideo:
    def test_mp4(self):
        assert video.is_direct_video_url("https://cdn.example.com/video.mp4")

    def test_webm(self):
        assert video.is_direct_video_url("https://cdn.example.com/video.webm")

    def test_non_video(self):
        assert not video.is_direct_video_url("https://example.com/page.html")


class TestEmbedHtml:
    def test_youtube_returns_iframe_html(self):
        html = video.embed_html("https://youtu.be/dQw4w9WgXcQ")
        assert html is not None
        assert "<iframe" in html
        assert "dQw4w9WgXcQ" in html

    def test_direct_mp4_returns_video_tag(self):
        html = video.embed_html("https://example.com/clip.mp4")
        assert html is not None
        assert "<video" in html
        assert "clip.mp4" in html

    def test_unsupported_returns_none(self):
        assert video.embed_html("https://example.com/not-a-video") is None

    def test_empty_returns_none(self):
        assert video.embed_html("") is None
