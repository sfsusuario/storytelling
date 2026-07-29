from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from pathlib import Path

from .models import Persona


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from .env (cwd by default) into os.environ.

    Existing environment variables are never overridden. No dependency needed.
    """
    p = path or Path(".env")
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()

# ---------------------------------------------------------------------------
# Timing constants (seconds) — the core spec of the video format
# ---------------------------------------------------------------------------
AUDIO_TRIGGER_DELAY = 0.3   # silence before speech starts in each scene
SCENE_END_DELAY = 0.5       # silence after speech before the transition
TRANSITION_DURATION = 0.5   # total fade-to-black bridge between scenes
FADE_DURATION = 0.25        # half of the transition lives in each adjacent clip

DEFAULT_TEXT_MODEL = "claude-opus-5"
DEFAULT_GEMINI_TEXT_MODEL = "gemini-2.5-flash"
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"
# Narrador por defecto: voz masculina en español, grave y pausada para sonar
# como una persona mayor (edge-tts no trae voces "ancianas"; se simula con
# pitch y rate).
DEFAULT_VOICE = os.environ.get("ESCALATE_VOICE", "es-ES-AlvaroNeural")
DEFAULT_VOICE_RATE = os.environ.get("ESCALATE_VOICE_RATE", "-8%")
DEFAULT_VOICE_PITCH = os.environ.get("ESCALATE_VOICE_PITCH", "-12Hz")
DEFAULT_LANGUAGE = os.environ.get("ESCALATE_LANGUAGE", "es")
DEFAULT_WATERMARK = os.environ.get("ESCALATE_WATERMARK", "@sfsusers")

LANGUAGE_NAMES = {
    "es": "español",
    "en": "English",
    "pt": "português",
    "fr": "français",
    "de": "Deutsch",
    "it": "italiano",
}

# Word shown in the top-of-frame level indicator, per language
LEVEL_WORDS = {
    "es": "NIVEL", "en": "LEVEL", "pt": "NÍVEL",
    "fr": "NIVEAU", "de": "STUFE", "it": "LIVELLO",
}
DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
DEFAULT_FPS = 30
DEFAULT_STAGES = 5

# Curated edge-tts voices offered in the UI dropdown (any edge-tts voice works via CLI)
CURATED_VOICES = [
    "es-ES-AlvaroNeural",
    "es-MX-JorgeNeural",
    "es-AR-TomasNeural",
    "es-ES-ElviraNeural",
    "es-MX-DaliaNeural",
    "en-US-ChristopherNeural",
    "en-US-GuyNeural",
    "en-US-AriaNeural",
    "en-GB-RyanNeural",
    "en-GB-SoniaNeural",
]

# ---------------------------------------------------------------------------
# Style sets — each is an escalation ladder of 5 personas, level 1 -> 5.
# Adding a new set is just a new dict entry; nothing else changes.
# ---------------------------------------------------------------------------
STYLE_SETS: dict[str, list[Persona]] = {
    "medieval": [
        Persona(1, "Everyday Casual Person",
                "Plain modern everyday speech. Contractions, filler-free but relaxed, "
                "the way a friend would blurt it out.",
                "modern casual clothing (hoodie or t-shirt), an ordinary living room or "
                "street background, soft natural daylight, candid smartphone-photo realism"),
        Persona(2, "Contemporary Intellectual",
                "Measured, articulate modern prose of a public intellectual or philosopher. "
                "Precise vocabulary, a hint of abstraction, calmly persuasive.",
                "turtleneck and tweed blazer, a book-lined study with warm lamplight, "
                "shallow depth of field, refined editorial-portrait photography"),
        Persona(3, "Medieval Nobility",
                "Courtly late-medieval English of a noble. Formal address, elegant phrasing, "
                "genteel words such as 'pray' and 'henceforth'.",
                "rich velvet doublet with gold embroidery and a fur-trimmed cloak, a castle "
                "great hall with tapestries and candelabra, warm candlelight, oil-painting style"),
        Persona(4, "Medieval Knight",
                "Commanding chivalric speech of a sworn knight. Oaths, honor, resolve; "
                "forceful archaic English ('thou shalt', 'by my sword').",
                "polished steel plate armor with a heraldic tabard, a castle courtyard with "
                "banners, dramatic overcast light, epic realistic fantasy painting"),
        Persona(5, "Sovereign King",
                "A royal decree. Majestic plural ('We command'), absolute authority, ornate "
                "proclamation language sealed with finality.",
                "ermine-trimmed royal robes, jeweled crown and scepter, a golden throne room "
                "with stained glass, god-rays of golden light, grand renaissance royal portrait"),
    ],
    "scifi": [
        Persona(1, "Everyday Casual Person",
                "Plain modern everyday speech. Contractions, relaxed, offhand.",
                "modern casual clothing, an ordinary apartment background, soft natural "
                "daylight, candid smartphone-photo realism"),
        Persona(2, "Starship Engineer",
                "Pragmatic technical jargon of a ship engineer. Systems, power couplings, "
                "procedure — clipped and competent.",
                "utilitarian engineering jumpsuit with tool harness, a starship engine room "
                "with glowing conduits, cool teal practical lighting, gritty sci-fi realism"),
        Persona(3, "Fleet Officer",
                "Crisp naval-style professionalism of a bridge officer. Protocol, rank, "
                "formal directives.",
                "fitted fleet officer uniform with rank insignia, a starship bridge with "
                "holographic displays, clean white-blue lighting, polished cinematic sci-fi"),
        Persona(4, "Fleet Admiral",
                "Weighty strategic authority of a fleet admiral. Grand-scale vocabulary, "
                "orders that move armadas.",
                "decorated admiral dress uniform with medals and command cape, a flagship "
                "war room overlooking a fleet through a viewport, dramatic rim lighting, "
                "epic sci-fi concept art"),
        Persona(5, "Galactic Emperor",
                "Absolute imperial decree spanning star systems. Cosmic scope, cold majesty, "
                "the voice of an empire.",
                "obsidian-and-gold imperial regalia with a high collar and luminous sigils, "
                "a colossal throne hall aboard a star fortress with a galaxy visible beyond, "
                "otherworldly backlighting, majestic sci-fi splash art"),
    ],
    "corporate": [
        Persona(1, "Intern",
                "Eager, slightly nervous office-newbie speech. Apologetic hedges, "
                "upbeat informality.",
                "wrinkled business-casual shirt with a lanyard ID badge, an open-plan office "
                "cubicle with sticky notes, flat fluorescent lighting, candid office photo"),
        Persona(2, "Middle Manager",
                "Meeting-speak with light corporate jargon: 'align', 'circle back', "
                "'action this'. Polite but directive.",
                "off-the-rack suit without tie, a glass meeting room with a whiteboard, "
                "neutral office lighting, corporate stock-photo realism"),
        Persona(3, "Executive",
                "Polished executive communication. Strategic vocabulary, confident brevity, "
                "boardroom gravitas.",
                "tailored designer suit with a silk tie, a corner office with a city view, "
                "warm late-afternoon window light, premium editorial business portrait"),
        Persona(4, "CEO",
                "Visionary keynote authority. Sweeping declarations about markets and "
                "the future, quotable and absolute.",
                "immaculate black suit, a keynote stage with a giant screen and spotlights, "
                "dramatic stage lighting, high-contrast press-photo style"),
        Persona(5, "Global Tycoon",
                "Olympian pronouncements of someone who owns industries. Detached, "
                "world-shaping language, empire-scale certainty.",
                "bespoke three-piece suit with a gold pocket watch, a penthouse overlooking "
                "the city at night beside a private jet window, moody cinematic low-key "
                "lighting, opulent magazine-cover portrait"),
    ],
    "mythology": [
        Persona(1, "Village Peasant",
                "Humble, earthy rural speech. Simple words, homespun comparisons.",
                "rough-spun linen tunic, a rustic ancient village with clay houses and "
                "chickens, dusty golden-hour light, classical genre-painting realism"),
        Persona(2, "Temple Priest",
                "Reverent liturgical speech. Blessings, omens, invocations of the gods.",
                "white ceremonial robes with a laurel wreath, a marble temple interior with "
                "incense smoke and braziers, soft shafts of light, neoclassical painting"),
        Persona(3, "Demigod Hero",
                "Boastful epic-hero speech in the style of sung legend. Deeds, glory, "
                "destiny.",
                "bronze heroic armor with a lion-skin cloak, a storm-lashed cliff over a "
                "wine-dark sea, dramatic storm light, epic classical mythology painting"),
        Persona(4, "Olympian God",
                "Thunderous divine proclamation. Speaks of mortals from above, "
                "elemental imagery.",
                "flowing god-robes with a radiant aura and golden armbands, the clouded "
                "peak of Olympus with distant earth below, blinding divine light from above, "
                "grand baroque mythological painting"),
        Persona(5, "Supreme Deity",
                "The voice that shaped creation. Absolute cosmic decree, time and fate "
                "as instruments.",
                "robes woven from starlight and cosmos, an abyss of galaxies and nebulae "
                "bending around the figure, luminous celestial radiance, transcendent "
                "cosmic-divine artwork"),
    ],
    "military": [
        Persona(1, "Fresh Recruit",
                "Jumpy, unsure recruit speech. Short sentences, a nervous 'sir' or two.",
                "ill-fitting basic fatigues and a buzz cut, a muddy boot-camp training yard, "
                "flat gray morning light, documentary photo realism"),
        Persona(2, "Drill Sergeant",
                "Barked drill-sergeant cadence. All command, zero patience, "
                "parade-ground volume in text form.",
                "crisp camouflage uniform with a campaign hat, a barracks parade ground "
                "with recruits in the background, harsh midday sun, sharp military photography"),
        Persona(3, "Field Captain",
                "Terse tactical briefing language. Objectives, coordinates, controlled "
                "urgency.",
                "combat gear with captain's bars over a map table, a forward command tent "
                "with radios, warm lantern light at dusk, gritty war-film cinematography"),
        Persona(4, "General",
                "Grave strategic authority of a theater commander. History-aware, "
                "measured, iron certainty.",
                "dress uniform heavy with service ribbons and stars, a war room with maps "
                "and aides, low dramatic lighting, formal command portrait"),
        Persona(5, "Supreme Commander",
                "Address to nations. Doctrine-defining, absolute, the full weight of "
                "every army behind each word.",
                "immaculate supreme-commander regalia with gold braid and a greatcoat over "
                "the shoulders, a monumental headquarters balcony above massed formations, "
                "epic sunset backlighting, heroic propaganda-poster grandeur"),
    ],
    "pirate": [
        Persona(1, "Deckhand",
                "Green deckhand grumbling. Simple sea-slang, informal, a bit whiny.",
                "ragged striped shirt and rope belt, a swabbed ship deck with buckets and "
                "rigging, overcast sea light, weathered maritime realism"),
        Persona(2, "Seasoned Sailor",
                "Salty veteran sailor talk. Nautical slang, superstitions, easy confidence.",
                "worn leather vest, bandana and small gold earring, the ship's rail with open "
                "ocean behind, bright trade-wind sunlight, adventure-novel illustration"),
        Persona(3, "First Mate",
                "Firm quarterdeck authority just below the captain. Orders the crew, "
                "invokes the captain's will.",
                "long navy coat with brass buttons and a tricorn under the arm, the "
                "quarterdeck wheel at golden hour, warm dramatic light, romantic maritime "
                "painting"),
        Persona(4, "Pirate Captain",
                "Flamboyant pirate-captain menace. Theatrical threats, treasure and "
                "gallows imagery, rolling rhetoric.",
                "extravagant captain's coat with gold trim, plumed hat and cutlass, the "
                "captain's cabin with charts and candlelit treasure, moody candlelight, "
                "swashbuckling cinematic painting"),
        Persona(5, "Pirate King",
                "Sovereign of all free seas. Decrees to every ship afloat, myth-scale "
                "swagger and dominion.",
                "obsidian-black regalia crowned with a jeweled skull diadem, a throne of "
                "anchors and figureheads in a grotto of plundered gold, torchlit with "
                "emerald sea-glow, legendary dark-fantasy seascape art"),
    ],
    "arcane": [
        Persona(1, "Curious Apprentice",
                "Excitable apprentice chatter. Half-understood terms, wide-eyed wonder.",
                "ink-stained novice robes with an overstuffed satchel of scrolls, a cluttered "
                "wizard's workshop, warm candlelight, cinematic fantasy realism with "
                "storybook charm"),
        Persona(2, "Scholar Mage",
                "Precise academic magical terminology. Cites principles and treatises, "
                "lecture-hall cadence.",
                "neat scholarly robes with a silver amulet, a grand arcane library with "
                "floating books, cool moonlit windows and candle glow, detailed fantasy "
                "illustration"),
        Persona(3, "Archmage",
                "Authoritative high-magic speech. Wields terminology like instruments, "
                "quiet immense power.",
                "layered archmage vestments with glowing runes and an ornate staff, a "
                "sanctum with orbiting crystals and sigils in the air, arcane blue-violet "
                "light, painterly epic fantasy"),
        Persona(4, "Sorcerer Lord",
                "Imperious dark-sovereign proclamation. Dominion over forces and realms, "
                "veiled threat in every clause.",
                "regal sorcerer-lord armor-robes with a floating crown of shards, a citadel "
                "balcony over a storm of raw magic, crackling violet storm light, dramatic "
                "dark-fantasy concept art"),
        Persona(5, "God of Magic",
                "The primal voice of magic itself. Reality-defining decree, laws of nature "
                "as clauses.",
                "a form woven of pure spell-light and constellations, an infinite astral "
                "plane of runic rings and shattered realities, blinding prismatic radiance, "
                "transcendent cosmic fantasy masterpiece"),
    ],
}

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------
REWRITE_SYSTEM_TEMPLATE = """\
You rewrite a short phrase into escalating registers for a social-media video.
Rules:
- Preserve the core meaning and intent of the original phrase exactly.
- Each rewrite must match its persona's tone, vocabulary, and syntactic complexity,
  and sophistication must strictly increase from stage 1 to the last stage.
- Length grows with sophistication: stage 1 is short and plain (roughly 5-10
  words); each stage gets a little longer and more elaborate than the previous
  one; the final stage may reach two sentences (roughly 25-35 words). Keep it
  speakable and punchy — longer and more refined, but never rambling.
- The rewrites will be read aloud by a TTS narrator: no stage directions, no
  quotation marks, no emojis, no markdown — just the spoken words.
- Write EVERY rewrite in {language}, translating from the original phrase's
  language if needed.

Also produce a social post for the finished video (TikTok/Reels/Shorts):
- caption: ONE very short, punchy line in {language} — a hook that makes
  people watch to the end (the video shows the same person saying the phrase
  with increasing sophistication). No emojis spam: at most one or two.
- hashtags: 6-8 tags, no # symbol, mixing broad viral tags and niche ones,
  in {language} and English where it helps reach.
"""


def build_rewrite_system_prompt(language: str) -> str:
    return REWRITE_SYSTEM_TEMPLATE.format(
        language=LANGUAGE_NAMES.get(language, language))

REWRITE_USER_TEMPLATE = """\
Original phrase: "{phrase}"

Rewrite it once per stage below:
{stage_lines}
"""

IMAGE_PROMPT_TEMPLATE = """\
Transform this portrait into: {name} (sophistication level {level} of 5).

IDENTITY — non-negotiable: it must be the SAME person. Keep their face, facial \
structure, eyes, skin tone and recognizable likeness intact; anyone who knows \
them should recognize them instantly. Render the face with photographic \
fidelity to the reference photo even when the scene, clothing and background \
are stylized or painterly — NEVER cartoonify, caricature or redraw the face.

EVERYTHING ELSE — be bold and creative: fully reimagine the wardrobe, props, \
pose, attitude and expression nuance so they EMBODY this persona; rebuild the \
background and setting as a rich, detailed world that belongs to this level; \
use dramatic lighting and an art style true to the persona. The grandeur and \
production value should feel appropriate to rank {level} of 5 — humble and \
mundane at low levels, epic and magnificent at high levels.

This level's world: {image_detail}.

Vertical portrait composition, subject prominent, cinematic quality.\
"""


def build_image_prompt(persona: Persona) -> str:
    return IMAGE_PROMPT_TEMPLATE.format(
        name=persona.name, level=persona.level,
        image_detail=persona.image_detail)


# ---------------------------------------------------------------------------
# Options shared by CLI and UI — single source of defaults
# ---------------------------------------------------------------------------
@dataclass
class PipelineOptions:
    base_image: Path = None  # required
    phrase: str = ""         # required
    style_set: str = "random"            # set name | "random" | "mix"
    seed: int | None = None
    stages: int = DEFAULT_STAGES
    styles: list[str] | None = None      # manual persona-name override, bypasses sets
    voice: str = DEFAULT_VOICE
    voice_rate: str = DEFAULT_VOICE_RATE     # e.g. "-8%" (slower = older)
    voice_pitch: str = DEFAULT_VOICE_PITCH   # e.g. "-12Hz" (deeper = older)
    language: str = DEFAULT_LANGUAGE         # language of rewrites + narration
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    fps: int = DEFAULT_FPS
    fit: str = "crop"                    # crop (TikTok fill) | blur | pad
    watermark: str = DEFAULT_WATERMARK   # bottom-left text; "" disables it
    subtitles: bool = True               # burn narration subtitles into the video
    output_dir: Path | None = None       # default derived from input hash
    dry_run: bool = False
    test_mode: bool = False              # skip Gemini images: cheap run (Claude + free TTS only)
    force: bool = False
    force_from: str | None = None        # text | images | tts | render
    reencode_concat: bool = False
    text_provider: str = "auto"          # auto | claude | gemini
    text_model: str = DEFAULT_TEXT_MODEL
    image_model: str = DEFAULT_IMAGE_MODEL


# ---------------------------------------------------------------------------
# Persona resolution: set / random / mix / manual, with even-spacing for N<5
# ---------------------------------------------------------------------------
def _spaced_indices(total: int, count: int) -> list[int]:
    if count >= total:
        return list(range(total))
    if count == 1:
        return [total - 1]
    return [round(i * (total - 1) / (count - 1)) for i in range(count)]


def resolve_personas(options: PipelineOptions) -> tuple[str, list[Persona]]:
    """Return (set_label, personas) for this run. Deterministic given options.seed."""
    if options.styles:
        personas = [
            Persona(level=i + 1, name=name.strip(),
                    register=f"Speak fully in character as: {name.strip()}. "
                             f"Sophistication level {i + 1} of {len(options.styles)}.",
                    image_detail=f"clothing, background, lighting and art style that fully "
                                 f"embody: {name.strip()}")
            for i, name in enumerate(options.styles)
        ]
        return "custom", personas

    rng = random.Random(options.seed)
    if options.style_set == "mix":
        levels = _spaced_indices(5, min(options.stages, 5))
        personas = [rng.choice([s[lv] for s in STYLE_SETS.values()]) for lv in levels]
        return "mix", personas

    if options.style_set == "random":
        set_name = rng.choice(sorted(STYLE_SETS))
    else:
        set_name = options.style_set
        if set_name not in STYLE_SETS:
            raise ValueError(
                f"Unknown style set '{set_name}'. "
                f"Available: {', '.join(sorted(STYLE_SETS))}, random, mix")
    ladder = STYLE_SETS[set_name]
    if options.stages > len(ladder):
        raise ValueError(
            f"--stages {options.stages} exceeds the {len(ladder)} levels of set "
            f"'{set_name}'; pass an explicit --styles list instead")
    personas = [ladder[i] for i in _spaced_indices(len(ladder), options.stages)]
    return set_name, personas
