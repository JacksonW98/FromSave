"""Parse video URLs and build embed HTML for in-app playback."""
import re
from urllib.parse import urlparse

_DIRECT_VIDEO_EXTENSIONS = (".mp4", ".webm", ".ogg", ".mov", ".m4v", ".mkv")

_YOUTUBE_ID = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})"
)


def youtube_video_id(url: str) -> str | None:
    match = _YOUTUBE_ID.search(url)
    return match.group(1) if match else None


def embed_html(url: str, autoplay: bool = True) -> str | None:
    """Return a minimal HTML page that embeds the video, or None if unsupported."""
    url = url.strip()
    if yt_id := youtube_video_id(url):
        return _iframe_page(
            f"https://www.youtube.com/embed/{yt_id}?autoplay={int(autoplay)}&enablejsapi=1"
        )
    if urlparse(url).path.lower().endswith(_DIRECT_VIDEO_EXTENSIONS):
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
