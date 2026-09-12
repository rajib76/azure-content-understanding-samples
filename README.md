# Document extraction samples

Runnable scripts for turning documents into structured fields, on two platforms:

- **[Azure Content Understanding](https://learn.microsoft.com/azure/ai-services/content-understanding/)** —
  prebuilt analyzers, plus a custom field schema you define yourself.
- **[Databricks `ai_extract`](https://docs.databricks.com/aws/en/agents/agent-bricks/intelligent-document-processing)** —
  the Agent Bricks Intelligent Document Processing function, called over REST.

Same sample documents through both, so the approaches are directly comparable.
Walkthroughs: [tutorial.html](tutorial.html) (Azure),
[tutorial_databricks.html](tutorial_databricks.html) (Databricks).

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then fill in whichever platform you are using
```

## Azure Content Understanding

Needs a Microsoft Foundry resource in a
[supported region](https://learn.microsoft.com/azure/ai-services/content-understanding/language-region-support),
with a chat-completion and an embedding deployment on it. Authenticate with `az login`,
or set `CONTENTUNDERSTANDING_KEY` in `.env`.

```bash
python create_setup.py                                              # once per resource
python analyze_document.py samples/invoice_usd.pdf prebuilt-invoice  # a prebuilt analyzer
python create_analyzer.py --recreate                                 # your own schema
python analyze_document.py samples/invoice_usd.pdf custom_invoice_extended
```

| Script | Does | Bills |
|---|---|---|
| `create_setup.py` | Writes the model-deployment mapping onto the resource | no |
| `show_defaults.py` | Reads that mapping back | no |
| `show_analyzer.py` | Prints an analyzer definition; `--list` for all 88 | no |
| `create_analyzer.py` | Creates a custom analyzer from a field schema | no |
| `analyze_document.py` | Runs an analyzer against a local file | **yes** |

`create_setup.py` is required first: Content Understanding borrows model deployments from
your Foundry resource rather than hosting any, so it needs to know which deployment serves
which model name.

## Databricks ai_extract

Needs serverless compute, Unity Catalog, a nonzero serverless budget policy, and a region
where AI Functions are available. A 404 on the endpoint means one of those is missing.

```bash
export DATABRICKS_HOST="https://dbc-xxxxxxxx-xxxx.cloud.databricks.com"
export DATABRICKS_TOKEN="<token>"   # Settings > Developer > Access tokens

python databricks_extract.py samples/invoice_usd.pdf          schemas/invoice.json
python databricks_extract.py samples/invoice_spreadsheet.xlsx schemas/invoice.json
python databricks_extract.py samples/purchase_orders.csv      schemas/purchase_orders.json
```

| Script | Does |
|---|---|
| `databricks_extract.py` | Reads a PDF, xlsx or CSV locally, posts the text to `ai-extract` |
| `databricks_ai_extract.sh` | The same call as raw `curl`, for a quick check |
| `databricks_check_auth.sh` | Diagnoses a 401: bad credential, or endpoint unavailable? |

`ai_extract` takes **text, not files**, so the reading happens locally — `pypdf` for PDFs,
`openpyxl` for Excel, the standard library for CSV. Schemas are JSON files in `schemas/`.

Useful flags: `--show-text` prints what would be sent, `--dry-run` prints the whole
request, `--citations` asks for the source span behind each value, `--json OUT` saves the
response.

## Samples

All synthetic, and built to disagree with each other so a schema gets tested rather than
demonstrated.

| File | Tests |
|---|---|
| `invoice_usd.pdf` | Baseline: USD, Net 30, shipping line, remittance details |
| `invoice_eur.pdf` | EUR with comma decimals, German vendor, **no** shipping line, Net 60 |
| `invoice_gbp_net14.pdf` | GBP, UK vendor, Net 14 — a term absent from the enum |
| `credit_memo.pdf` | Classification: a credit, not an invoice; no payment due |
| `receipt_paid.pdf` | Classification: already paid in full |
| `invoice_spreadsheet.xlsx` | Excel input, formula values cached |
| `invoice_spreadsheet_formulas.xlsx` | Excel input, formulas **without** cached values |
| `purchase_orders.csv` | Tabular input, 7 rows, 4 currencies, mixed statuses |

Regenerate with `.venv/bin/pip install -r requirements-dev.txt`.

## Notes from building this

Things that cost time and are not obvious from either set of docs.

**Azure Content Understanding**

- An `analyzerId` cannot contain `-`. Creation fails with `InvalidAnalyzerId`, even though
  every Microsoft prebuilt is named with hyphens. Use underscores.
- Pick the generation method before polishing the description. An `EXTRACT` field returns
  empty when the value is not literally on the page, however well described. A `Currency`
  field stayed blank until it became `GENERATE` — the invoice writes `$4,153.97` and never
  says "USD".
- Check `supportedModels` on the analyzer. `prebuilt-invoice` accepts no mini model for
  completion; mapping the alias to one anyway raises no error and still returns results.
- `update_defaults` merges rather than replaces. Old entries survive until deleted.
- Confidence is not comparable across analyzers or input formats. On one file,
  `prebuilt-invoice` scored 0.31–0.43 while a custom schema scored 0.72–0.99, every value
  correct both times — re-rendering the document with proper typesetting changed nothing,
  so it is the analyzer, not the document. The prebuilt's *highest* scores were on fields
  that came back **empty**. Office formats report a flat `1` on every field: no OCR step,
  so no recognition uncertainty, and no bounding boxes either.

**Databricks ai_extract**

- SQL and REST spell the options differently: `enableConfidenceScores` in SQL's `map()`,
  `enable_confidence_scores` in the REST body. Both are off by default.
- The schema is a JSON **string** in SQL but a JSON **object** over REST.
- Version 2.1 nests fields under `response`, with `confidence_score` and `citation_ids`
  per field; `citation_ids` index into `metadata.citations` rather than carrying the span
  inline. Parse the document first and citations carry a page and bounding box; pass a
  plain string and they carry character offsets.
- Limits: 256 fields per schema, 12 nesting levels, 500 enum values, 1M tokens total,
  120 requests per minute per workspace, 100 pages per document over REST.

**Both**

- Excel formulas are read as their cached value, never evaluated. Excel writes that cache
  when it saves, so files from real users are fine; script-generated ones often are not,
  and every total reads as blank.
- Neither service OCRs a PDF that has no text layer as part of field extraction. Azure's
  base analyzer does the OCR itself; on Databricks that is `ai_parse_document`, a separate
  step before `ai_extract`.

## License

MIT
