# Price analyzer

## What it does

The price analyzer turns a Persian or English contract / statement of work
into an editable, priced project plan:

1. **Ingest** — upload a file (PDF, DOCX, XLSX, PPTX, HTML, CSV, text) or
   paste text. Extraction reuses `services/extract`, the same pipeline used
   by document processing, so it is script-agnostic: Farsi text extracts as
   Unicode text like any other language.
2. **Analyze** — the contract text is split into scope-of-work sections. If
   an LLM provider is configured (Settings → LLM), it splits the text and
   suggests a category, discipline/role and person-hour estimate per
   section. Without one, a deterministic heading/paragraph heuristic
   produces an editable starting point instead of failing.
3. **Edit** — every section's title, category, role, hours and an optional
   per-section hourly-rate override are editable. Sections can also be added
   or removed by hand.
4. **Price** — cost is computed from user-supplied coefficients stored per
   contract: an hourly rate per role, plus overhead %, contingency %, tax %
   and discount %. Costs recompute live; nothing is ever invented.
5. **WBS & Gantt** — `Generate WBS & Gantt` builds a 3-level work breakdown
   structure (`1` Project → `1.1` Phase → `1.1.1` Task, where phases are the
   section categories present and tasks are the sections themselves) and
   schedules tasks sequentially on a single timeline from a chosen start
   date, using the coefficients' hours-per-day. Regenerating replaces the
   existing schedule and RACI matrix; editing dates/assignee/% complete
   afterwards does not.
6. **RACI matrix** — a starter Responsible/Accountable suggestion is seeded
   per task (Project Manager = Accountable, a placeholder Section Owner =
   Responsible). Participants (columns) and every cell are editable; saving
   replaces the whole matrix for the contract.
7. **Export** — PDF (`reportlab`) and Excel (`openpyxl`) exports include the
   cost breakdown, the WBS table, a drawn Gantt chart and the RACI matrix.

## Integration with existing features

- A contract can be linked to an existing **Project** (`project_id`).
  `Sync phase milestones to project` pushes each WBS phase's title/end date
  into that project's existing `milestones` JSON field.
- `Push cost summary to Reports` creates a new ad-hoc **Report** from the
  current cost breakdown, so it can be edited/exported through the existing
  Reports pipeline.
- Access is gated by its own module RBAC entry (`price_analyzer`), granted
  per user/role under **Access & Features** like every other module.

## Farsi PDF export

PDF export reshapes and bidi-reorders Farsi text (`arabic-reshaper` +
`python-bidi`) so glyphs join and read right-to-left correctly. It also
looks for a Persian-capable TTF (Vazirmatn, Noto Naskh/Sans Arabic, Amiri)
under common system font directories and embeds it if found. If none is
installed on the host, the export still succeeds — the layout and
right-to-left order are still correct — but falls back to Helvetica for
those glyphs, and the PDF says so in its own footer rather than silently
producing broken text. Excel export has no such requirement.

## No LLM configured?

The `Analyze contract` action still works: `split_sections_heuristic` in
`app/services/price_analyzer.py` splits on markdown headings (or, if none
are present, on blank-line-separated paragraphs) and applies a rough
word-count-based hour estimate. It is intentionally conservative — treat it
as a first draft to edit, not a final estimate.
