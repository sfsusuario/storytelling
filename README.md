# Escalator — escalating-sophistication video generator

Give it a portrait and a short phrase (e.g. *"Shut that off"*) and it produces a
multi-scene vertical video: each scene shows a style-transformed version of the
portrait while a narrator speaks the phrase rewritten in an escalating register —
from casual person up to sovereign king, galactic emperor, pirate king…
depending on the style set.

Pipeline: **Claude** (text rewrites) → **Gemini** (identity-preserving image
transforms) → **edge-tts** (narration, free) → **ffmpeg** (timing + fades + assembly).

## Quick start (scripts)

```powershell
.\install.ps1     # installs the package + UI deps + ffmpeg, and creates .env
notepad .env      # put your API keys there (loaded automatically)
.\run-cli.ps1     # guided command-line run (asks image, phrase, style set...)
.\run-ui.ps1      # launches the local web UI
```

API keys go in `.env` (see [.env.example](.env.example)) — both the CLI and
the UI load it automatically from the repo root; already-set environment
variables win over `.env` values.

## Manual setup

1. **Python 3.11+** (tested on 3.14; if a dependency wheel misbehaves, create a
   venv with `py -3.12`).

2. **Install** (from the repo root):

   ```powershell
   pip install -e .        # CLI only
   pip install -e .[ui]    # CLI + web UI
   ```

3. **ffmpeg** — any of:

   ```powershell
   winget install Gyan.FFmpeg    # or: choco install ffmpeg (admin shell)
   ```

   or unzip a [static build](https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip)
   into `%LOCALAPPDATA%\ffmpeg\` — the tool finds it there automatically.

4. **API keys** (environment variables or `.env`):

   ```powershell
   $env:GOOGLE_API_KEY    = "..."          # images + (optionally) texts — https://aistudio.google.com/apikey
   $env:ANTHROPIC_API_KEY = "sk-ant-..."   # optional: use Claude for the text rewrites
   ```

   **A single Google key is enough**: with `--text-provider auto` (default),
   texts are written by Claude when `ANTHROPIC_API_KEY` is set and by Gemini
   otherwise. Force one with `--text-provider claude|gemini` (or the *Text
   provider* dropdown in the UI). TTS (edge-tts) needs no key, only internet.

## CLI usage

Only the image and the phrase are required — everything else has defaults:

```powershell
escalate example.png "Shut that off"
```

Common options:

```powershell
escalate example.png "Shut that off" --style-set pirate        # a specific ladder
escalate example.png "Shut that off" --style-set mix --seed 7  # random persona per level, reproducible
escalate example.png "Shut that off" --stages 3                # fewer scenes (keeps lowest+highest)
escalate example.png "Shut that off" --language en             # English output (default is Spanish)
escalate example.png "Apaga eso" --voice es-MX-JorgeNeural     # different narrator voice
escalate --list-style-sets                                     # show all ladders
escalate example.png "Shut that off" --dry-run                 # rewrites + manifest only (no images/video)
escalate example.png "Shut that off" --test-mode               # cheap full video: no Gemini images
```

**Test mode** (`--test-mode`, or the *Test mode* checkbox in the UI) produces a
complete video while spending almost nothing: it skips the Gemini image
generation entirely and reuses your portrait with a stage label on every scene.
Only the single Claude text call is billed; TTS is free. No Google key needed.
Use it to check rewrites, voices, timing and transitions before a real run.

**Phone/TikTok format** is the default: 1080×1920 vertical, and the image
*fills* the frame (`--fit crop`, center-crop). Alternatives:
`--fit blur` (whole photo visible over a blurred background, classic
social-media look) or `--fit pad` (black bars). Use `--resolution 1920x1080`
for landscape output.

**Scene images**: level 1 is always your untouched original photo **and** the
exact original phrase, verbatim — the video opens with reality and escalates
from there. Higher levels are generated with
Gemini preserving the person's identity, pose, action and centered framing;
only wardrobe and surroundings transform into each level's world. The UI also
keeps a **history**: every generated video under `output/` is listed in the
"📼 Historial" section, playable in place with its details and social caption.

**Spanish by default**: rewrites and narration come out in Spanish
(`--language es`), translated from the phrase if needed — switch with
`--language en|pt|fr|...`. The default narrator is an elderly-sounding male
voice (`es-ES-AlvaroNeural` slowed to `-8%` and deepened to `-12Hz`); tune
with `--voice`, `--voice-rate`, `--voice-pitch` or the UI fields.

**Narration subtitles** are burned into every scene by default — progressive,
TikTok-style: short caption chunks appear in sync with the narrator's voice
(word timings come from edge-tts), plus a **level indicator** at the top
("NIVEL 2/5", localized to the run's language). Disable both with
`--no-subtitles` or the UI checkbox. Rewrites **grow with the level**: short and plain at level 1,
progressively longer and more ornate toward the top. Each run also produces a
recommended **social caption + hashtags** (`social.txt`, printed by the CLI
and shown in the UI) ready to paste into TikTok/Reels.

Every scene carries a **watermark** at the bottom-left (`@sfsusers` by
default). Change it per run with `--watermark "@otro"` (or the UI textbox),
disable it with `--no-watermark`, or change the default via
`ESCALATE_WATERMARK` in `.env`.

Full flags: `escalate --help`. Notables: `--styles "A;B;C"` (fully manual
personas), `--resolution 1080x1920`, `--fit {crop,blur,pad}`, `--fps 30`, `--force`,
`--force-from {text,images,tts,render}`, `--reencode-concat`,
`--text-model`, `--image-model`, `--output-dir`, `--seed`.

## Web UI

```powershell
escalate-ui       # or: escalate ui
```

Opens a local Gradio app (http://127.0.0.1:7860): drop an image, type the
phrase, hit **Generate**. All parameters are pre-filled with the same defaults
as the CLI (style set, stages, voice, seed; resolution/fps/models/force under
*Advanced*). Progress streams live and the finished video plays inline.
The UI and CLI share the same engine, output folders, and cache — a UI run and
the equivalent CLI run reuse each other's assets.

## Output

Each run writes to `output/<phrase-slug>-<hash>/`:

```
01_text/rewrites.json    # the escalating rewrites
02_images/scene_NN.png   # styled portraits
03_audio/scene_NN.mp3    # narration per scene
04_clips/scene_NN.mp4    # per-scene clips (inspect these to debug)
final.mp4                # the assembled video (1080x1920 H.264+AAC)
pipeline.json            # full manifest: prompts, scripts, timing map
```

Timing per scene: 0.3 s silence → speech → 0.5 s pause, with a 0.5 s
fade-to-black bridging scenes (the fade lives inside the pauses, so scene
durations are exact). Re-running the same command reuses every cached asset;
same inputs → same output folder.

## Style sets

Seven escalation ladders ship in [config.py](src/escalator/config.py):
`medieval`, `scifi`, `corporate`, `mythology`, `military`, `pirate`, `arcane` —
each 5 personas, level 1→5, always ascending in sophistication. Adding a new
set is one dict entry in `STYLE_SETS`; nothing else changes.
