from __future__ import annotations

import os
import queue
import threading
from pathlib import Path

from .config import (CURATED_VOICES, DEFAULT_FPS, DEFAULT_HEIGHT,
                     DEFAULT_IMAGE_MODEL, DEFAULT_LANGUAGE, DEFAULT_STAGES,
                     DEFAULT_TEXT_MODEL, DEFAULT_VOICE, DEFAULT_VOICE_PITCH,
                     DEFAULT_VOICE_RATE, DEFAULT_WATERMARK, LANGUAGE_NAMES,
                     STYLE_SETS, DEFAULT_WIDTH, PipelineOptions)

_SET_LABELS_ES = {
    "medieval": "medieval", "scifi": "ciencia ficción", "corporate": "corporativo",
    "mythology": "mitología", "military": "militar", "pirate": "piratas",
    "arcane": "magia arcana",
}


def _style_set_choices() -> list[str]:
    return (["random (un set al azar)", "mix (mezcla por niveles)"]
            + sorted(STYLE_SETS))


def _style_set_info() -> str:
    lines = [f"**{name}** ({_SET_LABELS_ES.get(name, name)}): "
             + " → ".join(p.name for p in STYLE_SETS[name])
             for name in sorted(STYLE_SETS)]
    return ("*random* elige un set completo al azar; *mix* elige un personaje "
            "aleatorio por nivel (siempre ascendente).\n\n" + "\n\n".join(lines))


def _language_choices() -> list[str]:
    return [f"{code} — {name}" for code, name in LANGUAGE_NAMES.items()]


def build_app():
    import gradio as gr

    def generate(image_path, phrase, style_set, stages, language, voice,
                 seed, test_mode, subtitles, watermark, text_provider, fit,
                 resolution, fps, voice_rate, voice_pitch, text_model,
                 image_model, force, output_dir):
        if not image_path:
            raise gr.Error("Sube primero una imagen de retrato.")
        if not phrase or not phrase.strip():
            raise gr.Error("Escribe la frase a escalar.")
        have_claude = bool(os.environ.get("ANTHROPIC_API_KEY"))
        have_google = bool(os.environ.get("GOOGLE_API_KEY")
                           or os.environ.get("GEMINI_API_KEY"))
        provider = str(text_provider).split(" ")[0]
        if provider == "claude" and not have_claude:
            raise gr.Error("ANTHROPIC_API_KEY no está configurada. Ponla en "
                           ".env (o cambia el proveedor de texto a "
                           "auto/gemini) y reinicia.")
        if provider == "gemini" and not have_google:
            raise gr.Error("GOOGLE_API_KEY / GEMINI_API_KEY no está "
                           "configurada. Ponla en .env y reinicia.")
        if provider == "auto" and not (have_claude or have_google):
            raise gr.Error("No hay ninguna clave de API: pon ANTHROPIC_API_KEY "
                           "(Claude) o GOOGLE_API_KEY / GEMINI_API_KEY "
                           "(Gemini) en .env y reinicia.")
        if not test_mode and not have_google:
            raise gr.Error("GOOGLE_API_KEY / GEMINI_API_KEY no está "
                           "configurada (necesaria para las imágenes "
                           "estilizadas). Ponla en .env, o marca 'Modo "
                           "prueba' para una ejecución barata sin imágenes IA.")
        try:
            width, height = (int(x) for x in str(resolution).lower().split("x"))
        except ValueError:
            raise gr.Error(f"Resolución inválida '{resolution}', formato AnchoxAlto")

        options = PipelineOptions(
            base_image=Path(image_path),
            phrase=phrase.strip(),
            style_set=str(style_set).split(" ")[0],
            seed=int(seed) if seed not in (None, "") else None,
            stages=int(stages),
            voice=voice,
            voice_rate=voice_rate or "+0%",
            voice_pitch=voice_pitch or "+0Hz",
            language=str(language).split(" ")[0],
            width=width, height=height, fps=int(fps),
            fit=str(fit).split(" ")[0],
            watermark=(watermark or "").strip(),
            subtitles=bool(subtitles),
            output_dir=Path(output_dir) if output_dir else None,
            test_mode=bool(test_mode),
            text_provider=provider,
            force=bool(force),
            text_model=text_model,
            image_model=image_model,
        )

        from .pipeline import run_pipeline

        q: queue.Queue = queue.Queue()
        holder: dict = {}

        def worker():
            try:
                holder["result"] = run_pipeline(options, on_progress=q.put)
            except Exception as e:  # surfaced as gr.Error below
                holder["error"] = e
            finally:
                q.put(None)

        threading.Thread(target=worker, daemon=True).start()
        lines: list[str] = []
        while True:
            item = q.get()
            if item is None:
                break
            lines.append(str(item))
            yield "\n".join(lines), None, gr.skip(), gr.skip()

        if "error" in holder:
            raise gr.Error(str(holder["error"]))
        result = holder["result"]
        personas = "\n".join(f"  N{p.level} — {p.name}" for p in result.personas)
        summary = (f"Set de estilos: {result.style_set}\n{personas}\n\n"
                   f"Carpeta:    {result.output_dir.resolve()}\n"
                   f"Manifiesto: {result.manifest_path.resolve()}")
        lines.append("¡listo!")
        yield ("\n".join(lines), str(result.final_video), summary,
               result.social or "")

    with gr.Blocks(title="Escalator — generador de videos") as demo:
        gr.Markdown(
            "# 🎬 Escalator\n"
            "Retrato + frase → video vertical con narración que **escala de "
            "sofisticación** escena a escena. Los valores por defecto "
            "funcionan tal cual: sube una imagen, escribe la frase y pulsa "
            "**Generar**.")
        with gr.Row(equal_height=False):
            # ------------------------- entrada -------------------------
            with gr.Column(scale=5):
                image = gr.Image(label="Retrato", type="filepath", height=260)
                phrase = gr.Textbox(
                    label="Frase", placeholder='p. ej. "Apaga eso"', lines=1)
                test_mode = gr.Checkbox(
                    value=False,
                    label="Modo prueba — ejecución barata (sin imágenes IA)",
                    info="Reutiliza el retrato con una etiqueta por nivel. "
                         "Solo gasta la llamada de texto; ideal para probar "
                         "sin consumir créditos.")
                go = gr.Button("🎬 Generar video", variant="primary", size="lg")

                with gr.Group():
                    gr.Markdown("**Parámetros** *(todos con valores por defecto)*")
                    with gr.Row():
                        style_set = gr.Dropdown(
                            _style_set_choices(),
                            value="random (un set al azar)",
                            label="Set de estilos")
                        stages = gr.Slider(2, DEFAULT_STAGES,
                                           value=DEFAULT_STAGES, step=1,
                                           label="Escenas")
                    with gr.Row():
                        language = gr.Dropdown(
                            _language_choices(),
                            value=f"{DEFAULT_LANGUAGE} — "
                                  f"{LANGUAGE_NAMES[DEFAULT_LANGUAGE]}",
                            label="Idioma (textos y narración)")
                        voice = gr.Dropdown(
                            CURATED_VOICES, value=DEFAULT_VOICE,
                            label="Voz del narrador",
                            info="Por defecto: voz mayor, grave y pausada")
                    with gr.Row():
                        watermark = gr.Textbox(
                            value=DEFAULT_WATERMARK,
                            label="Marca de agua (abajo-izquierda)",
                            info="Vacío = sin marca")
                        seed = gr.Number(label="Seed (vacío = aleatorio)",
                                         value=None, precision=0)
                    subtitles = gr.Checkbox(
                        value=True, label="Subtítulos de la narración",
                        info="Incrusta el texto narrado en cada escena")

                with gr.Accordion("Avanzado", open=False):
                    text_provider = gr.Dropdown(
                        ["auto (Claude si hay clave, si no Gemini)",
                         "claude", "gemini"],
                        value="auto (Claude si hay clave, si no Gemini)",
                        label="Proveedor de texto",
                        info="Con 'gemini' basta la clave de Google")
                    fit = gr.Dropdown(
                        ["crop (llena la pantalla, estilo TikTok)",
                         "blur (fondo difuminado)", "pad (bandas negras)"],
                        value="crop (llena la pantalla, estilo TikTok)",
                        label="Relleno del encuadre")
                    with gr.Row():
                        resolution = gr.Textbox(
                            value=f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}",
                            label="Resolución (AnchoxAlto)")
                        fps = gr.Number(value=DEFAULT_FPS, label="FPS",
                                        precision=0)
                    with gr.Row():
                        voice_rate = gr.Textbox(
                            value=DEFAULT_VOICE_RATE, label="Velocidad de voz",
                            info="p. ej. -8% (más lenta = más mayor)")
                        voice_pitch = gr.Textbox(
                            value=DEFAULT_VOICE_PITCH, label="Tono de voz",
                            info="p. ej. -12Hz (más grave = más mayor)")
                    text_model = gr.Textbox(value=DEFAULT_TEXT_MODEL,
                                            label="Modelo de texto")
                    image_model = gr.Textbox(value=DEFAULT_IMAGE_MODEL,
                                             label="Modelo de imagen (Gemini)")
                    force = gr.Checkbox(
                        label="Forzar regeneración (ignorar caché)")
                    output_dir = gr.Textbox(
                        label="Carpeta de salida (vacío = automática)")

                with gr.Accordion("Sets de estilos disponibles", open=False):
                    gr.Markdown(_style_set_info())

            # ------------------------- salida --------------------------
            with gr.Column(scale=7):
                video = gr.Video(label="Video final", height=560)
                social = gr.Textbox(
                    label="📣 Descripción y hashtags para TikTok/redes",
                    lines=4, interactive=False,
                    info="Copia y pega al publicar (también en social.txt)")
                summary = gr.Textbox(label="Resumen de la ejecución", lines=6,
                                     interactive=False)
                with gr.Accordion("Progreso", open=True):
                    log = gr.Textbox(show_label=False, lines=10, max_lines=14,
                                     interactive=False)

        go.click(generate,
                 inputs=[image, phrase, style_set, stages, language, voice,
                         seed, test_mode, subtitles, watermark, text_provider,
                         fit, resolution, fps, voice_rate, voice_pitch,
                         text_model, image_model, force, output_dir],
                 outputs=[log, video, summary, social])
    return demo


def main() -> int:
    try:
        import gradio  # noqa: F401
    except ImportError:
        print("La interfaz necesita gradio. Instálalo con:\n"
              "  pip install -e .[ui]")
        return 1
    import gradio as gr
    build_app().launch(
        inbrowser=True,
        theme=gr.themes.Soft(primary_hue="orange", neutral_hue="stone"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
