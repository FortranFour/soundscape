"""Speech in a recording, put into words by one of Home Assistant's speech-to-text engines."""
from __future__ import annotations

import numpy as np

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

STT_RATE = 16000


class NoEngine(HomeAssistantError):
    """No speech-to-text engine is set up."""


def prepare(pcm: bytes, rate: int) -> bytes:
    """16-bit mono at any rate -> 16 kHz, brought up to a level a recogniser expects.

    Camera microphones are quiet and speech in a yard is far from them, so the
    recording is scaled until its loudest moments sit just under full scale.
    """
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    if not len(x):
        return b""
    x -= float(x.mean())
    if rate != STT_RATE:
        # low-pass under the new Nyquist, then pick the new sample points
        taps = 63
        t = np.arange(taps) - (taps - 1) / 2
        cut = 0.45 * STT_RATE / rate * 2
        fir = np.sinc(cut * t) * cut * np.hamming(taps)
        x = np.convolve(x, fir / fir.sum(), mode="same")
        n = int(len(x) * STT_RATE / rate)
        x = np.interp(np.arange(n) * rate / STT_RATE, np.arange(len(x)), x)
    peak = float(np.percentile(np.abs(x), 99.9)) if len(x) else 0.0
    if peak > 1e-4:
        x = x * min(0.7 / peak, 60.0)
    return (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()


def engine_id(hass: HomeAssistant, wanted: str | None) -> str:
    from homeassistant.components import stt  # noqa: PLC0415  loaded only when asked for

    if "stt" not in hass.config.components:
        raise NoEngine
    if wanted and stt.async_get_speech_to_text_engine(hass, wanted):
        return wanted
    if found := stt.async_default_engine(hass):
        return found
    raise NoEngine


async def transcribe(hass: HomeAssistant, wanted: str | None, pcm: bytes, rate: int) -> tuple[str, str]:
    """Return (text, name of the engine). Empty text means it heard no words."""
    from homeassistant.components import stt  # noqa: PLC0415
    from homeassistant.util import language as language_util  # noqa: PLC0415

    eid = engine_id(hass, wanted)
    engine = stt.async_get_speech_to_text_engine(hass, eid)
    if engine is None:
        raise NoEngine
    audio = await hass.async_add_executor_job(prepare, pcm, rate)
    supported = list(engine.supported_languages)
    match = language_util.matches(hass.config.language, supported, country=hass.config.country)
    language = match[0] if match else ("en" if "en" in supported else supported[0] if supported else "en")
    meta = stt.SpeechMetadata(
        language=language, format=stt.AudioFormats.WAV, codec=stt.AudioCodecs.PCM,
        bit_rate=stt.AudioBitRates.BITRATE_16, sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
        channel=stt.AudioChannels.CHANNEL_MONO)

    async def chunks():
        for i in range(0, len(audio), 4096):
            yield audio[i:i + 4096]

    result = await engine.async_process_audio_stream(meta, chunks())
    if result.result != stt.SpeechResultState.SUCCESS:
        raise HomeAssistantError("The speech-to-text engine could not process the recording")
    name = getattr(engine, "name", None) or eid
    return (result.text or "").strip(), str(name)
