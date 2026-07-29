from __future__ import annotations

import textwrap
from pathlib import Path

from .config import FADE_DURATION
from .ffutil import run_ffmpeg
from .models import Timeline


def _drawtext_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(":", "\\:")
                .replace("'", "’").replace(",", "\\,"))


_SUB_STYLE = (
    "fontfile='C\\:/Windows/Fonts/arialbd.ttf':"
    "fontsize=h/34:fontcolor=white:"
    "borderw=3:bordercolor=black@0.7:"
    "box=1:boxcolor=black@0.35:boxborderw=14:"
    "line_spacing=6:text_align=C:"
    "x=(w-text_w)/2:y=h*0.82-text_h"
)

_CHUNK_MAX_CHARS = 24


def _chunk_words(words: list[dict]) -> list[tuple[str, float, float]]:
    """Group word timings into short caption chunks: (text, start, end)."""
    chunks: list[tuple[str, float, float]] = []
    current: list[dict] = []
    length = 0
    for word in words:
        current.append(word)
        length += len(word["w"]) + 1
        if length >= _CHUNK_MAX_CHARS:
            text = " ".join(w["w"] for w in current)
            chunks.append((text, current[0]["t"],
                           current[-1]["t"] + current[-1]["d"]))
            current, length = [], 0
    if current:
        text = " ".join(w["w"] for w in current)
        chunks.append((text, current[0]["t"],
                       current[-1]["t"] + current[-1]["d"]))
    return chunks


def _sub_textfile(clips_dir: Path, name: str, content: str) -> str:
    f = clips_dir / name
    f.write_text(content, encoding="utf-8", newline="\n")
    return f.resolve().as_posix().replace(":", "\\:")


def _subtitle_filters(scene, clips_dir: Path, duration: float,
                      trigger_delay: float) -> str:
    """Progressive narration captions: each chunk appears as it is spoken.

    Falls back to the full (wrapped) text when word timings are unavailable.
    """
    if scene.word_timings:
        filters = []
        # Sentence case over the WHOLE narration: only the very first letter
        # of the first chunk is uppercase; every other word is lowercase.
        lowered = [{**w, "w": w["w"].lower()} for w in scene.word_timings]
        chunks = _chunk_words(lowered)
        for i, (text, start, end) in enumerate(chunks):
            if i == 0 and text:
                text = text[0].upper() + text[1:]
            path = _sub_textfile(
                clips_dir, f"{scene.scene_id}.sub{i:02d}.txt",
                "\n".join(textwrap.wrap(text, width=_CHUNK_MAX_CHARS + 4)))
            show = max(0.0, start + trigger_delay - 0.05)
            # keep each caption up until the next one takes over
            if i + 1 < len(chunks):
                hide = chunks[i + 1][1] + trigger_delay - 0.05
            else:
                hide = min(duration - 0.3, end + trigger_delay + 0.4)
            filters.append(
                f"drawtext=textfile='{path}':{_SUB_STYLE}:"
                f"enable='between(t,{show:.3f},{hide:.3f})',")
        return "".join(filters)

    text = scene.speech_script.strip()
    text = text[0].upper() + text[1:].lower() if text else text
    wrapped = "\n".join(textwrap.wrap(text, width=28))
    path = _sub_textfile(clips_dir, f"{scene.scene_id}.sub.txt", wrapped)
    end = max(0.5, duration - 0.35)
    return (f"drawtext=textfile='{path}':{_SUB_STYLE}:"
            f"enable='between(t,0.15,{end:.3f})',")


def _level_filter(level_word: str, level: int, total: int) -> str:
    label = _drawtext_escape(f"{level_word} {level}/{total}")
    return (
        f"drawtext=text='{label}':"
        "fontfile='C\\:/Windows/Fonts/arialbd.ttf':"
        "fontsize=h/30:fontcolor=white:"
        "borderw=3:bordercolor=black@0.6:"
        "box=1:boxcolor=black@0.35:boxborderw=12:"
        "x=(w-text_w)/2:y=h*0.045,"
    )


def _watermark_filter(text: str) -> str:
    """Bottom-left overlay, sized relative to the frame."""
    return (
        f"drawtext=text='{_drawtext_escape(text)}':"
        "fontfile='C\\:/Windows/Fonts/arialbd.ttf':"
        "fontsize=h/42:fontcolor=white@0.85:"
        "borderw=2:bordercolor=black@0.55:"
        "x=w*0.035:y=h-text_h-h*0.03,"
    )


def render_scene_clip(ffmpeg: str, timeline: Timeline, scene, clips_dir: Path,
                      log=print) -> Path:
    out = clips_dir / f"{scene.scene_id}.mp4"
    meta_file = clips_dir / f"{scene.scene_id}.meta"
    stamp = "|".join(str(x) for x in (
        "v2-sentencecase",
        scene.speech_script, scene.scene_duration, timeline.fit,
        timeline.watermark, timeline.subtitles, timeline.width,
        timeline.height, timeline.fps, timeline.level_word,
        len(scene.word_timings or []),
        scene.image_path.stat().st_mtime_ns,
        scene.audio_path.stat().st_mtime_ns))
    if (out.exists() and out.stat().st_size > 0 and meta_file.exists()
            and meta_file.read_text(encoding="utf-8") == stamp):
        log(f"  clip: {out.name} (cached)")
        scene.clip_path = out
        return out

    w, h, fps = timeline.width, timeline.height, timeline.fps
    d = scene.scene_duration
    delay_ms = round(scene.audio_trigger_delay * 1000)
    fade_out_start = max(0.0, d - FADE_DURATION)

    # How the source image fills the (vertical) frame:
    #   crop — center-crop to fill, TikTok/Reels style (default)
    #   blur — fit inside, blurred stretched copy fills the background
    #   pad  — fit inside with black bars
    if timeline.fit == "blur":
        fill = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},gblur=sigma=24[bgb];"
            f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,"
        )
    elif timeline.fit == "pad":
        fill = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        )
    else:  # crop
        fill = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},"
        )

    watermark = _watermark_filter(timeline.watermark) if timeline.watermark else ""
    subtitle = level = ""
    if timeline.subtitles:
        if scene.speech_script:
            subtitle = _subtitle_filters(scene, clips_dir, d,
                                         scene.audio_trigger_delay)
        total = max(s.persona.level for s in timeline.scenes)
        level = _level_filter(timeline.level_word, scene.persona.level, total)
    filter_complex = (
        f"{fill}"
        f"{subtitle}"
        f"{level}"
        f"{watermark}"
        f"setsar=1,format=yuv420p,"
        f"fade=t=in:st=0:d={FADE_DURATION},"
        f"fade=t=out:st={fade_out_start:.6f}:d={FADE_DURATION}[v];"
        f"[1:a]adelay={delay_ms}|{delay_ms},apad[a]"
    )
    tmp = out.with_suffix(".tmp.mp4")
    run_ffmpeg(ffmpeg, [
        "-y",
        "-loop", "1", "-framerate", str(fps), "-i", str(scene.image_path),
        "-i", str(scene.audio_path),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-t", f"{d:.6f}", "-r", str(fps),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        str(tmp),
    ])
    tmp.replace(out)
    meta_file.write_text(stamp, encoding="utf-8")
    scene.clip_path = out
    log(f"  clip: {out.name}")
    return out


def concat_clips(ffmpeg: str, timeline: Timeline, clips_dir: Path,
                 final_path: Path, reencode: bool = False, log=print) -> Path:
    concat_file = clips_dir / "concat.txt"
    lines = [f"file '{s.clip_path.resolve().as_posix()}'" for s in timeline.scenes]
    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    codec_args = (["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                   "-c:a", "aac", "-b:a", "192k"]
                  if reencode else ["-c", "copy"])
    tmp = final_path.with_suffix(".tmp.mp4")
    run_ffmpeg(ffmpeg, [
        "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        *codec_args, "-movflags", "+faststart", str(tmp),
    ])
    tmp.replace(final_path)
    log(f"  final: {final_path.name}")
    return final_path


def render_all(ffmpeg: str, timeline: Timeline, clips_dir: Path,
               final_path: Path, reencode: bool = False, log=print) -> Path:
    clips_dir.mkdir(parents=True, exist_ok=True)
    for scene in timeline.scenes:
        render_scene_clip(ffmpeg, timeline, scene, clips_dir, log=log)
    return concat_clips(ffmpeg, timeline, clips_dir, final_path,
                        reencode=reencode, log=log)
