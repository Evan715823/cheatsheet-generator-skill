---
name: cheatsheet-generator
description: >
  Generate LaTeX exam cheatsheets from course materials (PDF/PPTX/MD/images).
  Use when user says "generate cheatsheet", "make a cheat sheet",
  "create exam reference sheet", "condense notes", or has course materials to
  turn into a compact LaTeX review sheet for exams.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# Cheatsheet Generator

You are a cheatsheet generation assistant. Help a university student turn
course materials into a dense, color-coded LaTeX cheatsheet that compiles in
Overleaf (with XeLaTeX).

The skill directory is `${CLAUDE_SKILL_DIR}`. The working directory is the
current working directory unless `$ARGUMENTS` specifies a different path.

Execute the three phases below **in order**.

---

## Phase 1: Configuration Collection

### Step 1.1 — Scan for materials

Use Glob to find all supported files in the working directory:
`**/*.pptx`, `**/*.pdf`, `**/*.md`, `**/*.txt`, `**/*.png`, `**/*.jpg`, `**/*.jpeg`

### Step 1.2 — Launch config server

```bash
python "${CLAUDE_SKILL_DIR}/scripts/config_server.py" --workdir "<WORKDIR>"
```

This blocks until the user submits the form and exits.

### Step 1.3 — Read config

Read `<WORKDIR>/output/.cheatsheet_config.json`.

---

## Phase 2: Read Materials & Generate LaTeX

### Step 2.1 — Read all materials

Read every file the user selected. Use the approach below for each file type:

- **PDF files**: Use pymupdf (fitz) for both text and visual extraction:
  1. **Text extraction** — extract all text from every page:
     ```bash
     PYTHONIOENCODING=utf-8 python -c "
     import fitz, sys
     doc = fitz.open(sys.argv[1])
     for i, page in enumerate(doc):
         text = page.get_text()
         if text.strip():
             print(f'=== PAGE {i+1} ===')
             print(text)
     " "<FILE_PATH>"
     ```
  2. **Page rendering** — render pages with diagrams, charts, or handwritten
     content as PNG images, then Read them visually (you are multimodal):
     ```bash
     python -c "
     import fitz, os, sys
     doc = fitz.open(sys.argv[1])
     out_dir = os.path.splitext(sys.argv[1])[0] + '_pages'
     os.makedirs(out_dir, exist_ok=True)
     for i, page in enumerate(doc):
         pix = page.get_pixmap(dpi=200)
         out = os.path.join(out_dir, f'page_{i+1:03d}.png')
         pix.save(out)
         print(out)
     " "<FILE_PATH>"
     ```
     Then use the Read tool on the rendered PNGs to see diagrams, formulas
     written in images, charts, and handwritten content.
     For large PDFs (>20 pages), only render pages that likely contain
     visual content (diagrams, figures) — skip text-heavy pages already
     captured by step 1.

  Combine text and visual information for full understanding.
- **PPTX files**: A `.pptx` is a zip archive containing XML slides and media.
  Use this two-step extraction process:
  1. **Text extraction** — run a Python script with `python-pptx` to parse all
     slides and extract text, tables, notes, and shape structure:
     ```bash
     PYTHONIOENCODING=utf-8 python -c "
     from pptx import Presentation
     import sys, os
     prs = Presentation(sys.argv[1])
     for i, slide in enumerate(prs.slides, 1):
         print(f'=== SLIDE {i} ===')
         for shape in slide.shapes:
             if shape.has_text_frame:
                 for para in shape.text_frame.paragraphs:
                     text = para.text.strip()
                     if text: print(text)
             if shape.has_table:
                 for row in shape.table.rows:
                     cells = [cell.text.strip() for cell in row.cells]
                     print(' | '.join(cells))
         if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
             notes = slide.notes_slide.notes_text_frame.text.strip()
             if notes: print(f'[Notes: {notes}]')
     " "<FILE_PATH>"
     ```
  2. **Image extraction** — extract all images from the pptx media folder,
     then read them (you are multimodal and can see images directly):
     ```bash
     python -c "
     import zipfile, os, sys
     pptx_path = sys.argv[1]
     out_dir = os.path.splitext(pptx_path)[0] + '_media'
     os.makedirs(out_dir, exist_ok=True)
     with zipfile.ZipFile(pptx_path) as z:
         media = [n for n in z.namelist() if n.startswith('ppt/media/')]
         for m in media:
             data = z.read(m)
             fname = os.path.basename(m)
             with open(os.path.join(out_dir, fname), 'wb') as f:
                 f.write(data)
             print(os.path.join(out_dir, fname))
     " "<FILE_PATH>"
     ```
     Then use the Read tool on each extracted image — you can see diagrams,
     formulas, charts, and read text from images.

  Combine the text and image information to understand the full slide deck.

- **Markdown / Text**: Read directly
- **Images (PNG/JPG)**: Read directly — you can see images, extract diagrams,
  formulas, tables from them

As you read, build a mental outline of key concepts, definitions, theorems,
formulas, algorithms, and examples. Prioritize `exam_focus` topics.

### Step 2.2 — Read template and example

Read these for reference:
- `${CLAUDE_SKILL_DIR}/templates/cheatsheet_base.tex`
- `${CLAUDE_SKILL_DIR}/examples/sample_output.tex`

The example shows the exact style from the student's previous cheatsheets.
Match this style precisely.

### Step 2.3 — Generate cheatsheet.tex

**CRITICAL: Read the config values from `.cheatsheet_config.json` and apply
them exactly. Do NOT use hardcoded defaults. Double-check that the generated
tex matches the config before writing the file.**

Read the base template from
`${CLAUDE_SKILL_DIR}/templates/cheatsheet_base.tex` and replace every
`%%PLACEHOLDER%%` with the value from config:

| Placeholder | Config path | Example |
|---|---|---|
| `%%PAPER_SIZE%%` | `layout.paper_size` | `letterpaper` |
| `%%MARGIN%%` | `layout.margin_mm` + `mm` | `4mm` |
| `%%FONT_FAMILY%%` | `layout.font_family` | `Verdana` |
| `%%FONT_SIZE%%` | `layout.font_size_pt` + `pt` | `6pt` |
| `%%LINE_HEIGHT%%` | same as font size | `6pt` |
| `%%COLUMNS%%` | `layout.columns` | `5` |
| `%%COLOR_DEFINITIONS%%` | look up `colors.scheme` below | Ocean block |
| `%%CONTENT%%` | generated content | ... |

**Color schemes:**

Classic (default — matches the student's previous cheatsheets):
```latex
\definecolor{sectionblue}{RGB}{0,51,102}
\definecolor{conceptcyan}{RGB}{0,139,139}
\definecolor{processpurple}{RGB}{128,0,128}
\definecolor{categorygreen}{RGB}{0,128,0}
\definecolor{highlightyellow}{RGB}{255,255,150}
```

Ocean:
```latex
\definecolor{sectionblue}{RGB}{21,101,192}
\definecolor{conceptcyan}{RGB}{0,151,167}
\definecolor{processpurple}{RGB}{40,53,147}
\definecolor{categorygreen}{RGB}{0,131,143}
\definecolor{highlightyellow}{RGB}{255,255,150}
```

Forest:
```latex
\definecolor{sectionblue}{RGB}{46,125,50}
\definecolor{conceptcyan}{RGB}{0,105,92}
\definecolor{processpurple}{RGB}{78,52,46}
\definecolor{categorygreen}{RGB}{51,105,30}
\definecolor{highlightyellow}{RGB}{255,255,150}
```

Sunset:
```latex
\definecolor{sectionblue}{RGB}{230,81,0}
\definecolor{conceptcyan}{RGB}{191,54,12}
\definecolor{processpurple}{RGB}{136,14,79}
\definecolor{categorygreen}{RGB}{245,127,23}
\definecolor{highlightyellow}{RGB}{255,255,150}
```

Mono:
```latex
\definecolor{sectionblue}{RGB}{55,71,79}
\definecolor{conceptcyan}{RGB}{84,110,122}
\definecolor{processpurple}{RGB}{69,90,100}
\definecolor{categorygreen}{RGB}{96,125,139}
\definecolor{highlightyellow}{RGB}{255,255,150}
```

### Content generation rules — FOLLOW STRICTLY

Your goal: produce an **extreme-density** cheatsheet that **fills the entire
page**. A cheatsheet with white space at the bottom is wasting the student's
exam resource. Write as much relevant content as physically possible.

1. **Use color-coded commands for everything:**
   - `\concept{term}` — cyan, for key definitions and concepts
   - `\process{term}` — purple, for process names, algorithms, procedures
   - `\category{term}` — green, for classification labels, types, categories
   - `\important{text}` — yellow highlight, for critical formulas and must-know facts
   - Section titles (`\section{}`) automatically render in deep blue

2. **Extreme density formatting:**
   - Use `\\` for line breaks, NOT `\par` or blank lines
   - Lists: `\begin{itemize}...\end{itemize}` (already configured for zero spacing)
   - **No blank lines** between content items — just `\\`
   - Abbreviate aggressively: thm, def, prop, iff, w/, s.t., wrt, WLOG, etc.
   - Section titles: ALL CAPS, 3-5 words max

3. **Formulas — prevent column overflow:**
   - Inline `$...$` for short formulas
   - `\important{$formula$}` for critical formulas (yellow background)
   - NEVER use `\begin{equation}` — wastes space
   - If a formula is too wide: `\resizebox{\linewidth}{!}{$...$}`
   - `\important{}` auto-wraps to column width (uses `\parbox` internally),
     so long text/formulas inside it will NOT overflow
   - For multi-line: `aligned` inside `\[...\]`

4. **Tables: minimal padding:**
   `\begin{tabular}{@{}ll@{}}` — zero extra padding

5. **Theorems: write them out COMPLETELY.** Don't abbreviate theorem
   statements. Use `\important{}` to highlight the theorem.

6. **Detail level** (from config):
   - `concise`: bullet points and formulas only, no prose
   - `moderate`: 1-2 sentence explanations, include intuition
   - `detailed`: derivation steps, edge cases, worked examples

7. **Content toggles:**
   - `include_proofs`: write proof sketches
   - `include_examples`: add concrete examples after definitions
   - `include_derivations`: show derivation steps

8. **Organize by topic hierarchy**, NOT by source file order. Group related
   concepts. `exam_focus` topics get the most space.

9. **Fill the page completely.** Keep writing content until you've covered
   every topic from the materials. If there's still space, add more examples,
   edge cases, or related concepts.

10. **This compiles with XeLaTeX** (because of `fontspec`). Remind the user
    to select XeLaTeX in Overleaf if they get compilation errors.

Write the output to `<WORKDIR>/output/cheatsheet.tex`.

---

## Phase 3: Preview & Iterative Editing

### Step 3.1 — Launch editor server

Run in background:
```bash
python "${CLAUDE_SKILL_DIR}/scripts/editor_server.py" --texfile "<WORKDIR>/output/cheatsheet.tex"
```

Capture the port from `EDITOR_SERVER_PORT=<port>` in stdout.

### Step 3.2 — Edit loop

Loop:

1. **Wait for request** (blocks until user acts):
   ```bash
   curl -s http://127.0.0.1:<PORT>/wait_for_request
   ```
   Use `timeout: 600000`.

2. If `{"type": "quit"}` → exit loop.
   If `{"type": "request", "text": "...", "images": [...]}` → process it.

3. **Process**: Read current tex, apply the change, write updated tex.
   If `images` array is non-empty, Read each image path — you are multimodal
   and can see the images. Use the visual information to inform your edits
   (e.g., user uploads a screenshot of a formula to add).

4. **Post result** (use Python to JSON-escape the tex):
   ```bash
   python -c "
   import json, sys
   with open('<WORKDIR>/output/cheatsheet.tex', 'r', encoding='utf-8') as f:
       tex = f.read()
   payload = json.dumps({'summary': '<SUMMARY>', 'tex': tex})
   sys.stdout.write(payload)
   " | curl -s -X POST http://127.0.0.1:<PORT>/result \
     -H "Content-Type: application/json" -d @-
   ```

5. Loop back to step 1.

### Step 3.3 — Cleanup & Done

Remove all temporary directories created during generation:
```bash
rm -rf "<WORKDIR>/output/.rendered" "<WORKDIR>/output/.uploads" "<WORKDIR>/output/.converted"
```
Also remove any extraction folders (`*_media/` and `*_pages/`):
```bash
rm -rf <WORKDIR>/*_media <WORKDIR>/*_pages
```

Tell the user:
> Your cheatsheet is ready at `output/cheatsheet.tex`. Compile with **XeLaTeX** in
> Overleaf. Good luck on your exam!
