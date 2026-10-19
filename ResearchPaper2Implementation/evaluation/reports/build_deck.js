// Builds the SPIRES / arm-comparison deck.
//   node reports/build_deck.js
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const BLOCK3 = JSON.parse(fs.readFileSync(path.join(__dirname, "arm_block3.json"), "utf8"));

// Palette: ink navy for dark slides, a cool near-white ground, and annotation
// vermilion as the single accent -- the colour of a marked-up statute. Green and
// vermilion also carry semantic load on slide 2 (captured vs lost), so they are
// doing work rather than decorating.
const INK = "1C2233";
const INK_SOFT = "2A3350";
const GROUND = "F6F7FA";
const PANEL = "FFFFFF";
const SUNK = "ECEEF4";
const ACCENT = "B5432F";
const KEEP = "2F6B4F";
const KEEP_BG = "E6F0EA";
const LOSE_BG = "FAEAE7";
const MUTED = "6B7286";
const RULE = "DCE0EA";

const SERIF = "Cambria";
const SANS = "Calibri";
const MONO = "Courier New";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";           // 13.3 x 7.5 -- must precede addSlide
pres.author = "Connor Macdougall";
pres.title = "SPIRES for Legal Text";

const W = 13.3, H = 7.5, M = 0.62;

// ---------------------------------------------------------------- helpers
function darkSlide() {
  const s = pres.addSlide();
  s.background = { color: INK };
  return s;
}
function lightSlide() {
  const s = pres.addSlide();
  s.background = { color: GROUND };
  return s;
}
function eyebrow(s, text, opts = {}) {
  s.addText(text, {
    x: M, y: opts.y || 0.42, w: 8, h: 0.26, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 11, charSpacing: 1.4,
    color: opts.color || ACCENT,
  });
}
function title(s, text, opts = {}) {
  s.addText(text, {
    x: M, y: opts.y || 0.74, w: opts.w || W - 2 * M, h: opts.h || 0.72,
    isTextBox: true, margin: 0, fontFace: SERIF, fontSize: opts.size || 34,
    bold: true, color: opts.color || INK, valign: "top",
  });
}
// A mono chip. The deck's one repeated motif, matching the graph's own label
// style (SP_Norm, @s6-1) rather than being invented ornament.
function chip(s, text, x, y, fg, bg, w) {
  s.addShape(pres.ShapeType.roundRect, {
    x, y, w: w || 1.25, h: 0.28, fill: { color: bg }, rectRadius: 0.04, line: { color: bg },
  });
  s.addText(text, {
    x, y, w: w || 1.25, h: 0.28, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 10, color: fg, align: "center", valign: "middle",
  });
}
function panel(s, x, y, w, h, fill) {
  s.addShape(pres.ShapeType.rect, {
    x, y, w, h, fill: { color: fill || PANEL }, line: { color: RULE, width: 0.75 },
  });
}
function notes(s, t) { s.addNotes(t); }

// ================================================================ SLIDE 1
{
  const s = darkSlide();
  eyebrow(s, "SLIDE 1  ·  METHOD", { color: "E0A090" });
  title(s, "SPIRES, adapted from biomedicine to statute", { color: "FFFFFF" });
  s.addText(
    "Caufield et al. (Bioinformatics, 2024) extract structured knowledge into a LinkML schema by " +
    "zero-shot prompting. The method is domain-neutral; the schema is not. Ours replaces their " +
    "biomedical ontology with the structure a legislative provision actually has.",
    { x: M, y: 1.52, w: 11.9, h: 0.68, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 14, color: "C6CBDA", lineSpacing: 20 });

  const rows = [
    ["Schema target", "Genes, diseases, chemicals grounded to OBO ontologies",
     "Norms: deontic modality, bearer, action, object, conditions, exceptions"],
    ["Grounding", "sqlite:obo — every entity linked to an ontology id",
     "Disabled. The bundled ontologies are biomedical and irrelevant to statute"],
    ["Core construct", "Entity–attribute assertions",
     "OBLIGATION / PROHIBITION / PERMISSION / DISAPPLICATION / APPLIES-WHEN"],
    ["Nesting", "CompoundExpression for measurements and relationships",
     "CompoundExpression for Norm, Condition, Exemption — so structure survives"],
    ["Cross-references", "Not applicable to abstracts",
     "Taken from regex instead: it found 28 provisions to SPIRES' 10"],
  ];

  let y = 2.60;
  s.addText("SPIRES AS PUBLISHED", { x: 4.42, y: 2.30, w: 3.6, h: 0.26, isTextBox: true,
    margin: 0, fontFace: MONO, fontSize: 10, charSpacing: 1, color: "8B93A8" });
  s.addText("ADAPTED FOR SCHEDULE 1", { x: 8.28, y: 2.30, w: 4.4, h: 0.26, isTextBox: true,
    margin: 0, fontFace: MONO, fontSize: 10, charSpacing: 1, color: "E0A090" });

  rows.forEach((r, i) => {
    if (i % 2 === 0) {
      s.addShape(pres.ShapeType.rect, { x: M, y: y - 0.09, w: 12.06, h: 0.80,
        fill: { color: INK_SOFT }, line: { color: INK_SOFT } });
    }
    s.addText(r[0], { x: M + 0.16, y: y - 0.09, w: 3.5, h: 0.80, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 13, bold: true, color: "FFFFFF", valign: "middle" });
    s.addText(r[1], { x: 4.42, y: y - 0.09, w: 3.72, h: 0.80, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 11.5, color: "9AA2B6", valign: "middle" });
    s.addText(r[2], { x: 8.28, y: y - 0.09, w: 4.4, h: 0.80, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 11.5, color: "F0DCD6", valign: "middle" });
    y += 0.84;
  });

  notes(s, "SPIRES is domain-neutral in method and biomedical in its shipped schemas. " +
    "The adaptation is the LinkML schema: norms with deontic modality rather than entities " +
    "with ontology ids. Grounding was switched off. Cross-reference edges come from the " +
    "existing regex parser, which measured 28 provisions against SPIRES' 10.");
}

// ================================================================ SLIDE 2
{
  const s = lightSlide();
  eyebrow(s, "SLIDE 2  ·  EXTRACTION FIDELITY");
  title(s, "APP 6.1 — what reached the graph, and what did not");

  // --- left: source text
  panel(s, M, 1.62, 5.24, 2.52);
  s.addText("SOURCE TEXT", { x: M + 0.18, y: 1.76, w: 3, h: 0.24, isTextBox: true,
    margin: 0, fontFace: MONO, fontSize: 9.5, charSpacing: 1, color: MUTED });
  s.addText([
    { text: "If an APP entity ", options: { color: INK } },
    { text: "holds", options: { color: ACCENT, bold: true } },
    { text: " personal information ", options: { color: INK } },
    { text: "about an individual", options: { color: ACCENT, bold: true } },
    { text: " that was ", options: { color: INK } },
    { text: "collected for a particular purpose (the primary purpose)", options: { color: ACCENT, bold: true } },
    { text: ", the entity ", options: { color: INK } },
    { text: "must not use or disclose", options: { color: KEEP, bold: true } },
    { text: " the information ", options: { color: INK } },
    { text: "for another purpose (the secondary purpose)", options: { color: KEEP, bold: true } },
    { text: " unless: (a) ", options: { color: INK } },
    { text: "the individual has consented", options: { color: KEEP, bold: true } },
    { text: "; or (b) ", options: { color: INK } },
    { text: "subclause 6.2 or 6.3 applies", options: { color: KEEP, bold: true } },
    { text: ".", options: { color: INK } },
  ], { x: M + 0.18, y: 2.06, w: 4.88, h: 1.96, isTextBox: true, margin: 0,
       fontFace: SANS, fontSize: 12.5, lineSpacing: 19, valign: "top" });

  chip(s, "captured", M + 0.18, 4.26, KEEP, KEEP_BG, 1.0);
  chip(s, "lost", M + 1.30, 4.26, ACCENT, LOSE_BG, 0.7);
  s.addText("Colour marks the fragment's fate in the extraction.",
    { x: M + 2.12, y: 4.26, w: 3.3, h: 0.28, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 10.5, color: MUTED, valign: "middle" });

  // --- right: captured
  panel(s, 6.22, 1.62, 6.46, 2.52, PANEL);
  s.addShape(pres.ShapeType.ellipse, { x: 6.40, y: 1.74, w: 0.22, h: 0.22,
    fill: { color: KEEP }, line: { color: KEEP } });
  s.addText("CAPTURED IN THE GRAPH", { x: 6.72, y: 1.72, w: 4, h: 0.26, isTextBox: true,
    margin: 0, fontFace: MONO, fontSize: 9.5, charSpacing: 1, color: KEEP });
  s.addText([
    { text: "SP_Norm", options: { fontFace: MONO, color: INK, bold: true } },
    { text: "  modality = PROHIBITION\n", options: { fontFace: SANS, color: INK } },
    { text: "SP_Action", options: { fontFace: MONO, color: INK, bold: true } },
    { text: "  “use or disclose”\n", options: { fontFace: SANS, color: INK } },
    { text: "SP_Condition", options: { fontFace: MONO, color: INK, bold: true } },
    { text: "  “for a secondary purpose”\n", options: { fontFace: SANS, color: INK } },
    { text: "SP_Exemption", options: { fontFace: MONO, color: INK, bold: true } },
    { text: "  “the individual has consented…”\n", options: { fontFace: SANS, color: INK } },
    { text: "SP_Exemption", options: { fontFace: MONO, color: INK, bold: true } },
    { text: "  “subclause 6.2 or 6.3 applies…”  src=6.2, 6.3\n", options: { fontFace: SANS, color: INK } },
    { text: "SP_REFERS_TO", options: { fontFace: MONO, color: INK, bold: true } },
    { text: "  → 6.2, → 6.3   ·   ← 6.4 (inbound)", options: { fontFace: SANS, color: INK } },
  ], { x: 6.40, y: 2.06, w: 6.1, h: 2.0, isTextBox: true, margin: 0,
       fontSize: 11.5, lineSpacing: 19, valign: "top" });

  // --- bottom: lost + defects
  panel(s, M, 4.72, 5.24, 2.16, PANEL);
  s.addShape(pres.ShapeType.ellipse, { x: M + 0.18, y: 4.84, w: 0.22, h: 0.22,
    fill: { color: ACCENT }, line: { color: ACCENT } });
  s.addText("LOST IN EXTRACTION", { x: M + 0.50, y: 4.82, w: 4, h: 0.26, isTextBox: true,
    margin: 0, fontFace: MONO, fontSize: 9.5, charSpacing: 1, color: ACCENT });
  s.addText([
    { text: "“holds” — the possession precondition. Element 6.1-E01 has no node.", options: {} },
    { text: "“about an individual” — the data subject is absent entirely.", options: {} },
    { text: "“collected for a particular purpose (the primary purpose)” — the primary purpose is never established. Element 6.1-E02 is unreachable.", options: {} },
    { text: "“APP” — the bearer is stored as bare “entity”.", options: {} },
    { text: "Paragraph labels (a) / (b) — exception (a) carries no source.", options: {} },
  ].map((o, i, arr) => ({ text: o.text, options: { bullet: true, breakLine: i < arr.length - 1,
      fontFace: SANS, fontSize: 10.5, color: INK, paraSpaceAfter: 4 } })),
    { x: M + 0.18, y: 5.16, w: 4.88, h: 1.60, isTextBox: true, margin: 0, valign: "top" });

  panel(s, 6.22, 4.72, 6.46, 2.16, SUNK);
  s.addText("DEFECTS VISIBLE IN THE GRAPH ITSELF", { x: 6.40, y: 4.84, w: 5, h: 0.26,
    isTextBox: true, margin: 0, fontFace: MONO, fontSize: 9.5, charSpacing: 1, color: MUTED });
  s.addText([
    { text: "Two SP_Norm nodes where the clause states one prohibition with two exceptions — the merge declined to collapse them because their object phrasing differs.", options: {} },
    { text: "Each exception is stored twice: once from the first extraction pass, once from the verification pass that re-quotes it with “unless”.", options: {} },
    { text: "SP_REFERS_TO edges come from the regex parser, not SPIRES — over 62 clauses the regex found cross-references in 28 provisions against SPIRES' 10.", options: {} },
  ].map((o, i, arr) => ({ text: o.text, options: { bullet: true, breakLine: i < arr.length - 1,
      fontFace: SANS, fontSize: 10.5, color: INK, paraSpaceAfter: 5 } })),
    { x: 6.40, y: 5.16, w: 6.1, h: 1.60, isTextBox: true, margin: 0, valign: "top" });

  notes(s, "Modality, the regulated act, the condition and both exceptions survive. " +
    "What is lost is the clause's preconditions: holding, the data subject, and the primary " +
    "purpose. Those are elements 6.1-E01 and 6.1-E02, and neither is reachable from the graph.");
}

// ================================================================ SLIDES 3-9
const ARMS = [
  ["none", "Control · no supplementary context",
   "Block 3 says only that nothing was retrieved. The target clause and the task rules are all the model sees.",
   "1 LLM call", "no database"],
  ["full-corpus", "Control · the whole Schedule pasted",
   "All 134 corpus documents verbatim, including the target itself. No retrieval, no selection.",
   "1 LLM call", "no database"],
  ["kg", "EDC graph · triples plus provision text",
   "EDC entity extractor seeds the graph, a hop-limited walk retrieves a subgraph, and it is serialised as flat triples alongside the text of cross-referenced clauses.",
   "2 LLM calls", ":AppNode — 369 nodes"],
  ["rp1", "RP1 concept graph · selected whole",
   "Twenty-one entities with descriptions, ordered deontic-first. Too small to retrieve from, so everything is included and only the emphasis varies.",
   "1 LLM call", ":RP1Entity — 21 nodes"],
  ["kg-text-only", "Ablation of kg · triples withheld",
   "Identical seeding, retrieval and provision text to kg. The single difference is that the triples never reach the prompt — which isolates what the graph itself contributes.",
   "2 LLM calls", ":AppNode — 369 nodes"],
  ["spires", "SPIRES norm graph",
   "The target clause detected by regex, then a one-hop walk over SP_REFERS_TO and SP_DISAPPLIES in both directions. Inbound matters: 2.1 is misleading until 2.2, which points at it, is in view.",
   "1 LLM call", ":SP_* — 533 nodes"],
  ["spires-hybrid", "SPIRES norms plus statutory text",
   "The same walk, with the verbatim text of every provision it reached appended in a separate labelled section. Structure says which rule is which; text says what each one says.",
   "1 LLM call", ":SP_* + :AppNode"],
];

function excerpt(text, maxChars, maxLines) {
  const lines = text.replace(/^={5,}$/gm, "─".repeat(74)).split("\n");
  const out = [];
  let n = 0;
  for (const ln of lines) {
    if (out.length >= maxLines || n + ln.length > maxChars) break;
    out.push(ln.length > 96 ? ln.slice(0, 94) + "…" : ln);
    n += ln.length + 1;
  }
  return out.join("\n");
}

ARMS.forEach(([key, subtitle, blurb, calls, source], idx) => {
  const s = lightSlide();
  eyebrow(s, `SLIDE ${idx + 3}  ·  ARM ${idx + 1} OF 7`);
  s.addText(key, { x: M, y: 0.72, w: 6.4, h: 0.52, isTextBox: true, margin: 0,
    fontFace: SERIF, fontSize: 30, bold: true, color: INK, valign: "middle" });
  s.addText(subtitle, { x: M, y: 1.26, w: 11.9, h: 0.30, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 14, italic: true, color: ACCENT });
  s.addText(blurb, { x: M, y: 1.66, w: 11.9, h: 0.62, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 12.5, color: INK, lineSpacing: 18, valign: "top" });

  // stat strip, four cells across the full width -- no column to collide with the panel
  const b = BLOCK3[key];
  const stats = [
    ["BLOCK 3 BODY", `${b.body_chars.toLocaleString()} chars`],
    ["WHOLE PROMPT", `${b.prompt_chars.toLocaleString()} chars`],
    ["COST", calls],
    ["GRAPH READ", source],
  ];
  stats.forEach((st, i) => {
    const x = M + i * 3.02;
    s.addShape(pres.ShapeType.rect, { x, y: 2.40, w: 2.86, h: 0.62,
      fill: { color: SUNK }, line: { color: SUNK } });
    s.addText(st[0], { x: x + 0.16, y: 2.46, w: 2.6, h: 0.22, isTextBox: true, margin: 0,
      fontFace: MONO, fontSize: 8.5, charSpacing: 0.8, color: MUTED });
    s.addText(st[1], { x: x + 0.16, y: 2.68, w: 2.6, h: 0.28, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 12.5, bold: true, color: INK });
  });

  panel(s, M, 3.20, 12.06, 3.72, PANEL);
  s.addText(`WHAT THIS ARM PUTS IN BLOCK 3 — APP 6.1, RUN 1${b.body_chars > 10 ? "" : "  (header only — there is no body)"}`,
    { x: M + 0.2, y: 3.30, w: 9, h: 0.22,
      isTextBox: true, margin: 0, fontFace: MONO, fontSize: 9, charSpacing: 1, color: MUTED });
  // The header is nearly identical across arms; the body is the arm. Fall back to the
  // header only for `none`, where the absence of a body IS the distinguishing fact.
  s.addText(excerpt(b.body_chars > 10 ? b.body : b.block3, 3000, 18), {
    x: M + 0.2, y: 3.56, w: 11.66, h: 3.26, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 8.5, color: INK, lineSpacing: 12.2, valign: "top" });

  if (b.body_chars > 1500) {
    s.addText(`excerpt — this arm's block 3 body runs to ${b.body_chars.toLocaleString()} characters`, {
      x: M, y: 6.98, w: 8, h: 0.24, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 10, italic: true, color: MUTED });
  }
  notes(s, `${key}: ${blurb}`);
});

// ================================================================ SLIDE 10
{
  const s = darkSlide();
  eyebrow(s, "SLIDE 10  ·  WHERE THE GRAPH WINS", { color: "E0A090" });
  title(s, "Cost: a fifth of full-corpus, on a par with no context at all",
    { color: "FFFFFF", size: 30 });

  const stats = [
    ["27,014", "tokens · spires", "19,681 no-context  ·  124,989 full-corpus", true],
    ["$0.00010", "per scenario · spires", "$0.00012 no-context  ·  $0.00040 full-corpus", true],
    ["770", "context tokens · APP 6.1", "0 no-context  ·  13,013 full-corpus", false],
  ];
  stats.forEach((st, i) => {
    const x = M + i * 4.06;
    s.addShape(pres.ShapeType.rect, { x, y: 1.72, w: 3.82, h: 2.06,
      fill: { color: INK_SOFT }, line: { color: INK_SOFT } });
    s.addText(st[0], { x: x + 0.24, y: 1.84, w: 3.4, h: 0.76, isTextBox: true, margin: 0,
      fontFace: SERIF, fontSize: 38, bold: true, color: "E8A48E", valign: "middle" });
    s.addText(st[1], { x: x + 0.24, y: 2.64, w: 3.4, h: 0.3, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 13, bold: true, color: "FFFFFF" });
    s.addText(st[2], { x: x + 0.24, y: 3.00, w: 3.4, h: 0.62, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 10.5, color: "9AA2B6", valign: "top" });
  });

  s.addText("Against the no-context control the graph costs slightly MORE; against pasting the Schedule it costs a fifth as much.",
    { x: M, y: 3.90, w: 12.06, h: 0.28, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 12, italic: true, color: "C6CBDA" });

  s.addText("Total prompt + completion tokens across all 9 runs", { x: M, y: 4.28, w: 6, h: 0.28,
    isTextBox: true, margin: 0, fontFace: MONO, fontSize: 10, charSpacing: 1, color: "8B93A8" });

  s.addChart(pres.ChartType.bar, [{
    name: "Total tokens",
    labels: ["none", "kg-text-only", "spires", "spires-hybrid", "rp1", "kg", "full-corpus"],
    values: [19681, 23024, 27014, 28328, 29548, 46848, 124989],
  }], {
    x: M, y: 4.56, w: 12.06, h: 2.34,
    barDir: "bar", showTitle: false, showLegend: false,
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: "FFFFFF",
    dataLabelFontFace: SANS, dataLabelFontSize: 10, dataLabelFormatCode: "#,##0",
    chartColors: ["8B93A8", "C4735C", "C4735C", "C4735C", "8B93A8", "8B93A8", "B5432F"],
    catAxisLabelColor: "C6CBDA", catAxisLabelFontFace: MONO, catAxisLabelFontSize: 11,
    valAxisLabelColor: "8B93A8", valAxisLabelFontSize: 9, valAxisMaxVal: 140000,
    valGridLine: { color: "2A3350", size: 1 }, catGridLine: { style: "none" },
    valAxisLineShow: false, catAxisLineShow: false,
  });

  notes(s, "Cost is the clearest separation in the study and needs no interpretation. " +
    "full-corpus spends 8,904 tokens per scenario on APP 4.4 because it produces one or " +
    "two scenarios from a 13,000-token prompt.");
}

// ================================================================ SLIDE 11
{
  const s = lightSlide();
  eyebrow(s, "SLIDE 11  ·  WHERE THE GRAPH WINS");
  title(s, "The graph against both controls, after readable serialisation", { size: 29 });

  const cards = [
    ["Diversity-adjusted scenarios",
     ["6.2", "no context"], ["16.8", "SPIRES"], ["14.7", "full corpus"],
     "Raw counts flatter redundant output, so each run is discounted by its own self-BLEU. " +
     "The graph beats BOTH controls here, and the lead survives size control on all three subclauses."],
    ["Behaviours reproduced in all three runs",
     ["11%", "no context"], ["40%", "SPIRES"], ["6%", "full corpus"],
     "Temperature 0 is not deterministic. spires reproduces two in five of the behaviours it can " +
     "reach across three identical runs; both controls manage one in ten or worse."],
    ["Cross-referenced element coverage",
     ["36%", "no context"], ["64%", "SPIRES"], ["64%", "full corpus"],
     "The tier needing a provision the target only points at. The graph now MATCHES pasting the " +
     "entire Schedule — on a fifth of the tokens — where it trailed by 9 points before."],
  ];

  cards.forEach((c, i) => {
    const y = 1.62 + i * 1.74;
    panel(s, M, y, 12.06, 1.56, i === 1 ? SUNK : PANEL);
    s.addText(c[0], { x: M + 0.26, y: y + 0.18, w: 5.4, h: 0.3, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 14, bold: true, color: INK });
    s.addText(c[4], { x: M + 0.26, y: y + 0.54, w: 5.4, h: 0.88, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 11, color: INK, lineSpacing: 16, valign: "top" });

    // three figures side by side: control, graph, control
    [c[1], c[2], c[3]].forEach((f, k) => {
      const x = M + 6.10 + k * 1.99;
      const isGraph = k === 1;
      s.addText(f[0], { x, y: y + 0.24, w: 1.86, h: 0.62, isTextBox: true, margin: 0,
        fontFace: SERIF, fontSize: isGraph ? 34 : 24, bold: true,
        color: isGraph ? ACCENT : MUTED, align: "center", valign: "middle" });
      s.addText(f[1], { x, y: y + 0.92, w: 1.86, h: 0.28, isTextBox: true, margin: 0,
        fontFace: MONO, fontSize: 9, color: isGraph ? INK : MUTED, align: "center" });
    });
  });

  s.addText(
    "The graph wins two and ties the third — but only since the norms were rendered as sentences: that " +
    "one change moved overall coverage 11 points. Two further controls bound all of it: " +
    "the coverage judge is measurably lenient (κ = 0.451, precision 0.56), and rephrasing one paragraph " +
    "of the prompt moves cross-referenced coverage by up to 9.1 points. n = 3 subclauses.",
    { x: M, y: 6.90, w: 12.06, h: 0.42, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 10, italic: true, color: MUTED, valign: "top" });

  notes(s, "These are the metrics most favourable to the knowledge graph. The honest framing " +
    "is that they are real but bounded: full-corpus still leads cross-referenced coverage at " +
    "64%, and the format control shows adjacent arms are not separable.");
}

pres.writeFile({ fileName: path.join(__dirname, "SPIRES_Arms_Deck.pptx") })
  .then(f => console.log("wrote", f));
