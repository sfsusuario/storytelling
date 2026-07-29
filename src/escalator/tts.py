from __future__ import annotations

import asyncio
from pathlib import Path

from .ffutil import probe_duration
from .models import Scene


class TtsError(RuntimeError):
    pass


async def _synthesize_one(text: str, voice: str, out_path: Path,
                          rate: str, pitch: str) -> list[dict]:
    """Synthesize audio and return word timings [{t, d, w}] in seconds."""
    import edge_tts

    tmp = out_path.with_suffix(".tmp")
    for attempt in (1, 2):
        try:
            words: list[dict] = []
            communicate = edge_tts.Communicate(text, voice, rate=rate,
                                               pitch=pitch,
                                               boundary="WordBoundary")
            with open(tmp, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        words.append({"t": chunk["offset"] / 1e7,
                                      "d": chunk["duration"] / 1e7,
                                      "w": chunk["text"]})
            if tmp.stat().st_size == 0:
                raise TtsError(f"edge-tts produced an empty file for: {text!r}")
            tmp.replace(out_path)
            return words
        except TtsError:
            tmp.unlink(missing_ok=True)
            raise
        except Exception as e:
            tmp.unlink(missing_ok=True)
            if attempt == 2:
                raise TtsError(
                    f"edge-tts failed for {out_path.name}: {e}\n"
                    "edge-tts needs internet access; check connectivity.") from e
            await asyncio.sleep(2)
    return []


def synthesize_scenes(scenes: list[Scene], voice: str, audio_dir: Path,
                      ffprobe: str, rate: str = "+0%", pitch: str = "+0Hz",
                      log=print) -> None:
    """Generate one audio file per scene (cached) and fill in durations."""
    audio_dir.mkdir(parents=True, exist_ok=True)

    import json

    async def run() -> None:
        for scene in scenes:
            out = audio_dir / f"{scene.scene_id}.mp3"
            meta = audio_dir / f"{scene.scene_id}.json"
            stamp = f"{voice}|{rate}|{pitch}|wb|{scene.speech_script}"
            cached_meta = None
            if out.exists() and out.stat().st_size > 0 and meta.exists():
                try:
                    data = json.loads(meta.read_text(encoding="utf-8"))
                    if data.get("stamp") == stamp:
                        cached_meta = data
                except json.JSONDecodeError:
                    pass
            if cached_meta is not None:
                scene.word_timings = cached_meta.get("words") or None
                log(f"  tts: {out.name} (cached)")
            else:
                words = await _synthesize_one(scene.speech_script, voice, out,
                                              rate, pitch)
                scene.word_timings = words or None
                meta.write_text(json.dumps({"stamp": stamp, "words": words},
                                           ensure_ascii=False),
                                encoding="utf-8")
                log(f"  tts: {out.name}")
            scene.audio_path = out

    asyncio.run(run())

    for scene in scenes:
        scene.audio_duration = probe_duration(ffprobe, scene.audio_path)
