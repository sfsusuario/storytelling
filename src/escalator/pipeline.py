from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Callable

from . import config
from .config import LEVEL_WORDS, PipelineOptions, resolve_personas
from .ffutil import require_ffmpeg
from .models import Persona, Scene
from .timeline import build_timeline
from .manifest import write_manifest

Progress = Callable[[str], None]

# Stage dependency chain for --force-from: text -> {images, tts} -> render
_STAGE_INVALIDATES = {
    "text": ["01_text", "02_images", "03_audio", "04_clips", "final.mp4"],
    "images": ["02_images", "04_clips", "final.mp4"],
    "tts": ["03_audio", "04_clips", "final.mp4"],
    "render": ["04_clips", "final.mp4"],
}


class PipelineResult:
    def __init__(self, output_dir: Path, manifest_path: Path,
                 final_video: Path | None, style_set: str,
                 personas: list[Persona], social: str = ""):
        self.output_dir = output_dir
        self.manifest_path = manifest_path
        self.final_video = final_video
        self.style_set = style_set
        self.personas = personas
        self.social = social


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:32] or "run"


def default_output_dir(options: PipelineOptions, personas: list[Persona]) -> Path:
    h = hashlib.sha256()
    h.update(options.phrase.encode("utf-8"))
    h.update("|".join(p.name for p in personas).encode("utf-8"))
    h.update(f"{options.width}x{options.height}@{options.fps}|{options.voice}"
             f"|{options.voice_rate}|{options.voice_pitch}|{options.language}"
             f"|{options.fit}|{options.watermark}|subs={options.subtitles}".encode())
    if options.test_mode:
        h.update(b"|test-mode")
    h.update(Path(options.base_image).read_bytes())
    return Path("output") / f"{_slugify(options.phrase)}-{h.hexdigest()[:8]}"


def _estimate_duration(text: str) -> float:
    return max(1.0, len(text.split()) / 2.5)


def _apply_force(output_dir: Path, options: PipelineOptions, log: Progress) -> None:
    if options.force:
        targets = _STAGE_INVALIDATES["text"]
    elif options.force_from:
        targets = _STAGE_INVALIDATES[options.force_from]
    else:
        return
    for name in targets:
        target = output_dir / name
        if target.is_dir():
            shutil.rmtree(target)
            log(f"  force: cleared {name}/")
        elif target.is_file():
            target.unlink()
            log(f"  force: cleared {name}")


def run_pipeline(options: PipelineOptions,
                 on_progress: Progress = print) -> PipelineResult:
    log = on_progress

    base_image = Path(options.base_image)
    if not base_image.is_file():
        raise FileNotFoundError(f"Base image not found: {base_image}")
    if not options.phrase.strip():
        raise ValueError("Phrase must not be empty")

    style_set, personas = resolve_personas(options)
    log(f"style set: {style_set} -> " + " / ".join(p.name for p in personas))

    scenes = [
        Scene(index=i + 1, scene_id=f"scene_{i + 1:02d}", persona=p,
              visual_style_prompt=config.build_image_prompt(p),
              audio_trigger_delay=config.AUDIO_TRIGGER_DELAY,
              scene_end_delay=config.SCENE_END_DELAY)
        for i, p in enumerate(personas)
    ]

    output_dir = Path(options.output_dir) if options.output_dir \
        else default_output_dir(options, personas)
    output_dir.mkdir(parents=True, exist_ok=True)
    log(f"output dir: {output_dir}")
    _apply_force(output_dir, options, log)

    ffmpeg = ffprobe = None
    if not options.dry_run:
        ffmpeg, ffprobe = require_ffmpeg()

    # Stage 1: text rewrites (Claude or Gemini)
    from .text_gen import generate_rewrites, resolve_text_backend
    provider, text_model = resolve_text_backend(options.text_provider,
                                                options.text_model)
    options.text_provider, options.text_model = provider, text_model
    log(f"[1/5] text rewrites ({provider}: {text_model})")
    rewrites, social = generate_rewrites(options.phrase, personas, text_model,
                                         output_dir / "01_text",
                                         provider=provider,
                                         language=options.language)
    for scene, rewrite in zip(scenes, rewrites):
        scene.speech_script = rewrite
        log(f'  L{scene.persona.level} {scene.persona.name}: "{rewrite}"')
    if social:
        (output_dir / "social.txt").write_text(social, encoding="utf-8")

    if options.dry_run:
        for scene in scenes:
            scene.audio_duration = _estimate_duration(scene.speech_script)
        timeline = build_timeline(scenes, options.width, options.height,
                                  options.fps, options.fit, options.watermark,
                                  options.subtitles,
                                  LEVEL_WORDS.get(options.language, "NIVEL"))
        manifest_path = write_manifest(options, timeline, style_set, output_dir,
                                       dry_run=True)
        log(f"[dry-run] manifest: {manifest_path}")
        return PipelineResult(output_dir, manifest_path, None, style_set,
                              personas, social)

    # Stage 2: styled images (Gemini) — or cheap placeholders in test mode
    if options.test_mode:
        from .image_gen import generate_test_images
        log("[2/5] images (TEST MODE: no Gemini, reusing portrait)")
        generate_test_images(scenes, base_image, output_dir / "02_images",
                             ffmpeg, log=log)
    else:
        from .image_gen import generate_scene_images
        log(f"[2/5] images ({options.image_model})")
        generate_scene_images(scenes, base_image, options.image_model,
                              output_dir / "02_images", ffmpeg=ffmpeg, log=log)

    # Stage 3: TTS + durations
    from .tts import synthesize_scenes
    log(f"[3/5] tts ({options.voice})")
    synthesize_scenes(scenes, options.voice, output_dir / "03_audio",
                      ffprobe, rate=options.voice_rate,
                      pitch=options.voice_pitch, log=log)

    # Stage 4: timeline
    timeline = build_timeline(scenes, options.width, options.height,
                              options.fps, options.fit, options.watermark,
                              options.subtitles,
                              LEVEL_WORDS.get(options.language, "NIVEL"))
    log(f"[4/5] timeline: {timeline.total_duration:.2f}s total")

    # Stage 5: render
    from .renderer import render_all
    log("[5/5] render")
    final_path = render_all(ffmpeg, timeline, output_dir / "04_clips",
                            output_dir / "final.mp4",
                            reencode=options.reencode_concat, log=log)

    manifest_path = write_manifest(options, timeline, style_set, output_dir,
                                   dry_run=False)
    log(f"done: {final_path}")
    return PipelineResult(output_dir, manifest_path, final_path, style_set,
                          personas, social)
