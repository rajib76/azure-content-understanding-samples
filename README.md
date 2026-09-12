# Azure Content Understanding — samples

Small, runnable scripts for [Azure Content Understanding](https://learn.microsoft.com/azure/ai-services/content-understanding/):
configure a resource, run a prebuilt analyzer, then build a custom field schema and run
that instead. Includes sample documents (PDF and Excel) and a
[walkthrough](tutorial.html).

## Setup

Requires Python 3.9+, a Microsoft Foundry resource in a
[region that supports Content Understanding](https://learn.microsoft.com/azure/ai-services/content-understanding/language-region-support),
and a chat-completion plus an embedding deployment on it.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then fill in your endpoint and deployment names
az login                  # or set CONTENTUNDERSTANDING_KEY in .env
```

Then write the model mapping onto the resource. This is a one-time step per resource —
Content Understanding borrows your Foundry deployments rather than hosting models, so it
needs to know which deployment serves which model name:

```bash
python create_setup.py
```

## Scripts

| Script | What it does | Bills tokens |
|---|---|---|
| `create_setup.py` | Writes the model-deployment mapping onto the resource | no |
| `show_defaults.py` | Prints the mapping currently saved on the resource | no |
| `show_analyzer.py` | Prints an analyzer definition; `--list` for all of them | no |
| `create_analyzer.py` | Creates a custom analyzer from a field schema | no |
| `analyze_document.py` | Runs an analyzer against a local file | **yes** |

## Running an analyzer

```bash
# a prebuilt analyzer — 88 are available on a fresh resource
python analyze_document.py samples/invoice_usd.pdf prebuilt-invoice

# a custom schema
python create_analyzer.py --recreate
python analyze_document.py samples/invoice_usd.pdf custom_invoice_extended

# the same schema against a spreadsheet
python analyze_document.py samples/invoice_spreadsheet.xlsx custom_invoice_extended

# full JSON result, including page markdown and bounding boxes
python analyze_document.py samples/invoice_eur.pdf custom_invoice_extended --json out.json
```

`--recreate` deletes the analyzer before creating it, which you need after editing the
schema — the service rejects creating an id that already exists.

## Samples

All synthetic, built to disagree with each other so the schema gets tested rather than
demonstrated.

| File | Tests |
|---|---|
| `invoice_usd.pdf` | Baseline: USD, Net 30, a shipping line, remittance details |
| `invoice_eur.pdf` | EUR with comma decimals, German vendor, **no** shipping line, Net 60 |
| `invoice_gbp_net14.pdf` | GBP, UK vendor, Net 14 — a term absent from the enum |
| `credit_memo.pdf` | Classification: a credit, not an invoice; no payment due |
| `receipt_paid.pdf` | Classification: already paid in full |
| `invoice_spreadsheet.xlsx` | Excel input, values cached |
| `invoice_spreadsheet_formulas.xlsx` | Excel input, formulas **without** cached values |

To regenerate them: `.venv/bin/pip install -r requirements-dev.txt`.

## Notes from building this

Things that cost time and aren't obvious from the docs:

- **An `analyzerId` cannot contain `-`.** Creation fails with `InvalidAnalyzerId`, even
  though every Microsoft prebuilt is named with hyphens. Use underscores.
- **Pick the generation method before polishing the description.** An `EXTRACT` field
  returns empty when the value isn't literally on the page, no matter how well described.
  A `Currency` field stayed blank until it became `GENERATE` — the invoice writes
  `$4,153.97` and never says "USD".
- **Check `supportedModels` on the analyzer.** `prebuilt-invoice` accepts no mini models
  for completion. Mapping the alias to one anyway raises no error and still returns
  results.
- **`update_defaults` merges, it doesn't replace.** Old entries survive until deleted.
- **Confidence is not comparable across analyzers or input formats.** On one file,
  `prebuilt-invoice` scored 0.31–0.43 while a custom schema scored 0.72–0.99, every value
  correct both times; re-rendering the document with proper typesetting changed nothing, so
  it's the analyzer, not the document. The prebuilt's *highest* scores were on fields that
  came back **empty**. Office formats report a flat `1` on every field, since there's no OCR
  step and therefore no recognition uncertainty — and no bounding boxes either.
- **Excel formulas are not evaluated.** The service reads stored cell values. Excel caches
  computed results when it saves, so real files are fine; script-generated ones often
  aren't.

## License

MIT
