from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .config import build_image_prompt
from .models import Scene

# Long edge the base image is downscaled to before sending to Gemini —
# uploading a multi-MB original per stage wastes time and input tokens.
UPLOAD_MAX_EDGE = 1536
MAX_PARALLEL = 4


class ImageGenError(RuntimeError):
    pass


def require_google_key() -> None:
    if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        raise ImageGenError(
            "GOOGLE_API_KEY / GEMINI_API_KEY not set. Get a key at "
            "https://aistudio.google.com/apikey and set it with:\n"
            "  $env:GOOGLE_API_KEY = '...'")


def generate_test_images(scenes: list[Scene], base_image: Path,
                         images_dir: Path, ffmpeg: str, log=print) -> None:
    """Cheap test mode: reuse the portrait unchanged for every scene.

    No Gemini calls; the narration subtitles distinguish the stages.
    """
    images_dir.mkdir(parents=True, exist_ok=True)
    for scene in scenes:
        out = images_dir / f"{scene.scene_id}.png"
        scene.visual_style_prompt = f"[test mode] {build_image_prompt(scene.persona)}"
        if out.exists() and out.stat().st_size > 0:
            log(f"  image: {out.name} (cached, test)")
        else:
            out.write_bytes(base_image.read_bytes())
            log(f"  image: {out.name} (test placeholder)")
        scene.image_path = out


def _prepare_upload_image(base_image: Path, images_dir: Path,
                          ffmpeg: str | None) -> tuple[bytes, str]:
    """Downscale the base image once (<= UPLOAD_MAX_EDGE, JPEG) for upload.

    Falls back to the original bytes if ffmpeg is unavailable or fails.
    """
    if ffmpeg:
        from .ffutil import FfmpegError, run_ffmpeg

        prepared = images_dir / "_base_upload.jpg"
        if not (prepared.exists() and prepared.stat().st_size > 0):
            tmp = prepared.with_suffix(".tmp.jpg")
            try:
                run_ffmpeg(ffmpeg, [
                    "-y", "-i", str(base_image),
                    "-vf", (f"scale='min({UPLOAD_MAX_EDGE},iw)':"
                            f"'min({UPLOAD_MAX_EDGE},ih)':"
                            "force_original_aspect_ratio=decrease"),
                    "-q:v", "2", "-frames:v", "1", str(tmp),
                ])
                tmp.replace(prepared)
            except FfmpegError:
                tmp.unlink(missing_ok=True)
                prepared = None
        if prepared and prepared.exists():
            return prepared.read_bytes(), "image/jpeg"
    import mimetypes
    return (base_image.read_bytes(),
            mimetypes.guess_type(str(base_image))[0] or "image/png")


def _generate_one(client, types, model: str, image_bytes: bytes, mime: str,
                  scene: Scene, out: Path) -> Path:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime),
                          scene.visual_style_prompt],
            )
            image_part = None
            for cand in (resp.candidates or []):
                for part in (cand.content.parts or []) if cand.content else []:
                    if part.inline_data and part.inline_data.data:
                        image_part = part.inline_data.data
                        break
                if image_part:
                    break
            if not image_part:
                raise ImageGenError(
                    f"Gemini returned no image for stage '{scene.persona.name}' "
                    "(safety block or text-only reply). Try rewording the style.")
            tmp = out.with_suffix(".tmp")
            tmp.write_bytes(image_part)
            tmp.replace(out)
            return out
        except ImageGenError:
            raise
        except Exception as e:
            last_error = e
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
    raise ImageGenError(
        f"Gemini image generation failed for '{scene.persona.name}': "
        f"{last_error}") from last_error


def generate_scene_images(scenes: list[Scene], base_image: Path, model: str,
                          images_dir: Path, ffmpeg: str | None = None,
                          log=print) -> None:
    """One identity-preserving styled image per scene, from the ORIGINAL base image.

    Independent stages are generated in parallel; the base image is downscaled
    once before upload so every call sends far fewer bytes/tokens.
    """
    images_dir.mkdir(parents=True, exist_ok=True)

    pending = []
    for scene in scenes:
        out = images_dir / f"{scene.scene_id}.png"
        if scene.persona.level <= 1:
            # Level 1 is always the untouched original photo: the video opens
            # with reality, then escalates.
            scene.visual_style_prompt = "[original photo, no generation]"
            if not (out.exists() and out.stat().st_size > 0):
                out.write_bytes(base_image.read_bytes())
            scene.image_path = out
            log(f"  image: {out.name} (original, level 1)")
            continue
        scene.visual_style_prompt = build_image_prompt(scene.persona)
        if out.exists() and out.stat().st_size > 0:
            log(f"  image: {out.name} (cached)")
            scene.image_path = out
        else:
            pending.append((scene, out))
    if not pending:
        return

    require_google_key()
    from google import genai
    from google.genai import types

    client = genai.Client()
    image_bytes, mime = _prepare_upload_image(base_image, images_dir, ffmpeg)

    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL, len(pending))) as pool:
        futures = {
            pool.submit(_generate_one, client, types, model, image_bytes,
                        mime, scene, out): scene
            for scene, out in pending
        }
        errors = []
        for future in as_completed(futures):
            scene = futures[future]
            try:
                scene.image_path = future.result()
                log(f"  image: {scene.image_path.name} ({scene.persona.name})")
            except Exception as e:
                errors.append(e)
        if errors:
            raise errors[0]
