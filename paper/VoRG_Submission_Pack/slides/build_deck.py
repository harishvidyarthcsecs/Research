"""
Build VoRG_Talk.pptx - a decorative, self-contained 16-slide talk on
Verify-or-Reject Grounding, with speaker notes, fade transitions on every slide,
and click-by-click "Fade / By Paragraph" bullet animation on content slides.

python-pptx has no API for transitions or animations, so both are injected as
OOXML into the saved file (see the animate section at the bottom): the
transition is the plain 2006 <p:transition>, and the timing tree is the exact
structure PowerPoint writes for "Fade | On Click | By Paragraph", so the file
opens without a repair prompt.

Run:  python3 build_deck.py
"""
import zipfile
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
OUT = HERE / "VoRG_Talk.pptx"

# ---- palette --------------------------------------------------------------
PURPLE   = RGBColor(0x6A, 0x1B, 0x9A)   # primary
PURPLE_D = RGBColor(0x4A, 0x12, 0x6E)   # dark purple
GOLD     = RGBColor(0xF5, 0xA6, 0x23)   # accent 1
TEAL     = RGBColor(0x1F, 0x9E, 0x8F)   # accent 2
GREEN    = RGBColor(0x2E, 0x7D, 0x32)   # "pass"
RED      = RGBColor(0xC0, 0x39, 0x2B)   # "fail"
LAV      = RGBColor(0xF3, 0xE9, 0xF9)   # light card fill
CREAM    = RGBColor(0xFD, 0xF6, 0xE9)   # light gold fill
INK      = RGBColor(0x20, 0x20, 0x20)
GREY     = RGBColor(0x5A, 0x5A, 0x5A)
WHITE    = RGBColor(0xFF, 0xFF, 0xFF)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
SW, SH = prs.slide_width, prs.slide_height
BLANK = prs.slide_layouts[6]

BODY_SPIDS = {}   # slide number (1-based) -> body placeholder shape id


# ---- primitives --------------------------------------------------------------
def _noline(shape):
    shape.line.fill.background()


def rect(slide, x, y, w, h, color, line=None):
    sp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    sp.fill.solid(); sp.fill.fore_color.rgb = color
    if line is None:
        _noline(sp)
    else:
        sp.line.color.rgb = line; sp.line.width = Pt(1)
    sp.shadow.inherit = False
    return sp


def rrect(slide, x, y, w, h, color, radius=0.08):
    sp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    sp.fill.solid(); sp.fill.fore_color.rgb = color
    _noline(sp)
    sp.shadow.inherit = False
    try:
        sp.adjustments[0] = radius
    except Exception:
        pass
    return sp


def oval(slide, x, y, d, color):
    sp = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, d, d)
    sp.fill.solid(); sp.fill.fore_color.rgb = color
    _noline(sp); sp.shadow.inherit = False
    return sp


def text(shape, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    """runs: list of (text, size, bold, color) or a single string."""
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = Inches(0.12); tf.margin_right = Inches(0.12)
    tf.margin_top = Inches(0.06); tf.margin_bottom = Inches(0.06)
    if isinstance(runs, str):
        runs = [(runs, 18, False, INK)]
    for i, (t, sz, b, c) in enumerate(runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = t
        p.alignment = align
        p.font.size = Pt(sz); p.font.bold = b; p.font.color.rgb = c
        p.space_after = Pt(4)
    return shape


def textbox(slide, x, y, w, h, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    return text(slide.shapes.add_textbox(x, y, w, h), runs, align, anchor)


def chip(slide, x, y, w, label, fill, fg=WHITE, size=13):
    sp = rrect(slide, x, y, w, Inches(0.42), fill, radius=0.5)
    text(sp, [(label, size, True, fg)], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    return sp


def card(slide, x, y, w, h, title, body, fill=LAV, title_color=PURPLE, body_color=INK):
    sp = rrect(slide, x, y, w, h, fill, radius=0.06)
    tf = sp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.margin_left = Inches(0.18); tf.margin_right = Inches(0.18)
    tf.margin_top = Inches(0.14); tf.margin_bottom = Inches(0.12)
    p = tf.paragraphs[0]
    p.text = title; p.font.size = Pt(16); p.font.bold = True; p.font.color.rgb = title_color
    p.space_after = Pt(6)
    for line in body:
        q = tf.add_paragraph()
        q.text = line; q.font.size = Pt(13); q.font.color.rgb = body_color
        q.space_after = Pt(3)
    return sp


def callout(slide, x, y, w, h, lines, fill=GOLD, fg=WHITE):
    sp = rrect(slide, x, y, w, h, fill, radius=0.10)
    text(sp, [(t, sz, b, fg) for (t, sz, b) in lines],
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    return sp


def deco_circles(slide):
    oval(slide, SW - Inches(2.4), -Inches(1.6), Inches(4.2), GOLD)
    oval(slide, -Inches(1.7), SH - Inches(2.0), Inches(3.4), TEAL)


def chrome(slide, n, title):
    """Title band + gold underline + footer + page pill for a content slide."""
    rect(slide, 0, 0, SW, Inches(1.06), PURPLE)
    rect(slide, 0, Inches(1.06), SW, Inches(0.07), GOLD)
    rect(slide, 0, 0, Inches(0.14), SH, GOLD)
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.12), SW - Inches(2.2), Inches(0.85))
    text(tb, [(title, 26, True, WHITE)], anchor=MSO_ANCHOR.MIDDLE)
    textbox(slide, Inches(0.45), SH - Inches(0.42), Inches(7.0), Inches(0.35),
            [("VoRG  ·  Reject-Before-Propagate", 10, False, GREY)])
    pill = rrect(slide, SW - Inches(1.15), SH - Inches(0.5), Inches(0.7), Inches(0.36),
                 PURPLE, radius=0.5)
    text(pill, [(f"{n}", 12, True, WHITE)], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def bullets(slide, items, x=Inches(0.7), y=Inches(1.45),
            w=Inches(11.9), h=Inches(5.6), size=17):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame; tf.word_wrap = True
    for i, (lvl, t) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = ("▸  " if lvl == 0 else "     –  ") + t
        p.level = lvl
        p.font.size = Pt(size - 2 * lvl)
        p.font.color.rgb = INK if lvl == 0 else GREY
        p.space_after = Pt(9 if lvl == 0 else 5)
    return box


def notes(slide, txt):
    slide.notes_slide.notes_text_frame.text = txt


def content(n, title, items, image=None, img_w=Inches(4.7)):
    s = prs.slides.add_slide(BLANK)
    chrome(s, n, title)
    bw = Inches(11.9) if image is None else Inches(7.3)
    box = bullets(s, items, w=bw)
    BODY_SPIDS[n] = box.shape_id
    if image and (ASSETS / image).exists():
        pic = s.shapes.add_picture(str(ASSETS / image), SW - img_w - Inches(0.5),
                                   Inches(1.55), width=img_w)
        rrect(s, pic.left - Emu(9525), pic.top - Emu(9525),
              pic.width + Emu(19050), pic.height + Emu(19050), GOLD, radius=0.03)
        s.shapes._spTree.remove(s.shapes[-1]._element)  # drop the frame we just added on top
    return s


def section(n, num, title):
    s = prs.slides.add_slide(BLANK)
    rect(s, 0, 0, SW, SH, PURPLE)
    rect(s, 0, SH/2 + Inches(0.2), SW, Inches(0.06), GOLD)
    textbox(s, Inches(0.9), SH/2 - Inches(1.5), Inches(4), Inches(1.6),
            [(f"{num:02d}", 80, True, GOLD)])
    textbox(s, Inches(0.9), SH/2 + Inches(0.4), Inches(11), Inches(1.4),
            [(title, 34, True, WHITE)])
    deco_circles(s)
    return s


# ========================================================================
# 1  Title
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, SW, SH, PURPLE)
deco_circles(s)
rect(s, Inches(0.9), Inches(2.05), Inches(3.4), Inches(0.10), GOLD)
textbox(s, Inches(0.9), Inches(2.2), Inches(11.6), Inches(2.6), [
    ("Reject-Before-Propagate", 44, True, WHITE),
    ("Build-Time Citation Gates for Agentic Literature-Synthesis Pipelines", 22, False, GOLD),
])
textbox(s, Inches(0.9), Inches(5.0), Inches(11.6), Inches(1.6), [
    ("N. Harish Vidyarth*,  A. L. Reshma,  R. Divya", 18, True, WHITE),
    ("Dept. of CSE (Cyber Security), Rajalakshmi Engineering College, Chennai", 15, False, WHITE),
    ("Target venue: ICACCS 2027  (IEEE Xplore)   ·   * corresponding author", 13, False, RGBColor(0xE0,0xC8,0xF0)),
])
notes(s, "Thesis in one line: LLM pipelines that review literature can emit "
         "citations that are wrong or fabricated. We stop that structurally, by "
         "making citation grounding a build-time invariant rather than a score a "
         "later stage can ignore.")

# 2  Roadmap
s = prs.slides.add_slide(BLANK)
chrome(s, 2, "What this talk covers")
road = ["The problem", "Why a score is not enough", "The idea: Verify-or-Reject Grounding",
        "The reference system", "The certification algorithm", "Evaluation and the central finding"]
cols = 2
for i, item in enumerate(road):
    cx = Inches(0.8) + (i % cols) * Inches(6.3)
    cy = Inches(1.7) + (i // cols) * Inches(1.6)
    oval(s, cx, cy, Inches(0.7), GOLD)
    textbox(s, cx + Inches(0.16), cy + Inches(0.12), Inches(0.5), Inches(0.5),
            [(str(i + 1), 18, True, PURPLE_D)])
    textbox(s, cx + Inches(0.95), cy + Inches(0.06), Inches(5.1), Inches(1.2),
            [(item, 17, True, INK)])
BODY_SPIDS[2] = None  # decorative slide, no paragraph build
notes(s, "Six beats. Keep the problem and the finding as the two you must land.")

# 3  The problem
sl = content(3, "The problem: hallucinated and fabricated citations", [
    (0, "LLM pipelines extract claims, detect contradictions, and draft synthesis prose over a set of papers."),
    (0, "Hallucination: the generated sentence looks well supported, but nothing in the source says it."),
    (0, "Citation-level failure: the cited paper does not make the claim, or the reference does not exist."),
    (0, "Example: a pipeline emitted “GNNs outperform descriptor baselines on ADMET tasks” with confidence 0.71; the cited paper never makes that comparison."),
    (0, "When the output feeds a real manuscript, one wrong citation is expensive to catch later."),
], image="03-reference-validator.png")
callout(sl, Inches(0.7), Inches(6.05), Inches(7.1), Inches(0.9),
        [("Today the citation check exists, but only as an advisory score.", 14, True)],
        fill=RED)
notes(sl, "Ground the stakes with the concrete example. The screenshot shows the "
          "reference validator: the check is there, it just does not gate.")

# 4  Why a score is not enough
s = prs.slides.add_slide(BLANK)
chrome(s, 4, "Scored grounding leaves a gap")
card(s, Inches(0.7), Inches(1.5), Inches(5.9), Inches(4.6),
     "Scored grounding", [
        "A confidence value, a flag, or a review-queue entry is attached to the output.",
        "The value sits next to the text; it does not control whether the text is emitted.",
        "If the next stage reads the text field and not the score field, the unverified sentence propagates.",
        "A hurried human reviewer can do the same.",
     ], fill=CREAM, title_color=RED)
card(s, Inches(6.9), Inches(1.5), Inches(5.7), Inches(4.6),
     "What we want instead", [
        "The check is part of the stage's output type, not a value beside it.",
        "An unverifiable value is never produced, so no later stage can receive one.",
        "The guarantee holds for stages added later, without them knowing a score existed.",
     ], fill=LAV, title_color=GREEN)
BODY_SPIDS[4] = None
notes(s, "Key distinction. Scored grounding is a property of the output and is "
         "skippable. We move the guarantee into the pipeline itself.")

# 5  The idea
s = prs.slides.add_slide(BLANK)
chrome(s, 5, "Verify-or-Reject Grounding (VoRG)")
textbox(s, Inches(0.7), Inches(1.4), Inches(11.9), Inches(1.0), [
    ("Treat citation grounding as a build-time invariant. Every stage satisfies one of three conditions, or the build fails:", 16, False, INK)])
c1 = card(s, Inches(0.7), Inches(2.5), Inches(3.9), Inches(3.0),
     "1. Deterministic", [
        "The stage transforms only already-verified inputs.",
        "It adds no new hallucination surface.",
     ], fill=LAV)
c2 = card(s, Inches(4.75), Inches(2.5), Inches(3.9), Inches(3.0),
     "2. Explicit check", [
        "A verification step discards any non-conforming output before it propagates.",
     ], fill=CREAM)
c3 = card(s, Inches(8.8), Inches(2.5), Inches(3.8), Inches(3.0),
     "3. Build error", [
        "The stage cannot verify its output, so it fails loudly instead of degrading quietly.",
     ], fill=RGBColor(0xF7,0xE2,0xDE), title_color=RED)
callout(s, Inches(0.7), Inches(5.75), Inches(11.9), Inches(0.95),
        [("Same reject-by-default logic as the fail-safe-defaults principle in protection-system design (Saltzer and Schroeder, 1975).", 13, True)],
        fill=PURPLE)
BODY_SPIDS[5] = None
notes(s, "VoRG is a property of the pipeline. A downstream stage cannot bypass "
         "it by ignoring a score it was never given.")

# 6  Reference system
s = prs.slides.add_slide(BLANK)
chrome(s, 6, "Reference system: an eight-stage pipeline")
stages = [("Topic\nexpansion", False), ("Paper\ndiscovery", False), ("Claim\nextraction", False),
          ("Claim\nnormalisation", False), ("Contradiction\ndetection", True),
          ("Research-gap\ndetection", False), ("Citation\nbuilding", True), ("Persistence", True)]
x0 = Inches(0.6); bw = Inches(1.48); gap = Inches(0.06)
for i, (label, gated) in enumerate(stages):
    bx = x0 + i * (bw + gap)
    fill = GOLD if gated else LAV
    fg = PURPLE_D if gated else INK
    b = rrect(s, bx, Inches(2.2), bw, Inches(1.5), fill, radius=0.10)
    text(b, [(label, 11, True, fg)], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    if gated:
        badge = rrect(s, bx + Inches(0.25), Inches(1.85), Inches(1.0), Inches(0.34), PURPLE, radius=0.5)
        text(badge, [("GATE", 9, True, WHITE)], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
textbox(s, Inches(0.7), Inches(4.2), Inches(11.9), Inches(2.6), [
    ("Three subsystems enforce verify-or-reject grounding explicitly:", 15, True, PURPLE),
    ("Evidence-grounded synthesis: verbatim substring check, deterministic aggregation, citation verifier.", 13, False, INK),
    ("Contradiction detection: judgments below the Likert threshold are discarded, not reported with low confidence.", 13, False, INK),
    ("Journal-metadata reconciliation: a metric is reported only when a source states it; conflicts are surfaced, never averaged.", 13, False, INK),
])
BODY_SPIDS[6] = None
notes(s, "Gold boxes are gated. Evaluation is stage-level, in the spirit of "
         "AgentBench, not a single end-to-end demo.")

# 7  Inside the gated path
s = prs.slides.add_slide(BLANK)
chrome(s, 7, "Inside the evidence-grounded synthesis gate")
steps = [
    ("Evidence extraction", "Every field must be a verbatim or near-verbatim substring of the source before it enters the evidence table.", LAV, PURPLE),
    ("Synthesis matrix", "A methods-by-datasets grid built deterministically, with no LLM call, so the aggregation-heavy step adds no hallucination surface.", CREAM, PURPLE),
    ("Narrative generation", "The LLM drafts prose that cites evidence rows.", LAV, PURPLE),
    ("Narrative verifier", "Any sentence whose citation key does not resolve to a verified row is a build error, not a warning.", RGBColor(0xF7,0xE2,0xDE), RED),
]
for i, (t, d, fill, tc) in enumerate(steps):
    cy = Inches(1.5) + i * Inches(1.35)
    card(s, Inches(0.8), cy, Inches(11.6), Inches(1.2), t, [d], fill=fill, title_color=tc)
    if i < 3:
        textbox(s, Inches(6.4), cy + Inches(1.18), Inches(0.6), Inches(0.3),
                [("▼", 12, True, GOLD)])
BODY_SPIDS[7] = None
notes(s, "Structurally close to the evidence-retrieval step in FEVER, except an "
         "unsupported extraction is discarded, not scored 'not enough info'.")

# 8  Algorithm
s = prs.slides.add_slide(BLANK)
chrome(s, 8, "VoRG-Certify: linear-time certification")
textbox(s, Inches(0.7), Inches(1.45), Inches(11.9), Inches(1.1), [
    ("A naive scored implementation checks every generated sentence against every evidence row.", 15, False, INK),
    ("VoRG-Certify hashes the evidence table by citation key once, then certifies the whole narrative in a single pass.", 15, False, INK)])
code = rrect(s, Inches(0.8), Inches(2.7), Inches(7.2), Inches(2.7), RGBColor(0x2B,0x2B,0x2B), radius=0.05)
text(code, [
    ("BuildIndex(E):  H[key(e)] <- e            # expected O(1) each", 12, False, RGBColor(0xEE,0xEE,0xEE)),
    ("Certify(N, H):", 12, False, RGBColor(0xEE,0xEE,0xEE)),
    ("  for each sentence s in N:               # one pass", 12, False, RGBColor(0xEE,0xEE,0xEE)),
    ("    keys <- ExtractKeys(s)                # one regex scan", 12, False, RGBColor(0xEE,0xEE,0xEE)),
    ("    if no keys or key not in H:  reject(s)  # build error", 12, False, RGBColor(0xF5,0xA6,0x23)),
    ("    else:  keep(s)", 12, False, RGBColor(0x9E,0xE0,0x9E)),
], anchor=MSO_ANCHOR.MIDDLE)
callout(s, Inches(8.3), Inches(2.7), Inches(4.3), Inches(1.5),
        [("O(n · m)   →   O(n + M)", 20, True), ("the quadratic term is gone", 12, False)],
        fill=TEAL)
card(s, Inches(8.3), Inches(4.4), Inches(4.3), Inches(1.9), "Legend", [
    "n = evidence rows",
    "m = generated sentences",
    "M = total narrative length",
], fill=LAV)
textbox(s, Inches(0.8), Inches(5.6), Inches(7.2), Inches(1.2), [
    ("Same index-then-certify structure is reused for contradiction judgments and journal-metadata fields, so the bound carries over.", 12, False, GREY)])
BODY_SPIDS[8] = None
notes(s, "This is the technical core reviewers will probe. Stress that "
         "certification stays linear as the evidence base grows.")

# 9  Evaluation design
s = prs.slides.add_slide(BLANK)
chrome(s, 9, "Evaluation design")
grid = [
    ("Full pipeline", "all gates on", GREEN),
    ("Scored ablation", "same decomposition and LLM calls, every gate replaced by a score, nothing dropped", GOLD),
    ("Pattern-mode", "rule-based extraction, gates on", TEAL),
    ("Naive baseline", "one prompt for claims, contradictions, gaps", GREY),
]
for i, (t, d, col) in enumerate(grid):
    gx = Inches(0.8) + (i % 2) * Inches(6.2)
    gy = Inches(1.6) + (i // 2) * Inches(1.7)
    sp = rrect(s, gx, gy, Inches(5.8), Inches(1.5), LAV, radius=0.06)
    bar = rect(s, gx, gy, Inches(0.16), Inches(1.5), col)
    tf = sp.text_frame; tf.word_wrap = True
    tf.margin_left = Inches(0.28)
    p = tf.paragraphs[0]; p.text = t; p.font.bold = True; p.font.size = Pt(15); p.font.color.rgb = PURPLE
    q = tf.add_paragraph(); q.text = d; q.font.size = Pt(12); q.font.color.rgb = INK
callout(s, Inches(0.8), Inches(5.15), Inches(11.7), Inches(1.6), [
    ("Provider Groq, model openai/gpt-oss-120b  ·  3 runs per configuration", 13, True),
    ("Pilot corpus: 10 papers, abstract coverage lifted from 1/10 to 7/10 by Semantic Scholar and OpenAlex backfill", 12, False),
    ("Downstream-error metrics: unsupported sentences in the narrative, retained false-positive contradictions, narrative build failed", 12, False),
], fill=PURPLE)
BODY_SPIDS[9] = None
notes(s, "The scored ablation is the key comparison: reject versus score on "
         "otherwise identical output. Gold labels are authored by correcting "
         "pipeline output, not rubber-stamping it.")

# 10  Results: claim extraction
s = prs.slides.add_slide(BLANK)
chrome(s, 10, "Results: claim extraction")
tb = s.shapes.add_table(4, 4, Inches(1.2), Inches(1.7), Inches(10.9), Inches(2.4)).table
hdr = ["Configuration", "Precision", "Recall", "F1"]
rows = [
    ["Full pipeline (verify-or-reject)", "0.294", "0.889", "0.442"],
    ["Pattern-mode ablation", "0.439", "0.667", "0.510"],
    ["Naive single-LLM baseline", "0.104", "0.333", "0.158"],
]
for j, htext in enumerate(hdr):
    cell = tb.cell(0, j); cell.text = htext
    cell.fill.solid(); cell.fill.fore_color.rgb = PURPLE
    cell.text_frame.paragraphs[0].font.color.rgb = WHITE
    cell.text_frame.paragraphs[0].font.bold = True
    cell.text_frame.paragraphs[0].font.size = Pt(13)
for i, r in enumerate(rows, start=1):
    for j, v in enumerate(r):
        cell = tb.cell(i, j); cell.text = v
        cell.fill.solid(); cell.fill.fore_color.rgb = LAV if i % 2 else WHITE
        cell.text_frame.paragraphs[0].font.size = Pt(12)
callout(s, Inches(1.2), Inches(4.5), Inches(10.9), Inches(1.9), [
    ("Both decomposed configurations beat the naive baseline (F1 2.8x and 3.2x).", 14, True),
    ("Pattern-mode's higher point estimate rides on a 3-sentence gold set and 5x the variance;", 12, False),
    ("the multi-topic study is designed to settle rule-based versus LLM extraction.", 12, False),
], fill=GOLD)
BODY_SPIDS[10] = None
notes(s, "Be honest about the tiny gold set. The point is the next slide.")

# 11  Results: contradiction + gap
s = prs.slides.add_slide(BLANK)
chrome(s, 11, "Results: contradiction detection and research gaps")
callout(s, Inches(0.8), Inches(1.6), Inches(5.7), Inches(2.1), [
    ("Contradiction detection", 15, True),
    ("False-positive rate 0.0", 20, True),
    ("on hand-labelled negative pairs, across all nine runs", 11, False),
], fill=GREEN)
callout(s, Inches(6.8), Inches(1.6), Inches(5.7), Inches(2.1), [
    ("Research-gap detection", 15, True),
    ("recall 0.17   ·   precision@3 = 0.0", 16, True),
    ("this stage has no verify-or-reject gate", 11, False),
], fill=RED)
card(s, Inches(0.8), Inches(4.0), Inches(11.7), Inches(2.5),
     "The concrete failure", [
        "Top-ranked gap: “no studies have applied graph-based generative models for de novo molecular generation.”",
        "Directly contradicted by the corpus's own paper: “Molecular generative Graph Neural Networks for Drug Discovery.”",
        "The candidate gap was generated and ranked, but never checked against the corpus it judges.",
     ], fill=CREAM, title_color=RED)
BODY_SPIDS[11] = None
notes(s, "The green versus red contrast previews the finding. Read the false gap "
         "quote slowly.")

# 12  The finding
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, SW, SH, PURPLE)
rect(s, 0, 0, SW, Inches(0.07), GOLD)
textbox(s, Inches(0.9), Inches(0.7), Inches(11.6), Inches(1.4), [
    ("The finding: a gap-to-failure correspondence", 30, True, WHITE)])
callout(s, Inches(1.1), Inches(2.4), Inches(11.1), Inches(1.5), [
    ("Two gated stages  →  zero output contradicted by the reviewed corpus", 18, True)],
    fill=GREEN)
callout(s, Inches(1.1), Inches(4.1), Inches(11.1), Inches(1.5), [
    ("One ungated stage  →  one confirmed false claim, contradicted by a corpus paper", 18, True)],
    fill=RED)
textbox(s, Inches(1.1), Inches(5.9), Inches(11.1), Inches(1.2), [
    ("The failure lands exactly where the architecture has no gate. This correspondence, not the F1 numbers, is the evidence for build-time rejection over post-hoc scoring.", 13, False, RGBColor(0xE8,0xD8,0xF2))])
deco_circles(s)
BODY_SPIDS[12] = None
notes(s, "The money slide. It emerged during evaluation of the existing "
         "pipeline; it was not staged as a test of VoRG.")

# 13  What this means
sl = content(13, "What this means", [
    (0, "Nothing about the pattern is specific to literature review."),
    (0, "Any pipeline that generates text or structured records from retrieved sources can apply the same accept-or-reject check before passing output downstream."),
    (0, "The evaluation shows where verification is already load bearing, and where its absence produces a concrete, corpus-contradicted failure."),
    (0, "It does not claim VoRG solves hallucination in every setting."),
])
notes(sl, "Generalise, then scope honestly.")

# 14  Limitations and next steps
s = prs.slides.add_slide(BLANK)
chrome(s, 14, "Limitations and next steps")
card(s, Inches(0.8), Inches(1.55), Inches(5.9), Inches(4.7), "Limitations", [
    "One topic with adjudicated gold; three gold claims, so claim-extraction numbers are underpowered.",
    "Pilot corpus was abstract-poor; backfill lifted coverage to 7 of 10.",
    "Multi-topic F1 and the pooled scored-ablation counts are still pending gold annotation.",
], fill=CREAM, title_color=RED)
card(s, Inches(7.0), Inches(1.55), Inches(5.5), Inches(4.7), "Next steps", [
    "Run the matched scored-grounding ablation on identical output.",
    "Extend to three to five gold-annotated topics with an independent annotator.",
    "Apply the verify-or-reject gate to research-gap detection.",
    "Submit to an IEEE Xplore venue; camera-ready carries the multi-topic tables.",
], fill=LAV, title_color=GREEN)
BODY_SPIDS[14] = None
notes(s, "The harness for all three next steps is implemented and released; what "
         "remains is human gold annotation.")

# 15  Contributions recap
s = prs.slides.add_slide(BLANK)
chrome(s, 15, "Contributions")
items = [
    ("Pattern + algorithm", "VoRG stated formally; VoRG-Certify runs in O(n+M), removing the O(n·m) term.", GOLD),
    ("System + harness", "Three gated subsystems in an eight-stage pipeline, with a reproducible evaluation harness, released.", TEAL),
    ("The finding", "A gap-to-failure correspondence: gated stages produce no corpus-contradicted output; the one ungated stage does.", PURPLE),
]
for i, (t, d, col) in enumerate(items):
    cy = Inches(1.7) + i * Inches(1.75)
    oval(s, Inches(0.9), cy + Inches(0.1), Inches(0.9), col)
    textbox(s, Inches(1.05), cy + Inches(0.28), Inches(0.6), Inches(0.5),
            [(str(i + 1), 20, True, WHITE)])
    card(s, Inches(2.1), cy, Inches(10.4), Inches(1.5), t, [d], fill=LAV)
BODY_SPIDS[15] = None
notes(s, "Three chips. This is the slide people photograph.")

# 16  Close
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, SW, SH, PURPLE)
deco_circles(s)
textbox(s, Inches(0.9), Inches(2.5), Inches(11.6), Inches(2.6), [
    ("Make the gate the pipeline, not the score.", 34, True, WHITE),
    ("github.com/harishvidyarthcsecs/Research", 18, False, GOLD),
])
textbox(s, Inches(0.9), Inches(5.2), Inches(11.6), Inches(1.2), [
    ("Thank you.  Questions on the complexity argument and the gap-to-failure result are welcome.", 15, False, RGBColor(0xE8,0xD8,0xF2)),
    ("harishvidyarth.n.2024.csecs@rajalakshmi.edu.in", 12, False, WHITE),
])
notes(s, "Close on the one-line thesis and the repo.")

prs.save(OUT)

# ------------------------------------------------------------------ animate
# python-pptx has no API for transitions or animations. Both are injected as
# OOXML into the saved .pptx. The transition is the plain 2006 <p:transition>;
# the timing tree is the exact shape PowerPoint itself writes for
# "Fade | On Click | By Paragraph" on one body placeholder, so PowerPoint opens
# the file without a repair prompt.
PNS = 'http://schemas.openxmlformats.org/presentationml/2006/main'

FADE = f'<p:transition xmlns:p="{PNS}" spd="med" advClick="1"><p:fade/></p:transition>'


def timing_build(spid):
    return (
        f'<p:timing xmlns:p="{PNS}">'
        '<p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">'
        '<p:childTnLst>'
        '<p:seq concurrent="1" nextAc="seek">'
        '<p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
        '<p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond delay="indefinite"/></p:stCondLst>'
        '<p:childTnLst>'
        '<p:par><p:cTn id="4" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst>'
        '<p:childTnLst>'
        '<p:par><p:cTn id="5" presetID="10" presetClass="entr" presetSubtype="0" '
        'fill="hold" grpId="0" nodeType="clickEffect"><p:stCondLst><p:cond delay="0"/></p:stCondLst>'
        '<p:childTnLst>'
        '<p:set><p:cBhvr><p:cTn id="6" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
        f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'
        '<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>'
        '<p:to><p:strVal val="visible"/></p:to></p:set>'
        '<p:animEffect transition="in" filter="fade"><p:cBhvr>'
        '<p:cTn id="7" dur="500"/>'
        f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>'
        '</p:childTnLst></p:cTn></p:par>'
        '</p:childTnLst></p:cTn></p:par>'
        '</p:childTnLst></p:cTn></p:par>'
        '</p:childTnLst></p:cTn>'
        '<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
        '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>'
        '</p:seq>'
        '</p:childTnLst></p:cTn></p:par></p:tnLst>'
        f'<p:bldLst><p:bldP spid="{spid}" grpId="0" build="p"/></p:bldLst>'
        '</p:timing>'
    )


def _slide_num(name):
    return int(Path(name).name[len("slide"):-len(".xml")])


with zipfile.ZipFile(OUT) as zin:
    names = zin.namelist()
    slide_files = sorted(
        (n for n in names
         if Path(n).parent.as_posix() == "ppt/slides"
         and Path(n).name.startswith("slide") and n.endswith(".xml")),
        key=_slide_num,
    )
    payload = {n: zin.read(n) for n in names}

for name in slide_files:
    idx = _slide_num(name)
    xml = payload[name].decode("utf-8")
    spid = BODY_SPIDS.get(idx)
    inject = FADE + (timing_build(spid) if spid else "")
    if "</p:clrMapOvr>" in xml:
        xml = xml.replace("</p:clrMapOvr>", "</p:clrMapOvr>" + inject, 1)
    else:
        xml = xml.replace("</p:sld>", inject + "</p:sld>", 1)
    payload[name] = xml.encode("utf-8")

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zout:
    for name, data in payload.items():
        zout.writestr(name, data)

n_anim = sum(1 for v in BODY_SPIDS.values() if v)
print(f"wrote {OUT}")
print(f"slides: {len(slide_files)}   transitions: all   paragraph animations: {n_anim}")
