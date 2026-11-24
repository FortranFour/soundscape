"""One ffmpeg process and one thread per microphone."""
from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable

from .dsp import HOP, HOPS_PER_COL, Analyzer

_LOGGER = logging.getLogger(__name__)
CHUNK_COLS = 4


class Capture(threading.Thread):
    """Decode a stream to mono PCM and run the analyzer on it."""

    def __init__(self, ffmpeg: str, mic: str, url: str, sr: int,
                 on_audio: Callable, input_args: tuple[str, ...] = ()) -> None:
        super().__init__(name=f"soundscape-{mic}", daemon=True)
        self.mic, self.url, self.sr = mic, url, sr
        self._ffmpeg, self._on_audio, self._input_args = ffmpeg, on_audio, input_args
        self._halt = threading.Event()
        self._proc: subprocess.Popen | None = None
        self.error: str | None = None
        self.running = False
        self.on_pcm: Callable | None = None  # set while someone is listening live
        self.ring_seconds = 0.0              # how much raw audio to remember, for recordings of sounds
        self.ring: deque[tuple[float, bytes]] = deque()
        self._ring_bytes = 0

    def stop(self) -> None:
        self._halt.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def _command(self) -> list[str]:
        cmd = [self._ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", *self._input_args]
        if self.url.startswith(("rtsp://", "rtsps://")):
            cmd += ["-rtsp_transport", "tcp", "-timeout", "15000000"]
        if "://" not in self.url:
            cmd += ["-re"]  # a file: play it at its own pace
        return [*cmd, "-i", self.url, "-vn", "-ac", "1", "-ar", str(self.sr), "-f", "s16le", "-"]

    def run(self) -> None:
        wait = 5.0
        want = HOP * HOPS_PER_COL * CHUNK_COLS * 2
        while not self._halt.is_set():
            analyzer = Analyzer(self.sr)
            errors: list[str] = []
            got = 0
            try:
                self._proc = proc = subprocess.Popen(
                    self._command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                threading.Thread(target=self._drain, args=(proc, errors), daemon=True).start()
                while not self._halt.is_set():
                    data = proc.stdout.read(want)
                    if not data:
                        break
                    got += len(data)
                    if not self.running:
                        self.running, self.error = True, None
                    data = data[: len(data) & ~1]
                    if listener := self.on_pcm:
                        listener(self.mic, data)
                    if self.ring_seconds:
                        self.ring.append((time.time(), data))
                        self._ring_bytes += len(data)
                        while self._ring_bytes > self.ring_seconds * self.sr * 2:
                            self._ring_bytes -= len(self.ring.popleft()[1])
                    cols, n, feats = analyzer.process(data)
                    if n or feats:
                        self._on_audio(self.mic, cols, n, feats)
            except Exception as err:  # noqa: BLE001 - keep the thread alive
                errors.append(repr(err))
            finally:
                self.running = False
                if self._proc and self._proc.poll() is None:
                    self._proc.kill()
            if self._halt.is_set():
                break
            self.error = (errors[-1] if errors else "stream ended")[:300]
            # Credentials can sit in the URL: log the microphone, not the address.
            _LOGGER.warning("Soundscape: audio from %s stopped (%s); retrying in %.0f s",
                            self.mic, self.error, wait)
            self._halt.wait(wait)
            wait = 5.0 if got > self.sr * 2 * 60 else min(120.0, wait * 2)

    def cut(self, t0: float, t1: float) -> tuple[float, bytes]:
        """The remembered audio between two clock times: (when it actually starts, PCM)."""
        out, first = [], None
        for t_end, data in list(self.ring):
            t_start = t_end - len(data) / 2 / self.sr
            if t_end <= t0 or t_start >= t1:
                continue
            a = max(0, int((t0 - t_start) * self.sr)) * 2
            b = min(len(data), int((t1 - t_start) * self.sr) * 2)
            if b > a:
                if first is None:
                    first = t_start + a / 2 / self.sr
                out.append(data[a:b])
        return first or t0, b"".join(out)

    @staticmethod
    def _drain(proc: subprocess.Popen, errors: list[str]) -> None:
        for line in proc.stderr:
            text = re.sub(r"//[^@/\s]+@", "//***@", line.decode(errors="replace").strip())
            if text:
                errors.append(text)
                del errors[:-5]
