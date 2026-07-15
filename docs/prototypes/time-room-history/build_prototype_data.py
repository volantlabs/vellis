from __future__ import annotations

# The reviewed historical seed is intentionally kept as readable inline prose.
# ruff: noqa: E501
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

CURRENT_DIR = Path(__file__).resolve().parent
DATA_DIR = CURRENT_DIR / "data"
QUERY_DIR = DATA_DIR / "queries"
SCHEMA_CALL_PATH = DATA_DIR / "time-room-history-schema-v0.json"
LIVE_RECORDS_PATH = DATA_DIR / "ada-lovelace-live-records.json"

NAMESPACE = UUID("594c1c66-a2d2-4c18-a0bf-99d499ed16f1")
GRAPH_ID = "time_room_history"
SNAPSHOT_PATH = "snapshots/time-room-history-alpha.json"
RUNTIME_PACK_KEY = "ada-lovelace-alpha"


SOURCES: tuple[dict[str, str], ...] = (
    {
        "key": "science-museum-women-computing",
        "title": "Women in Computing: Ada Lovelace",
        "provider": "Science Museum",
        "url": "https://www.sciencemuseum.org.uk/objects-and-stories/women-computing",
        "source_kind": "museum historical overview",
        "verification_status": "reviewed",
        "publication_note": "Authoritative museum synthesis with collection context and a bounded account of Lovelace's education, collaboration, notes, and Bernoulli-number procedure.",
    },
    {
        "key": "science-museum-difference-engines",
        "title": "Charles Babbage's Difference Engines and the Science Museum",
        "provider": "Science Museum",
        "url": "https://www.sciencemuseum.org.uk/objects-and-stories/charles-babbages-difference-engines-and-science-museum",
        "source_kind": "museum object and history essay",
        "verification_status": "reviewed",
        "publication_note": "Authoritative museum account of the engines, their physical state, and Lovelace's role in interpreting the Analytical Engine.",
    },
    {
        "key": "chm-babbage-history",
        "title": "Babbage Engine: A Brief History",
        "provider": "Computer History Museum",
        "url": "https://www.computerhistory.org/babbage/history/",
        "source_kind": "museum technical history",
        "verification_status": "reviewed",
        "publication_note": "Museum history of the Difference and Analytical Engines, including store, mill, punched cards, and Lovelace's 1843 publication.",
    },
    {
        "key": "chm-ada-lovelace",
        "title": "Ada Lovelace",
        "provider": "Computer History Museum",
        "url": "https://www.computerhistory.org/babbage/adalovelace",
        "source_kind": "museum biographical exhibit",
        "verification_status": "reviewed",
        "publication_note": "Concise museum biography covering family, education, meeting Babbage, and the Menabrea translation with extensive notes.",
    },
    {
        "key": "gutenberg-analytical-engine",
        "title": "Sketch of the Analytical Engine invented by Charles Babbage",
        "provider": "Project Gutenberg",
        "url": "https://www.gutenberg.org/files/75107/75107-h/75107-h.htm",
        "source_kind": "digitized 1843 primary publication",
        "verification_status": "reviewed",
        "publication_note": "Public-domain transcription of Menabrea's paper translated by Ada King, Countess of Lovelace, with her Notes A-G. Runtime uses paraphrases and source markers rather than long quotations.",
    },
    {
        "key": "bodleian-lovelace-archive",
        "title": "Archive of the Noel, Byron and Lovelace Families",
        "provider": "Bodleian Libraries",
        "url": "https://archives.bodleian.ox.ac.uk/repositories/2/resources/3228",
        "source_kind": "archival finding aid",
        "verification_status": "reviewed",
        "publication_note": "Archival provenance for family correspondence and Lovelace papers. The finding aid notes permission restrictions; no archival body text is reproduced in the runtime pack.",
    },
)


ENTITIES: tuple[dict[str, str], ...] = (
    {
        "key": "ada-lovelace",
        "name": "Ada Lovelace",
        "kind": "person",
        "summary": "English mathematician and writer associated with the Analytical Engine.",
    },
    {
        "key": "charles-babbage",
        "name": "Charles Babbage",
        "kind": "person",
        "summary": "Designer of the Difference and Analytical Engines and Lovelace's collaborator.",
    },
    {
        "key": "mary-somerville",
        "name": "Mary Somerville",
        "kind": "person",
        "summary": "Scientific writer and mathematician who introduced Lovelace to Babbage.",
    },
    {
        "key": "augustus-de-morgan",
        "name": "Augustus De Morgan",
        "kind": "person",
        "summary": "Mathematician who tutored Lovelace through correspondence.",
    },
    {
        "key": "luigi-menabrea",
        "name": "Luigi Menabrea",
        "kind": "person",
        "summary": "Italian engineer whose French paper on the Analytical Engine Lovelace translated.",
    },
    {
        "key": "difference-engine",
        "name": "Difference Engine",
        "kind": "machine",
        "summary": "Babbage's specialized mechanical calculating engine for mathematical tables.",
    },
    {
        "key": "analytical-engine",
        "name": "Analytical Engine",
        "kind": "machine",
        "summary": "Babbage's unrealized programmable general-purpose mechanical computing design.",
    },
    {
        "key": "punched-cards",
        "name": "Punched cards",
        "kind": "technology",
        "summary": "Card-based instructions and data proposed for controlling the Analytical Engine.",
    },
    {
        "key": "bernoulli-numbers",
        "name": "Bernoulli numbers",
        "kind": "mathematical concept",
        "summary": "A number sequence used in Lovelace's Note G procedure.",
    },
    {
        "key": "scientific-memoirs",
        "name": "Scientific Memoirs, volume 3",
        "kind": "publication",
        "summary": "The 1843 English publication containing Menabrea's paper, Lovelace's translation, and Notes A-G.",
    },
)


CLAIMS: tuple[dict[str, Any], ...] = (
    {
        "key": "birth-1815",
        "text": "Augusta Ada Byron, later Countess of Lovelace, was born in London on 10 December 1815.",
        "kid_summary": "Ada was born in London in 1815, long before electronic computers existed.",
        "topic": "early life",
        "certainty": "high",
        "keywords": "born|birth|1815|london|childhood|young",
        "boundary": "Biographical fact; do not invent childhood memories.",
        "sources": ("chm-ada-lovelace", "science-museum-women-computing"),
        "entities": ("ada-lovelace",),
    },
    {
        "key": "byron-and-annabella",
        "text": "Ada was the daughter of Annabella Milbanke and the poet Lord Byron.",
        "kid_summary": "Ada's parents were Annabella Milbanke and the poet Lord Byron.",
        "topic": "family",
        "certainty": "high",
        "keywords": "mother|father|parents|family|byron|annabella",
        "boundary": "Family relationship only; avoid diagnosing motives or private feelings.",
        "sources": ("chm-ada-lovelace", "bodleian-lovelace-archive"),
        "entities": ("ada-lovelace",),
    },
    {
        "key": "private-mathematics-education",
        "text": "Ada received private mathematical education that was unusual for a woman in early nineteenth-century Britain.",
        "kid_summary": "Ada studied serious mathematics at a time when girls rarely received that opportunity.",
        "topic": "education",
        "certainty": "high",
        "keywords": "school|study|education|math|mathematics|girl|woman",
        "boundary": "Describe the historical access barrier without claiming Ada was the only educated woman.",
        "sources": ("chm-ada-lovelace", "science-museum-women-computing"),
        "entities": ("ada-lovelace",),
    },
    {
        "key": "somerville-and-de-morgan",
        "text": "Mary Somerville and Augustus De Morgan were important figures in Ada's mathematical education.",
        "kid_summary": "Ada learned with help from accomplished thinkers including Mary Somerville and Augustus De Morgan.",
        "topic": "education",
        "certainty": "high",
        "keywords": "teacher|tutor|somerville|de morgan|learn|mathematics",
        "boundary": "Do not collapse different teaching relationships into one classroom scene.",
        "sources": ("science-museum-women-computing", "bodleian-lovelace-archive"),
        "entities": ("ada-lovelace", "mary-somerville", "augustus-de-morgan"),
    },
    {
        "key": "met-babbage-1833",
        "text": "Mary Somerville introduced Ada to Charles Babbage in June 1833.",
        "kid_summary": "Ada met Charles Babbage in 1833 through Mary Somerville.",
        "topic": "collaboration",
        "certainty": "high",
        "keywords": "meet|met|babbage|1833|somerville|introduced",
        "boundary": "The exact dialogue and room details are not established by this claim.",
        "sources": ("science-museum-women-computing", "science-museum-difference-engines"),
        "entities": ("ada-lovelace", "charles-babbage", "mary-somerville"),
    },
    {
        "key": "saw-difference-engine",
        "text": "Babbage demonstrated a small working section of the Difference Engine to Ada.",
        "kid_summary": "Ada saw part of Babbage's Difference Engine working and became fascinated by it.",
        "topic": "machines",
        "certainty": "high",
        "keywords": "difference engine|machine|demonstration|saw|working|gears",
        "boundary": "A demonstration is supported; sensory details and spoken reactions require reconstruction labels.",
        "sources": ("science-museum-difference-engines", "chm-babbage-history"),
        "entities": ("ada-lovelace", "charles-babbage", "difference-engine"),
    },
    {
        "key": "long-collaboration",
        "text": "Lovelace and Babbage maintained a long intellectual friendship centered on mathematics and his engine designs.",
        "kid_summary": "Ada and Babbage kept exchanging ideas about mathematics and machines for many years.",
        "topic": "collaboration",
        "certainty": "high",
        "keywords": "friend|collaborate|babbage|letters|work together|partnership",
        "boundary": "Do not romanticize the relationship or invent private conversations.",
        "sources": ("science-museum-difference-engines", "bodleian-lovelace-archive"),
        "entities": ("ada-lovelace", "charles-babbage"),
    },
    {
        "key": "translated-menabrea",
        "text": "In 1843 Lovelace published an English translation of Luigi Menabrea's French account of the Analytical Engine.",
        "kid_summary": "Ada translated an important French paper about the Analytical Engine into English.",
        "topic": "publication",
        "certainty": "high",
        "keywords": "translate|translation|french|menabrea|paper|1843|english",
        "boundary": "Credit Menabrea as the original author and Lovelace as translator and note author.",
        "sources": ("chm-babbage-history", "gutenberg-analytical-engine"),
        "entities": ("ada-lovelace", "luigi-menabrea", "analytical-engine", "scientific-memoirs"),
    },
    {
        "key": "nine-month-note-work",
        "text": "Lovelace developed her translation and notes over roughly nine months in 1842 and 1843 while discussing the work with Babbage.",
        "kid_summary": "Ada spent months developing the translation and her own detailed notes.",
        "topic": "writing process",
        "certainty": "high",
        "keywords": "months|writing|notes|worked|1842|1843|process",
        "boundary": "Do not invent a daily schedule or exact desk scene.",
        "sources": ("science-museum-women-computing",),
        "entities": ("ada-lovelace", "charles-babbage", "analytical-engine"),
    },
    {
        "key": "notes-three-times-longer",
        "text": "Lovelace's Notes A-G were approximately three times as long as Menabrea's original paper.",
        "kid_summary": "Ada's added notes were much longer than the paper she translated.",
        "topic": "publication",
        "certainty": "high",
        "keywords": "notes|long|three times|paper|a-g|writing",
        "boundary": "Approximate comparative length, not a page-count claim across every edition.",
        "sources": ("science-museum-women-computing", "chm-babbage-history"),
        "entities": ("ada-lovelace", "luigi-menabrea", "scientific-memoirs"),
    },
    {
        "key": "published-as-aal",
        "text": "The 1843 publication credited Lovelace's notes with the initials A.A.L.",
        "kid_summary": "Ada's published notes were signed with her initials, A.A.L.",
        "topic": "publication",
        "certainty": "high",
        "keywords": "a.a.l|initials|signed|published|name|credit",
        "boundary": "Do not imply the initials made her authorship secret to every contemporary reader.",
        "sources": ("science-museum-women-computing", "gutenberg-analytical-engine"),
        "entities": ("ada-lovelace", "scientific-memoirs"),
    },
    {
        "key": "only-extensive-english-paper",
        "text": "Her translation and notes formed the only extensive English publication about the Analytical Engine during Babbage's lifetime.",
        "kid_summary": "Ada's publication became the major detailed English explanation of the Analytical Engine available while Babbage was alive.",
        "topic": "impact",
        "certainty": "high",
        "keywords": "english|publication|important|impact|explain|available",
        "boundary": "Use the bounded museum formulation; do not claim it was the only mention of the engine in English.",
        "sources": ("science-museum-women-computing",),
        "entities": ("ada-lovelace", "charles-babbage", "analytical-engine", "scientific-memoirs"),
    },
    {
        "key": "difference-versus-analytical",
        "text": "Lovelace emphasized that the specialized Difference Engine and the more general Analytical Engine worked on fundamentally different principles.",
        "kid_summary": "Ada explained that the Difference Engine followed a narrower job, while the Analytical Engine was designed for many kinds of procedures.",
        "topic": "machines",
        "certainty": "high",
        "keywords": "difference|analytical|compare engines|different|specialized|general",
        "boundary": "Keep the distinction conceptual; avoid mapping every modern computer feature directly onto the designs.",
        "sources": ("gutenberg-analytical-engine", "chm-babbage-history"),
        "entities": ("difference-engine", "analytical-engine", "ada-lovelace"),
    },
    {
        "key": "general-purpose-design",
        "text": "The Analytical Engine was conceived as a programmable general-purpose mechanical computing design rather than a machine for one fixed calculation.",
        "kid_summary": "The Analytical Engine was planned to follow different sets of instructions, not just repeat one calculation.",
        "topic": "machines",
        "certainty": "high",
        "keywords": "general purpose|computer|programmable|instructions|many jobs|analytical engine",
        "boundary": "It was a design, not a completed modern computer.",
        "sources": ("chm-babbage-history", "science-museum-difference-engines"),
        "entities": ("analytical-engine", "charles-babbage"),
    },
    {
        "key": "store-mill-cards",
        "text": "Babbage's Analytical Engine plans separated a store for values from a mill for operations and used punched cards to control work.",
        "kid_summary": "The design separated stored values from the part doing operations and used punched cards for instructions.",
        "topic": "machine architecture",
        "certainty": "high",
        "keywords": "store|mill|memory|operation|punched card|card|architecture",
        "boundary": "Use historical terms first; modern analogies are explanatory, not claims of identical hardware.",
        "sources": ("chm-babbage-history",),
        "entities": ("analytical-engine", "punched-cards", "charles-babbage"),
    },
    {
        "key": "symbols-beyond-number",
        "text": "Lovelace reasoned that if relationships could be represented in the engine's operations, it might manipulate symbols or other quantities as well as ordinary numbers.",
        "kid_summary": "Ada realized a programmable machine might work with symbols and patterns, not only arithmetic answers.",
        "topic": "vision",
        "certainty": "high",
        "keywords": "symbols|letters|patterns|beyond numbers|ideas|vision|quantities",
        "boundary": "This is a conceptual possibility in her notes, not evidence that the machine actually processed text.",
        "sources": ("gutenberg-analytical-engine", "science-museum-difference-engines"),
        "entities": ("ada-lovelace", "analytical-engine"),
    },
    {
        "key": "music-possibility",
        "text": "Lovelace suggested that a sufficiently represented system of musical relationships might allow the engine to compose elaborate music.",
        "kid_summary": "Ada imagined that encoded musical relationships might let such a machine create music.",
        "topic": "vision",
        "certainty": "high",
        "keywords": "music|compose|notes|sound|creative|art",
        "boundary": "A speculative possibility in the 1843 Notes; no music was produced by the unbuilt engine.",
        "sources": ("gutenberg-analytical-engine", "science-museum-women-computing"),
        "entities": ("ada-lovelace", "analytical-engine"),
    },
    {
        "key": "note-g-bernoulli",
        "text": "Lovelace's Note G included a detailed table of steps for the Analytical Engine to calculate Bernoulli numbers.",
        "kid_summary": "In Note G, Ada laid out a detailed procedure for calculating Bernoulli numbers with the Engine.",
        "topic": "algorithm",
        "certainty": "high",
        "keywords": "algorithm|program|bernoulli|note g|steps|table|calculate",
        "boundary": "Describe the published procedure precisely without pretending it ran on a completed engine.",
        "sources": ("gutenberg-analytical-engine", "science-museum-women-computing"),
        "entities": ("ada-lovelace", "analytical-engine", "bernoulli-numbers"),
    },
    {
        "key": "first-programmer-attribution",
        "text": "The Note G procedure is often described as the first published computer program or algorithm, although historians debate simplified 'first programmer' labels.",
        "kid_summary": "Ada is often called the first computer programmer because of Note G, but careful history explains why that label is debated.",
        "topic": "historical interpretation",
        "certainty": "qualified",
        "keywords": "first programmer|first program|debate|credit|algorithm|history",
        "boundary": "Always preserve the qualification; do not present a contested title as uncontested fact.",
        "sources": ("science-museum-women-computing", "gutenberg-analytical-engine"),
        "entities": ("ada-lovelace", "analytical-engine", "bernoulli-numbers"),
    },
    {
        "key": "engine-unbuilt",
        "text": "Babbage never completed the Analytical Engine; only plans and trial pieces were produced.",
        "kid_summary": "The full Analytical Engine was never built in Ada and Babbage's lifetimes.",
        "topic": "machines",
        "certainty": "high",
        "keywords": "built|finished|completed|real machine|trial piece|never built",
        "boundary": "Do not describe runtime results as observed historical events.",
        "sources": ("science-museum-difference-engines", "chm-babbage-history"),
        "entities": ("analytical-engine", "charles-babbage", "ada-lovelace"),
    },
)


SCENES: tuple[dict[str, Any], ...] = (
    {
        "key": "difference-engine-demonstration",
        "title": "A machine demonstration",
        "place": "Babbage's demonstration room",
        "scene": "Imagine brass wheels turning while a guide inspired by Ada leans closer to follow how one motion produces the next.",
        "mood": "curious",
        "imagination_note": "The demonstration is historical; the room, movements, and inner reaction are reconstructed.",
        "claims": ("met-babbage-1833", "saw-difference-engine"),
    },
    {
        "key": "translation-desk",
        "title": "Notes beside a translation",
        "place": "an imagined nineteenth-century writing desk",
        "scene": "Pages of French and English sit beside diagrams while the guide checks how each explanation connects to the Engine's design.",
        "mood": "focused",
        "imagination_note": "The translation and months of work are historical; this exact desk moment is invented.",
        "claims": ("translated-menabrea", "nine-month-note-work", "notes-three-times-longer"),
    },
    {
        "key": "punched-card-table",
        "title": "Instructions as cards",
        "place": "an imagined engine-planning table",
        "scene": "The guide arranges pretend cards into a sequence and explains that changing instructions could change the work performed.",
        "mood": "inventive",
        "imagination_note": "Punched-card control belongs to the design; this teaching demonstration is invented.",
        "claims": ("general-purpose-design", "store-mill-cards"),
    },
    {
        "key": "music-in-numbers",
        "title": "Patterns that might become music",
        "place": "an imagined music room",
        "scene": "A page of musical notes sits beside numerical patterns as the guide wonders how relationships could be encoded for a machine.",
        "mood": "wondering",
        "imagination_note": "Lovelace proposed musical possibilities; the room and activity are reconstruction.",
        "claims": ("symbols-beyond-number", "music-possibility"),
    },
    {
        "key": "bernoulli-table",
        "title": "Following Note G",
        "place": "an imagined mathematics study",
        "scene": "The guide traces a table one operation at a time, checking which value must move or change next.",
        "mood": "determined",
        "imagination_note": "The published table is historical; the live explanation and gestures are invented.",
        "claims": ("note-g-bernoulli", "engine-unbuilt"),
    },
    {
        "key": "museum-label-debate",
        "title": "A careful museum label",
        "place": "a modern museum gallery",
        "scene": "The guide compares two labels: one calls Ada the first programmer, while the other explains the evidence and the historical debate.",
        "mood": "thoughtful",
        "imagination_note": "The attribution debate is real; this particular museum conversation is invented.",
        "claims": ("first-programmer-attribution", "note-g-bernoulli"),
    },
)


PROMPTS: tuple[dict[str, Any], ...] = (
    {
        "key": "chat-engine-difference",
        "mode": "chat",
        "prompt": "How was the Analytical Engine different from the Difference Engine?",
        "answer": "The Difference Engine was designed for a narrower family of calculations. The Analytical Engine was planned to follow changing instructions for more general procedures.",
        "hint": "Think about one fixed job versus many instruction sets.",
        "claims": ("difference-versus-analytical", "general-purpose-design"),
    },
    {
        "key": "chat-ada-contribution",
        "mode": "chat",
        "prompt": "What did Ada add to the Engine project?",
        "answer": "She translated Menabrea's account, added much longer explanatory notes, described wider possibilities, and published a detailed Bernoulli-number procedure.",
        "hint": "Look at the translation, Notes A-G, and Note G.",
        "claims": (
            "translated-menabrea",
            "notes-three-times-longer",
            "symbols-beyond-number",
            "note-g-bernoulli",
        ),
    },
    {
        "key": "chat-music",
        "mode": "chat",
        "prompt": "Did Ada think computers could make music?",
        "answer": "She proposed that an engine might compose music if musical relationships could be represented for its operations. The unbuilt Engine never actually produced music.",
        "hint": "Separate a proposed possibility from a completed demonstration.",
        "claims": ("music-possibility", "engine-unbuilt"),
    },
    {
        "key": "story-first-machine",
        "mode": "story",
        "prompt": "Tell me about Ada seeing Babbage's machine.",
        "answer": "Use the machine-demonstration reconstruction, then ground it in the supported meeting and demonstration claims.",
        "hint": "Label room details as imagination.",
        "claims": ("met-babbage-1833", "saw-difference-engine"),
    },
    {
        "key": "story-writing-notes",
        "mode": "story",
        "prompt": "Tell me a story about Ada writing her notes.",
        "answer": "Use the translation-desk reconstruction and distinguish the documented nine-month work from invented moment-by-moment detail.",
        "hint": "The work is documented; the exact desk scene is not.",
        "claims": ("translated-menabrea", "nine-month-note-work", "published-as-aal"),
    },
    {
        "key": "story-bernoulli",
        "mode": "story",
        "prompt": "Tell me a story about the Bernoulli-number plan.",
        "answer": "Use the Bernoulli-table reconstruction and explain that the published procedure was designed for a machine that was not completed.",
        "hint": "A written procedure is not the same as a successful historical run.",
        "claims": ("note-g-bernoulli", "engine-unbuilt"),
    },
    {
        "key": "quiz-teachers",
        "mode": "quiz",
        "prompt": "Who helped Ada study mathematics?",
        "answer": "Mary Somerville and Augustus De Morgan were important figures in her mathematical education.",
        "hint": "One introduced Ada to Babbage; the other taught through correspondence.",
        "claims": ("somerville-and-de-morgan", "met-babbage-1833"),
    },
    {
        "key": "quiz-note-g",
        "mode": "quiz",
        "prompt": "What number sequence appeared in Ada's Note G procedure?",
        "answer": "Bernoulli numbers.",
        "hint": "The name begins with B.",
        "claims": ("note-g-bernoulli",),
    },
    {
        "key": "quiz-engine-built",
        "mode": "quiz",
        "prompt": "Was the complete Analytical Engine built in Ada's lifetime?",
        "answer": "No. Plans and trial pieces existed, but the complete Engine was not built.",
        "hint": "Separate a design from a finished machine.",
        "claims": ("engine-unbuilt",),
    },
    {
        "key": "compare-memory",
        "mode": "compare",
        "prompt": "How was the Engine's store like computer memory today?",
        "answer": "Both ideas keep values available for later operations, but Babbage's mechanical store and modern electronic memory use radically different physical technology.",
        "hint": "Use an analogy without claiming identical hardware.",
        "claims": ("store-mill-cards",),
    },
    {
        "key": "compare-programming",
        "mode": "compare",
        "prompt": "How were punched cards like programs today?",
        "answer": "The cards represented instructions and data for the planned Engine. Modern programs are encoded electronically, but both organize operations into controllable sequences.",
        "hint": "Compare purpose, then distinguish implementation.",
        "claims": ("general-purpose-design", "store-mill-cards"),
    },
    {
        "key": "compare-opportunity",
        "mode": "compare",
        "prompt": "How was studying mathematics different for Ada than for kids today?",
        "answer": "Ada needed unusual private access to advanced study at a time when women faced strong educational barriers. Many more children can study mathematics today, although access is still not equal everywhere.",
        "hint": "Do not turn progress into a claim that every barrier disappeared.",
        "claims": ("private-mathematics-education", "somerville-and-de-morgan"),
    },
)


MISCONCEPTIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "engine-was-built",
        "misconception": "Ada ran her program on a completed Analytical Engine.",
        "correction": "The complete Engine was never built; Note G was a published procedure designed for it.",
        "kid_response": "Ada wrote a plan for what the machine should do, but there was no finished Engine to run it.",
        "claim": "engine-unbuilt",
    },
    {
        "key": "ada-built-engine",
        "misconception": "Ada designed and physically built Babbage's engine by herself.",
        "correction": "Babbage designed the engines; Lovelace interpreted, explained, extended, and publicized their possibilities.",
        "kid_response": "Babbage designed the machine, while Ada made major contributions through mathematics, explanation, and published notes.",
        "claim": "translated-menabrea",
    },
    {
        "key": "first-programmer-simple",
        "misconception": "Every historian agrees without qualification that Ada was the first programmer.",
        "correction": "Note G is often called the first published program, but simplified first-person labels remain historically debated.",
        "kid_response": "The label is useful, but careful history also explains the debate and the evidence behind it.",
        "claim": "first-programmer-attribution",
    },
    {
        "key": "engine-thought-alone",
        "misconception": "Lovelace claimed the Engine could originate ideas and think independently.",
        "correction": "Her Notes emphasized following operations and relationships supplied to the Engine, while exploring how broadly symbols might be represented.",
        "kid_response": "Ada imagined broad uses, but she did not describe the Engine as inventing its own instructions.",
        "claim": "symbols-beyond-number",
    },
    {
        "key": "story-card-is-diary",
        "misconception": "A first-person Time Room scene is a recovered diary entry or exact quotation.",
        "correction": "Runtime scenes are labeled reconstructions grounded by separate historical claims.",
        "kid_response": "The scene helps us imagine the setting; the Fact lens tells us what the sources actually support.",
        "claim": "nine-month-note-work",
    },
)


PACK = {
    "key": RUNTIME_PACK_KEY,
    "version": "0.1.0",
    "figure_key": "ada-lovelace",
    "output_schema_version": 1,
    "guardrails": "Use only included claims for factual assertions; label every scene as reconstruction; preserve qualified certainty; cite graph and source keys; never require Vellis or a model at runtime.",
    "status": "alpha",
}


EXPECTED_COUNTS = {
    "anchor": {
        "HistoricalFigure": 1,
        "HistoricalSource": len(SOURCES),
        "HistoricalEntity": len(ENTITIES),
        "HistoricalClaim": len(CLAIMS),
        "ReconstructionScene": len(SCENES),
        "LearningPrompt": len(PROMPTS),
        "Misconception": len(MISCONCEPTIONS),
        "RuntimePack": 1,
    },
    "data_object": {
        "HistoricalFigureFacts": 1,
        "HistoricalSourceFacts": len(SOURCES),
        "HistoricalEntityFacts": len(ENTITIES),
        "HistoricalClaimFacts": len(CLAIMS),
        "ReconstructionSceneFacts": len(SCENES),
        "LearningPromptFacts": len(PROMPTS),
        "MisconceptionFacts": len(MISCONCEPTIONS),
        "RuntimePackFacts": 1,
    },
}


def _id(kind: str, key: str) -> str:
    return str(uuid5(NAMESPACE, f"{kind}:{key}"))


def _field(
    kind: str = "string", *, required: bool = True, format_name: str | None = None
) -> dict[str, Any]:
    field: dict[str, Any] = {"required": required, "value_kinds": [kind]}
    if format_name is not None:
        field["format"] = format_name
    return field


def _data_schema(
    type_key: str, description: str, properties: dict[str, Any], *, time_shape: str = "state_now"
) -> dict[str, Any]:
    return {
        "kind": "data_object",
        "type_key": type_key,
        "description": description,
        "time_shape": time_shape,
        "payload": {"properties": properties},
    }


def _anchor_schema(
    type_key: str, facts_type: str, description: str, *, time_shape: str = "state_now"
) -> dict[str, Any]:
    return {
        "kind": "anchor",
        "type_key": type_key,
        "description": description,
        "time_shape": time_shape,
        "payload": {"required_data_types": [facts_type]},
    }


def _link_schema(
    type_key: str,
    description: str,
    sources: list[str],
    targets: list[str],
    *,
    link_kind: str,
) -> dict[str, Any]:
    return {
        "kind": "link",
        "type_key": type_key,
        "description": description,
        "payload": {
            "allowed_source_types": sources,
            "allowed_target_types": targets,
            "link_kind": link_kind,
        },
    }


def schema_definitions() -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    pairs = (
        (
            "HistoricalFigure",
            "HistoricalFigureFacts",
            "A historical figure with a bounded runtime identity and biographical scope.",
            {
                "stable_key": _field(),
                "name": _field(),
                "years": _field(),
                "place": _field(),
                "summary": _field(),
            },
        ),
        (
            "HistoricalSource",
            "HistoricalSourceFacts",
            "An authoritative source or archival locator used to support historical claims.",
            {
                "stable_key": _field(),
                "title": _field(),
                "provider": _field(),
                "url": _field(),
                "source_kind": _field(),
                "verification_status": _field(),
                "publication_note": _field(),
            },
        ),
        (
            "HistoricalEntity",
            "HistoricalEntityFacts",
            "A person, machine, publication, concept, or technology mentioned by claims.",
            {"stable_key": _field(), "name": _field(), "kind": _field(), "summary": _field()},
        ),
        (
            "HistoricalClaim",
            "HistoricalClaimFacts",
            "A compact, source-supported historical assertion suitable for bounded runtime projection.",
            {
                "stable_key": _field(),
                "text": _field(),
                "kid_summary": _field(),
                "topic": _field(),
                "certainty": _field(),
                "keywords": _field(),
                "fact_boundary": _field(),
                "verification_status": _field(),
            },
            "state_as_of",
        ),
        (
            "ReconstructionScene",
            "ReconstructionSceneFacts",
            "A presentation scene explicitly separated from its grounding historical claims.",
            {
                "stable_key": _field(),
                "title": _field(),
                "place": _field(),
                "scene": _field(),
                "mood": _field(),
                "imagination_note": _field(),
            },
            "state_as_of",
        ),
        (
            "LearningPrompt",
            "LearningPromptFacts",
            "A deterministic chat, story, quiz, or comparison prompt grounded by claims.",
            {
                "stable_key": _field(),
                "mode": _field(),
                "prompt": _field(),
                "answer": _field(),
                "hint": _field(),
            },
            "state_as_of",
        ),
        (
            "Misconception",
            "MisconceptionFacts",
            "A known misleading simplification with a claim-grounded correction.",
            {
                "stable_key": _field(),
                "misconception": _field(),
                "correction": _field(),
                "kid_response": _field(),
            },
            "state_as_of",
        ),
        (
            "RuntimePack",
            "RuntimePackFacts",
            "An append-only compilation target describing one bounded offline runtime projection.",
            {
                "stable_key": _field(),
                "version": _field(),
                "figure_key": _field(),
                "output_schema_version": _field("integer"),
                "guardrails": _field(),
                "status": _field(),
            },
            "event",
        ),
    )
    for pair in pairs:
        anchor_type, facts_type, description, properties, *shape = pair
        time_shape = shape[0] if shape else "state_now"
        if time_shape == "state_as_of":
            properties = {
                **properties,
                "valid_from": _field(format_name="date_time"),
                "valid_to": _field(format_name="date_time"),
            }
        definitions.append(
            _data_schema(
                facts_type,
                f"Structured facts for {anchor_type}.",
                properties,
                time_shape=time_shape,
            )
        )
        anchor_time_shape = "state_now" if time_shape == "state_as_of" else time_shape
        definitions.append(
            _anchor_schema(anchor_type, facts_type, description, time_shape=anchor_time_shape)
        )
    definitions.extend(
        [
            _link_schema(
                "claim_about_figure",
                "Connects a historical claim to its subject figure.",
                ["HistoricalClaim"],
                ["HistoricalFigure"],
                link_kind="semantic",
            ),
            _link_schema(
                "claim_supported_by",
                "Connects a historical claim to an authoritative supporting source.",
                ["HistoricalClaim"],
                ["HistoricalSource"],
                link_kind="provenance",
            ),
            _link_schema(
                "claim_mentions",
                "Connects a historical claim to an entity needed for traversal or explanation.",
                ["HistoricalClaim"],
                ["HistoricalEntity"],
                link_kind="semantic",
            ),
            _link_schema(
                "scene_about_figure",
                "Connects a reconstruction scene to its figure.",
                ["ReconstructionScene"],
                ["HistoricalFigure"],
                link_kind="semantic",
            ),
            _link_schema(
                "scene_grounded_by",
                "Connects a reconstruction scene to a historical claim that bounds it.",
                ["ReconstructionScene"],
                ["HistoricalClaim"],
                link_kind="provenance",
            ),
            _link_schema(
                "prompt_about_figure",
                "Connects a learning prompt to its figure.",
                ["LearningPrompt"],
                ["HistoricalFigure"],
                link_kind="semantic",
            ),
            _link_schema(
                "prompt_grounded_by",
                "Connects a learning prompt to a historical claim used in its answer.",
                ["LearningPrompt"],
                ["HistoricalClaim"],
                link_kind="provenance",
            ),
            _link_schema(
                "misconception_about_figure",
                "Connects a misconception to the figure whose history it can distort.",
                ["Misconception"],
                ["HistoricalFigure"],
                link_kind="semantic",
            ),
            _link_schema(
                "misconception_corrected_by",
                "Connects a misconception to the claim that corrects it.",
                ["Misconception"],
                ["HistoricalClaim"],
                link_kind="provenance",
            ),
            _link_schema(
                "pack_for_figure",
                "Connects a runtime pack build to its subject figure.",
                ["RuntimePack"],
                ["HistoricalFigure"],
                link_kind="semantic",
            ),
            _link_schema(
                "pack_includes_claim",
                "Declares a claim included in a runtime pack.",
                ["RuntimePack"],
                ["HistoricalClaim"],
                link_kind="structural",
            ),
            _link_schema(
                "pack_includes_scene",
                "Declares a reconstruction scene included in a runtime pack.",
                ["RuntimePack"],
                ["ReconstructionScene"],
                link_kind="structural",
            ),
            _link_schema(
                "pack_includes_prompt",
                "Declares a learning prompt included in a runtime pack.",
                ["RuntimePack"],
                ["LearningPrompt"],
                link_kind="structural",
            ),
            _link_schema(
                "pack_includes_misconception",
                "Declares a misconception guard included in a runtime pack.",
                ["RuntimePack"],
                ["Misconception"],
                link_kind="structural",
            ),
        ]
    )
    return definitions


def _anchor_record(
    type_key: str, facts_type: str, key: str, display_name: str, properties: dict[str, Any]
) -> dict[str, Any]:
    return {
        "ref": {"resource_id": _id("anchor", f"{type_key}:{key}")},
        "type": type_key,
        "display_name": display_name,
        "facts": [
            {
                "ref": {"resource_id": _id("facts", f"{facts_type}:{key}")},
                "type": facts_type,
                "mode": "merge",
                "properties": properties,
            }
        ],
    }


def _anchor_ref(type_key: str, key: str) -> dict[str, str]:
    return {"resource_id": _id("anchor", f"{type_key}:{key}")}


def _link(
    link_type: str, source_type: str, source_key: str, target_type: str, target_key: str
) -> dict[str, Any]:
    key = f"{link_type}:{source_type}:{source_key}:{target_type}:{target_key}"
    return {
        "ref": {"resource_id": _id("link", key)},
        "type": link_type,
        "source_ref": _anchor_ref(source_type, source_key),
        "target_ref": _anchor_ref(target_type, target_key),
    }


def live_records() -> dict[str, Any]:
    validity = {
        "valid_from": "2026-07-10T00:00:00Z",
        "valid_to": "9999-12-31T23:59:59Z",
    }
    records = [
        _anchor_record(
            "HistoricalFigure",
            "HistoricalFigureFacts",
            "ada-lovelace",
            "Ada Lovelace",
            {
                "stable_key": "ada-lovelace",
                "name": "Ada Lovelace",
                "years": "1815-1852",
                "place": "Britain",
                "summary": "Mathematician and writer whose 1843 translation and Notes explored the possibilities of Babbage's Analytical Engine.",
            },
        )
    ]
    records.extend(
        _anchor_record(
            "HistoricalSource",
            "HistoricalSourceFacts",
            item["key"],
            item["title"],
            {
                "stable_key": item["key"],
                **{key: value for key, value in item.items() if key != "key"},
            },
        )
        for item in SOURCES
    )
    records.extend(
        _anchor_record(
            "HistoricalEntity",
            "HistoricalEntityFacts",
            item["key"],
            item["name"],
            {
                "stable_key": item["key"],
                **{key: value for key, value in item.items() if key != "key"},
            },
        )
        for item in ENTITIES
    )
    records.extend(
        _anchor_record(
            "HistoricalClaim",
            "HistoricalClaimFacts",
            item["key"],
            item["kid_summary"],
            {
                "stable_key": item["key"],
                "text": item["text"],
                "kid_summary": item["kid_summary"],
                "topic": item["topic"],
                "certainty": item["certainty"],
                "keywords": item["keywords"],
                "fact_boundary": item["boundary"],
                "verification_status": "reviewed",
                **validity,
            },
        )
        for item in CLAIMS
    )
    records.extend(
        _anchor_record(
            "ReconstructionScene",
            "ReconstructionSceneFacts",
            item["key"],
            item["title"],
            {
                "stable_key": item["key"],
                "title": item["title"],
                "place": item["place"],
                "scene": item["scene"],
                "mood": item["mood"],
                "imagination_note": item["imagination_note"],
                **validity,
            },
        )
        for item in SCENES
    )
    records.extend(
        _anchor_record(
            "LearningPrompt",
            "LearningPromptFacts",
            item["key"],
            item["prompt"],
            {
                "stable_key": item["key"],
                "mode": item["mode"],
                "prompt": item["prompt"],
                "answer": item["answer"],
                "hint": item["hint"],
                **validity,
            },
        )
        for item in PROMPTS
    )
    records.extend(
        _anchor_record(
            "Misconception",
            "MisconceptionFacts",
            item["key"],
            item["misconception"],
            {
                "stable_key": item["key"],
                "misconception": item["misconception"],
                "correction": item["correction"],
                "kid_response": item["kid_response"],
                **validity,
            },
        )
        for item in MISCONCEPTIONS
    )
    records.append(
        _anchor_record(
            "RuntimePack",
            "RuntimePackFacts",
            PACK["key"],
            "Ada Lovelace alpha runtime pack",
            {
                "stable_key": PACK["key"],
                **{key: value for key, value in PACK.items() if key != "key"},
            },
        )
    )

    links: list[dict[str, Any]] = []
    for claim in CLAIMS:
        links.append(
            _link(
                "claim_about_figure",
                "HistoricalClaim",
                claim["key"],
                "HistoricalFigure",
                "ada-lovelace",
            )
        )
        links.extend(
            _link("claim_supported_by", "HistoricalClaim", claim["key"], "HistoricalSource", source)
            for source in claim["sources"]
        )
        links.extend(
            _link("claim_mentions", "HistoricalClaim", claim["key"], "HistoricalEntity", entity)
            for entity in claim["entities"]
        )
    for scene in SCENES:
        links.append(
            _link(
                "scene_about_figure",
                "ReconstructionScene",
                scene["key"],
                "HistoricalFigure",
                "ada-lovelace",
            )
        )
        links.extend(
            _link(
                "scene_grounded_by", "ReconstructionScene", scene["key"], "HistoricalClaim", claim
            )
            for claim in scene["claims"]
        )
    for prompt in PROMPTS:
        links.append(
            _link(
                "prompt_about_figure",
                "LearningPrompt",
                prompt["key"],
                "HistoricalFigure",
                "ada-lovelace",
            )
        )
        links.extend(
            _link("prompt_grounded_by", "LearningPrompt", prompt["key"], "HistoricalClaim", claim)
            for claim in prompt["claims"]
        )
    for misconception in MISCONCEPTIONS:
        links.append(
            _link(
                "misconception_about_figure",
                "Misconception",
                misconception["key"],
                "HistoricalFigure",
                "ada-lovelace",
            )
        )
        links.append(
            _link(
                "misconception_corrected_by",
                "Misconception",
                misconception["key"],
                "HistoricalClaim",
                misconception["claim"],
            )
        )
    links.append(
        _link("pack_for_figure", "RuntimePack", PACK["key"], "HistoricalFigure", "ada-lovelace")
    )
    links.extend(
        _link("pack_includes_claim", "RuntimePack", PACK["key"], "HistoricalClaim", item["key"])
        for item in CLAIMS
    )
    links.extend(
        _link("pack_includes_scene", "RuntimePack", PACK["key"], "ReconstructionScene", item["key"])
        for item in SCENES
    )
    links.extend(
        _link("pack_includes_prompt", "RuntimePack", PACK["key"], "LearningPrompt", item["key"])
        for item in PROMPTS
    )
    links.extend(
        _link(
            "pack_includes_misconception", "RuntimePack", PACK["key"], "Misconception", item["key"]
        )
        for item in MISCONCEPTIONS
    )
    return {"anchor_records": records, "link_writes": links, "validation_mode": "strict"}


def _query_call(anchor_type: str, facts_type: str, bucket: str) -> dict[str, Any]:
    return {
        "tool": "rtg_execute_query",
        "arguments": {
            "query_spec": {
                "anchor_buckets": [{"name": bucket, "anchor_type_keys": [anchor_type]}],
                "data_requirements": [
                    {"name": "facts", "anchor_bucket": bucket, "data_type_key": facts_type}
                ],
                "return_spec": {"anchor_buckets": [bucket], "data_requirements": ["facts"]},
            },
            "query_options": {"live_filter": "live"},
            "response_options": {"format": "properties_only"},
        },
    }


def query_calls() -> dict[str, dict[str, Any]]:
    return {
        "figure": _query_call("HistoricalFigure", "HistoricalFigureFacts", "figure"),
        "sources": _query_call("HistoricalSource", "HistoricalSourceFacts", "source"),
        "claims": _query_call("HistoricalClaim", "HistoricalClaimFacts", "claim"),
        "scenes": _query_call("ReconstructionScene", "ReconstructionSceneFacts", "scene"),
        "prompts": _query_call("LearningPrompt", "LearningPromptFacts", "prompt"),
        "misconceptions": _query_call("Misconception", "MisconceptionFacts", "misconception"),
        "pack": _query_call("RuntimePack", "RuntimePackFacts", "pack"),
    }


def build_files() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QUERY_DIR.mkdir(parents=True, exist_ok=True)
    schema_call = {
        "tool": "rtg_stage_schema_migration",
        "arguments": {
            "migration_id": "time-room-history-schema-v0",
            "description": "Introduce the alpha source-grounded Time Room history schema and deterministic runtime-pack projection types.",
            "schema_definitions": schema_definitions(),
            "validation_mode": "strict",
        },
    }
    live_call = {"tool": "rtg_apply_live_anchor_records", "arguments": live_records()}
    SCHEMA_CALL_PATH.write_text(
        json.dumps(schema_call, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    LIVE_RECORDS_PATH.write_text(
        json.dumps(live_call, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for name, call in query_calls().items():
        (QUERY_DIR / f"{name}.json").write_text(
            json.dumps(call, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return {
        "schema_definition_count": len(schema_call["arguments"]["schema_definitions"]),
        "anchor_record_count": len(live_call["arguments"]["anchor_records"]),
        "link_count": len(live_call["arguments"]["link_writes"]),
        "query_count": len(query_calls()),
    }


def main() -> int:
    print(json.dumps(build_files(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
