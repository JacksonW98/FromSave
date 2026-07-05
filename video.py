"""Parse video URLs and build embed HTML for in-app playback."""
import re
from urllib.parse import parse_qs, urlparse

_DIRECT_VIDEO_EXTENSIONS = (".mp4", ".webm", ".ogg", ".mov", ".m4v", ".mkv")

_YOUTUBE_PATTERNS = (
    re.compile(r"(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([\w-]{11})"),
    re.compile(r"youtube\.com/watch\?.*[?&]v=([\w-]{11})"),
)
_TWITCH_VOD_PATTERN = re.compile(r"twitch\.tv/videos/(\d+)")
_TWITCH_CLIP_PATTERNS = (
    re.compile(r"twitch\.tv/[^/]+/clip/([\w-]+)"),
    re.compile(r"clips\.twitch\.tv/([\w-]+)"),
)


def normalize_video_url(url: str) -> str:
    return url.strip()


def is_direct_video_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _DIRECT_VIDEO_EXTENSIONS)


def youtube_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
        return vid if len(vid) == 11 else None
    if host in ("youtube.com", "m.youtube.com"):
        if parsed.path.startswith("/embed/"):
            vid = parsed.path.split("/")[2]
            return vid if len(vid) == 11 else None
        if parsed.path.startswith("/shorts/"):
            vid = parsed.path.split("/")[2]
            return vid if len(vid) == 11 else None
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            vid = qs.get("v", [None])[0]
            return vid if vid and len(vid) == 11 else None
    for pattern in _YOUTUBE_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def twitch_vod_id(url: str) -> str | None:
    match = _TWITCH_VOD_PATTERN.search(url)
    return match.group(1) if match else None


def twitch_clip_id(url: str) -> str | None:
    for pattern in _TWITCH_CLIP_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def embed_url_for(url: str, autoplay: bool = True) -> str | None:
    """Return an iframe-friendly embed URL, or None if unsupported."""
    url = normalize_video_url(url)
    if not url:
        return None

    yt_id = youtube_video_id(url)
    if yt_id:
        ap = "1" if autoplay else "0"
        return f"https://www.youtube.com/embed/{yt_id}?autoplay={ap}&enablejsapi=1"

    return None


def embed_html(url: str, autoplay: bool = True) -> str | None:
    """Return a minimal HTML page that embeds the video, or None if unsupported."""
    url = normalize_video_url(url)
    if not url:
        return None

    embed = embed_url_for(url, autoplay=autoplay)
    if embed:
        return _iframe_page(embed)

    if is_direct_video_url(url):
        return _video_page(url, autoplay=autoplay)

    return None


def unsupported_html() -> str:
    return """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html, body {
    margin: 0; padding: 0; height: 100%;
    background: #13131a;
    display: flex; align-items: center; justify-content: center;
    font-family: system-ui, -apple-system, sans-serif;
  }
  p { color: #888899; font-size: 13px; text-align: center; line-height: 1.7; margin: 0; padding: 0 28px; }
  strong { color: #aaaabb; }
</style>
</head><body>
<p>This website is not supported for inline playback.<br>
Press <strong>Open in browser</strong> below to watch the video.</p>
</body></html>"""


def _iframe_page(src: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html, body {{ margin: 0; padding: 0; background: #000; height: 100%; overflow: hidden; }}
  iframe {{ width: 100%; height: 100%; border: none; }}
</style>
<script>
window._embed_time = 0;
window.addEventListener('message', function(e) {{
  try {{
    var d = JSON.parse(e.data);
    if (d.event === 'infoDelivery' && d.info && d.info.currentTime !== undefined) {{
      window._embed_time = d.info.currentTime;
    }}
  }} catch(x) {{}}
}});
function _onPlayerLoad(el) {{
  try {{ el.contentWindow.postMessage('{{"event":"listening"}}', '*'); }} catch(e) {{}}
}}
</script>
</head><body>
<iframe src="{src}"
  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen"
  allowfullscreen
  onload="_onPlayerLoad(this)">
</iframe>
</body></html>"""


def _video_page(src: str, autoplay: bool = True) -> str:
    autoplay_attr = " autoplay" if autoplay else ""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html, body {{ margin: 0; padding: 0; background: #000; height: 100%; }}
  video {{ width: 100%; height: 100%; object-fit: contain; }}
</style></head><body>
<video controls{autoplay_attr} playsinline><source src="{src}"></video>
</body></html>"""
