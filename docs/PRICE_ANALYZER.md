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
   and discount %. Costs recompute live; nothing is ever invented. Defaults
   target the Iranian market — the currency defaults to **Toman (تومان)**
   with Toman-scale hourly rates and a 9% VAT (`tax_percent`), and the module
   defaults to **Farsi** — all editable per contract.
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

The `Analyze contract` action still works without any AI provider.
`split_sections_heuristic` in `app/services/price_analyzer.py` does real
structural analysis rather than a naive split:

- **Structure detection** — it recognizes Persian contract structure
  (`ماده`, `تبصره`, `بند`, `فصل`) and numbered clauses, falling back to
  markdown headings and then blank-line paragraphs.
- **Bilingual classification** — each section is categorized (requirements,
  design, development, testing, …) and assigned a discipline/role from
  Persian + English keyword tables, with text normalization that folds the
  zero-width non-joiner and Arabic yeh/kaf so matching is robust.
- **Boilerplate handling** — purely legal/administrative clauses (payment,
  termination, confidentiality, parties, …) are kept visible but priced at
  zero effort so they don't inflate the estimate. Note that vendor-side
  obligations (`تعهدات مجری/پیمانکار`) are treated as real scope, only the
  client-side `تعهدات کارفرما` is boilerplate.

It is still a first draft to edit, not a final estimate — and the UI shows a
hint after an offline analysis pointing to Settings → LLM for sharper
extraction. When an LLM *is* configured, the same keyword inference repairs
any category/role the model omits or mislabels, and the response's `method`
field (`ai` vs `heuristic`) tells the UI which path ran.
