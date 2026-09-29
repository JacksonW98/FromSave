from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QPointF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QImage, QPainter, QPolygonF
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSlider, QStackedWidget, QVBoxLayout, QWidget,
)

import video as video_module

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
    _HAS_MULTIMEDIA = True
except ImportError:
    _HAS_MULTIMEDIA = False

try:
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False

_UI_DIR = Path(__file__).parent


def _icon_button(icon: QIcon, on_click, tooltip: str = "") -> QPushButton:
    btn = QPushButton()
    btn.setIcon(icon)
    btn.setIconSize(QSize(14, 14))
    btn.setObjectName("ghostBtn")
    btn.setToolTip(tooltip)
    btn.clicked.connect(on_click)
    return btn


def _volume_slider(on_change) -> QSlider:
    slider = QSlider(Qt.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(100)
    slider.setFixedWidth(64)
    slider.valueChanged.connect(on_change)
    return slider


def _draw_centered(painter: QPainter, widget: QWidget, img: QImage) -> None:
    """Draw img scaled to fit inside widget, keeping its aspect ratio."""
    scaled = img.scaled(widget.size(), Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
    painter.drawImage((widget.width() - scaled.width()) // 2,
                      (widget.height() - scaled.height()) // 2, scaled)


class _ResizeHandle(QWidget):
    """Drag bar that sets the height of target."""

    _MIN_H = 120

    def __init__(self, target: QWidget, on_resize=None, parent=None):
        super().__init__(parent)
        self._target = target
        self._on_resize = on_resize
        self._drag_y = 0.0
        self._drag_h = 0
        self.setFixedHeight(5)
        self.setCursor(Qt.SizeVerCursor)
        self.setStyleSheet("background: #2a2a3a;")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_y = event.globalPosition().y()
            self._drag_h = self._target.height()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().y() - self._drag_y
            new_h = max(self._MIN_H, self._drag_h + int(delta))
            self._target.setFixedHeight(new_h)
            if self._on_resize:
                self._on_resize(new_h)
            event.accept()


class InlineVideoPlayer(QWidget):
    """Plays a local file with QtMultimedia or a web video in an embedded browser."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._url = ""
        self._player = None
        self._audio = None
        self._seeking = False
        self._thumb_player = None
        self._thumb_sink = None
        self._main_sink = None
        self._fs_window: Optional[QWidget] = None
        self._is_web: bool = False

        self._user_height: int = 0
        self.setFocusPolicy(Qt.ClickFocus)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 0)
        outer.setSpacing(0)
        self._outer_layout = outer

        self._stack = QStackedWidget()
        self._stack.setMinimumHeight(120)
        self._stack.setFixedHeight(320)

        if _HAS_MULTIMEDIA:
            self._video_widget = _VideoFrame()
            self._video_widget.installEventFilter(self)
        else:
            self._video_widget = QWidget()
            self._video_widget.setStyleSheet("background: #000;")

        self._video_container = QWidget()
        vc_layout = QVBoxLayout(self._video_container)
        vc_layout.setContentsMargins(0, 0, 0, 0)
        vc_layout.setSpacing(0)
        vc_layout.addWidget(self._video_widget)
        self._play_overlay = _PlayOverlay(self._toggle, self._video_container)
        self._play_overlay.hide()
        self._video_container.installEventFilter(self)

        self._stack.addWidget(self._video_container)  # index 0: local

        if _HAS_WEBENGINE:
            self._web_view = QWebEngineView()
            self._web_view.settings().setAttribute(
                QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True
            )
            self._web_view.page().fullScreenRequested.connect(self._on_web_fullscreen_requested)
        else:
            self._web_view = QWidget()
            self._web_view.setStyleSheet("background: #000;")
        self._stack.addWidget(self._web_view)  # index 1: web

        outer.addWidget(self._stack, 1)

        # Controls for local files
        self._local_bar = QWidget()
        self._local_bar.setStyleSheet("background: #16161e;")
        local_ctrl = QVBoxLayout(self._local_bar)
        local_ctrl.setContentsMargins(8, 4, 8, 4)
        local_ctrl.setSpacing(3)

        self._seek = QSlider(Qt.Horizontal)
        self._seek.setRange(0, 0)
        self._seek.sliderPressed.connect(self._on_seek_pressed)
        self._seek.sliderMoved.connect(self._on_seek_moved)
        self._seek.sliderReleased.connect(self._on_seek_released)
        local_ctrl.addWidget(self._seek)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._icon_play = QIcon(str(_UI_DIR / "play.svg"))
        self._icon_pause = QIcon(str(_UI_DIR / "pause.svg"))
        self._play_btn = _icon_button(self._icon_play, self._toggle)
        btn_row.addWidget(self._play_btn)

        self._time_lbl = QLabel("0:00 / 0:00")
        self._time_lbl.setStyleSheet("color: #888899; font-size: 11px;")
        btn_row.addWidget(self._time_lbl)

        btn_row.addStretch()

        self._vol = _volume_slider(self._set_volume)
        btn_row.addWidget(self._vol)

        browser_btn = QPushButton("Open in player")
        browser_btn.setObjectName("ghostBtn")
        browser_btn.clicked.connect(self._open_in_browser)
        btn_row.addWidget(browser_btn)

        self._icon_fullscreen = QIcon(str(_UI_DIR / "fullscreen.svg"))
        self._icon_fullscreen_exit = QIcon(str(_UI_DIR / "fullscreen_exit.svg"))
        self._fullscreen_btn = _icon_button(self._icon_fullscreen, self._toggle_fullscreen, "Fullscreen")
        btn_row.addWidget(self._fullscreen_btn)

        local_ctrl.addLayout(btn_row)
        outer.addWidget(self._local_bar)

        # Controls for web videos
        self._web_bar = QWidget()
        self._web_bar.setStyleSheet("background: #16161e;")
        web_row = QHBoxLayout(self._web_bar)
        web_row.setContentsMargins(8, 6, 8, 6)
        web_row.addStretch()

        self._web_vol = _volume_slider(self._set_web_volume)
        web_row.addWidget(self._web_vol)

        web_browser_btn = QPushButton("Open in browser")
        web_browser_btn.setObjectName("ghostBtn")
        web_browser_btn.clicked.connect(self._open_web_in_browser)
        web_row.addWidget(web_browser_btn)

        self._web_fullscreen_btn = _icon_button(self._icon_fullscreen, self._toggle_fullscreen, "Fullscreen")
        web_row.addWidget(self._web_fullscreen_btn)

        outer.addWidget(self._web_bar)
        outer.addWidget(_ResizeHandle(self._stack, on_resize=self._on_manual_resize))

        self._local_bar.hide()
        self._web_bar.hide()

    @property
    def url(self) -> str:
        return self._url

    def _on_manual_resize(self, h: int) -> None:
        self._user_height = h

    def update_height(self, win_h: int) -> None:
        """Follow the window height until the user drags the resize handle."""
        if self._user_height != 0:
            return
        new_h = max(120, int(win_h * 0.50))
        if abs(self._stack.height() - new_h) > 2:
            self._stack.setFixedHeight(new_h)

    def load(self, url: str) -> None:
        self._stop()
        self._url = url
        if not url:
            return
        parsed = QUrl(url)
        if parsed.isLocalFile():
            self._load_local(parsed)
        else:
            self._load_web(url)

    def unload(self) -> None:
        self._stop()
        if _HAS_WEBENGINE:
            self._web_view.load(QUrl("about:blank"))
        self._url = ""

    def _load_local(self, parsed: QUrl) -> None:
        if not _HAS_MULTIMEDIA:
            return
        if _HAS_WEBENGINE:
            self._web_view.load(QUrl("about:blank"))
        self._stack.setCurrentIndex(0)
        self._is_web = False
        self._local_bar.show()
        self._web_bar.hide()
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setVolume(self._vol.value() / 100.0)
        self._player.setAudioOutput(self._audio)
        self._main_sink = QVideoSink(self)
        self._main_sink.videoFrameChanged.connect(self._video_widget.update_frame)
        self._player.setVideoSink(self._main_sink)
        self._player.setSource(parsed)
        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state)
        self._play_overlay.set_thumbnail(None)
        self._play_overlay.setGeometry(self._video_container.rect())
        self._play_overlay.show()
        self._play_overlay.raise_()
        self._grab_thumbnail(parsed)

    def _load_web(self, url: str) -> None:
        if not _HAS_WEBENGINE:
            return
        self._stack.setCurrentIndex(1)
        self._is_web = True
        self._local_bar.hide()
        self._web_bar.show()
        html = video_module.embed_html(url, autoplay=False) or video_module.unsupported_html()
        self._web_view.setHtml(html, QUrl("http://localhost/"))
        QTimer.singleShot(1200, lambda: self._set_web_volume(self._web_vol.value()))

    def _stop(self) -> None:
        self._exit_fullscreen()
        self._is_web = False
        if self._thumb_player is not None:
            self._thumb_player.stop()
            self._thumb_player.deleteLater()
            self._thumb_player = None
        if self._thumb_sink is not None:
            self._thumb_sink.deleteLater()
            self._thumb_sink = None
        if self._player is not None:
            self._player.positionChanged.disconnect(self._on_position)
            self._player.durationChanged.disconnect(self._on_duration)
            self._player.playbackStateChanged.disconnect(self._on_state)
            self._player.stop()
            self._player.deleteLater()
            self._player = None
        if self._main_sink is not None:
            self._main_sink.deleteLater()
            self._main_sink = None
        if self._audio is not None:
            self._audio.deleteLater()
            self._audio = None
        self._play_overlay.hide()
        self._seeking = False
        self._seek.blockSignals(True)
        self._seek.setValue(0)
        self._seek.setRange(0, 0)
        self._seek.blockSignals(False)
        self._time_lbl.setText("0:00 / 0:00")
        self._play_btn.setIcon(self._icon_play)
        self._local_bar.hide()
        self._web_bar.hide()

    def _grab_thumbnail(self, url: QUrl) -> None:
        if not _HAS_MULTIMEDIA:
            return
        self._thumb_player = QMediaPlayer(self)
        self._thumb_sink = QVideoSink(self)
        self._thumb_player.setVideoSink(self._thumb_sink)
        self._thumb_player.setSource(url)
        state = {"seeked": False}

        def on_frame(frame) -> None:
            if self._thumb_player is None or not frame.isValid():
                return
            if not state["seeked"]:
                dur = self._thumb_player.duration()
                if dur > 1000:
                    self._thumb_player.setPosition(min(2000, dur // 4))
                state["seeked"] = True
                return
            img = frame.toImage()
            if img.isNull():
                return
            tp, ts = self._thumb_player, self._thumb_sink
            self._thumb_player = None
            self._thumb_sink = None
            tp.stop()
            tp.deleteLater()
            ts.deleteLater()
            self._play_overlay.set_thumbnail(img)

        self._thumb_sink.videoFrameChanged.connect(on_frame)
        self._thumb_player.play()

    def _open_in_browser(self) -> None:
        if self._player is not None:
            self._player.pause()
        QDesktopServices.openUrl(QUrl(self._url))

    def eventFilter(self, obj, event) -> bool:
        if obj is self._video_widget and event.type() == QEvent.Type.MouseButtonDblClick:
            self._toggle_fullscreen()
            return True
        if obj is self._video_widget and event.type() == QEvent.Type.MouseButtonRelease:
            self._toggle()
            self.setFocus()
            return True
        if obj is self._video_container and event.type() == QEvent.Type.Resize:
            self._play_overlay.setGeometry(obj.rect())
        if obj is self._fs_window and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F):
                self._exit_fullscreen()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._toggle()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F:
            self._toggle_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)

    def _toggle_fullscreen(self) -> None:
        if self._fs_window is not None:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _on_web_fullscreen_requested(self, request) -> None:
        request.accept()
        if request.toggleOn():
            self._enter_fullscreen()
        else:
            self._exit_fullscreen()

    def _enter_fullscreen(self) -> None:
        if self._fs_window is not None:
            return
        idx = self._stack.currentIndex()
        if idx == 0:
            content, bar, btn = self._video_container, self._local_bar, self._fullscreen_btn
        elif idx == 1:
            content, bar, btn = self._web_view, self._web_bar, self._web_fullscreen_btn
        else:
            return
        self._fs_idx = idx
        self._fs_content = content
        self._fs_bar = bar
        self._fs_btn = btn
        self._fs_bar_index = self._outer_layout.indexOf(bar)
        self._stack.removeWidget(content)
        self._outer_layout.removeWidget(bar)
        self._fs_window = QWidget()
        self._fs_window.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self._fs_window.setStyleSheet("background: #000;")
        self._fs_window.setWindowTitle("FromSave Manager - Video")
        layout = QVBoxLayout(self._fs_window)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(content, 1)
        layout.addWidget(bar)
        content.show()
        bar.show()
        self._fs_window.installEventFilter(self)
        self._fs_window.showFullScreen()
        self._fs_window.setFocus()
        btn.setIcon(self._icon_fullscreen_exit)

    def _exit_fullscreen(self) -> None:
        if self._fs_window is None:
            return
        fs_window = self._fs_window
        self._fs_window = None
        content, bar, btn, idx = self._fs_content, self._fs_bar, self._fs_btn, self._fs_idx
        fs_window.layout().removeWidget(content)
        fs_window.layout().removeWidget(bar)
        self._stack.insertWidget(idx, content)
        self._stack.setCurrentIndex(idx)
        if self._fs_bar_index >= 0:
            self._outer_layout.insertWidget(self._fs_bar_index, bar)
        else:
            self._outer_layout.addWidget(bar)
        bar.show()
        fs_window.removeEventFilter(self)
        fs_window.close()
        fs_window.deleteLater()
        btn.setIcon(self._icon_fullscreen)

    def _open_web_in_browser(self) -> None:
        if not _HAS_WEBENGINE:
            QDesktopServices.openUrl(QUrl(self._url))
            return
        self._web_view.page().runJavaScript(
            "(function(){"
            "var f=document.querySelector('iframe');if(!f)return;"
            "f.contentWindow.postMessage('{\"event\":\"command\",\"func\":\"pauseVideo\",\"args\":\"\"}','*');"
            "f.contentWindow.postMessage('{\"method\":\"pause\"}','*');"
            "})()"
        )
        self._web_view.page().runJavaScript(
            "window._embed_time||0",
            self._open_browser_at_time,
        )

    def _open_browser_at_time(self, t) -> None:
        url = self._url
        if isinstance(t, (int, float)) and t > 1 and video_module.youtube_video_id(url):
            sep = '&' if '?' in url else '?'
            url = f"{url}{sep}t={int(t)}"
        QDesktopServices.openUrl(QUrl(url))

    def _set_web_volume(self, v: int) -> None:
        if not _HAS_WEBENGINE or not self._is_web:
            return
        mute_cmd = "unMute" if v > 0 else "mute"
        self._web_view.page().runJavaScript(
            "(function(){"
            "var f=document.querySelector('iframe');if(!f)return;"
            "f.contentWindow.postMessage('{\"event\":\"command\",\"func\":\"setVolume\",\"args\":[" + str(v) + "]}','*');"
            "f.contentWindow.postMessage('{\"event\":\"command\",\"func\":\"" + mute_cmd + "\",\"args\":\"\"}','*');"
            "})()"
        )

    def _toggle(self) -> None:
        if self._player is None:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_seek_pressed(self) -> None:
        self._seeking = True

    def _on_seek_moved(self, ms: int) -> None:
        dur = self._player.duration() if self._player is not None else 0
        self._time_lbl.setText(f"{_fmt_ms(ms)} / {_fmt_ms(dur)}")
        if self._player is not None:
            self._player.setPosition(ms)

    def _on_seek_released(self) -> None:
        self._seeking = False
        if self._player is not None:
            self._player.setPosition(self._seek.value())

    def _set_volume(self, v: int) -> None:
        if self._audio is not None:
            self._audio.setVolume(v / 100.0)

    def _on_position(self, ms: int) -> None:
        if not self._seeking:
            self._seek.blockSignals(True)
            self._seek.setValue(ms)
            self._seek.blockSignals(False)
            dur = self._player.duration() if self._player is not None else 0
            self._time_lbl.setText(f"{_fmt_ms(ms)} / {_fmt_ms(dur)}")

    def _on_duration(self, ms: int) -> None:
        self._seek.setRange(0, ms)

    def _on_state(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._play_btn.setIcon(self._icon_pause if playing else self._icon_play)
        if playing:
            self._play_overlay.hide()


class _PlayOverlay(QWidget):
    def __init__(self, on_click, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._on_click = on_click
        self._thumbnail: QImage | None = None

    def set_thumbnail(self, img: QImage | None) -> None:
        self._thumbnail = img
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._thumbnail is not None and not self._thumbnail.isNull():
            _draw_centered(p, self, self._thumbnail)
            p.fillRect(self.rect(), QColor(0, 0, 0, 60))
        cx = self.width() / 2
        cy = self.height() / 2
        r = 36.0
        p.setBrush(QColor(255, 255, 255, 200))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)
        tri_h = r * 0.85
        tri_w = tri_h * 0.9
        ox = r * 0.12
        p.setBrush(QColor(20, 20, 20, 220))
        p.drawPolygon(QPolygonF([
            QPointF(cx - tri_w / 2 + ox, cy - tri_h / 2),
            QPointF(cx - tri_w / 2 + ox, cy + tri_h / 2),
            QPointF(cx + tri_w / 2 + ox, cy),
        ]))


class _VideoFrame(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: #000;")
        self._frame: QImage | None = None

    def update_frame(self, frame) -> None:
        if frame.isValid():
            img = frame.toImage()
            if not img.isNull():
                self._frame = img
                self.update()

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        if self._frame and not self._frame.isNull():
            _draw_centered(p, self, self._frame)


def _fmt_ms(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02}:{s:02}"
    return f"{m}:{s:02}"
