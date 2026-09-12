# coding=utf-8
"""
FILE: databricks_extract.py

DESCRIPTION:
    Extract structured fields from a PDF, Excel workbook or CSV using the Databricks
    ai_extract REST API.

    The API takes text, not files, so this script does the reading locally and sends the
    result as the `content` field:

      .pdf   text layer via pypdf. A scanned PDF with no text layer will come back
             empty - ai_extract has no OCR of its own.
      .xlsx  cell values via openpyxl, rendered as a pipe-delimited table. Formulas are
             read as their cached value; a file written by a script rather than by Excel
             often has no cached value and reads as blank.
      .csv   passed through, with a row cap so a large file does not blow the limit.

    The schema is a JSON file mapping field names to definitions, so you describe what to
    pull out without touching this script. See schemas/invoice.json.

USAGE:
    export DATABRICKS_HOST="https://dbc-xxxxxxxx-xxxx.cloud.databricks.com"
    export DATABRICKS_TOKEN="<token>"

    python databricks_extract.py samples/invoice_usd.pdf schemas/invoice.json
    python databricks_extract.py samples/invoice_spreadsheet.xlsx schemas/invoice.json
    python databricks_extract.py samples/purchase_orders.csv schemas/purchase_orders.json

    --dry-run     print the request that would be sent, and exit without calling
    --citations   ask for the source span behind each value
    --json OUT    write the full response
    --show-text   print the extracted text instead of calling the API

    Host and token may also be set in .env. The API is rate limited to 120 requests per
    minute per workspace.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv()

ENDPOINT = "/api/2.0/ai-functions/ai-extract"
MAX_CHARS = 60_000
MAX_CSV_ROWS = 500


# --------------------------------------------------------------------------- readers

def read_pdf(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("pypdf is needed for PDFs:  pip install pypdf")
    reader = PdfReader(path)
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(f"--- page {number} ---\n{text}")
    if not pages:
        sys.exit(
            f"{path} has no extractable text layer. It is probably a scan; "
            "ai_extract does not OCR, so run it through an OCR step first."
        )
    return "\n\n".join(pages)


def read_xlsx(path: str) -> str:
    try:
        from openpyxl import load_workbook
    except ImportError:
        sys.exit("openpyxl is needed for .xlsx files:  pip install openpyxl")
    # data_only=True returns the cached result of a formula rather than the formula text.
    workbook = load_workbook(path, data_only=True)
    blocks = []
    for sheet in workbook.worksheets:
        lines = [f"--- sheet: {sheet.title} ---"]
        for row in sheet.iter_rows(values_only=True):
            cells = ["" if c is None else str(c) for c in row]
            if any(c.strip() for c in cells):
                lines.append(" | ".join(cells).rstrip(" |"))
        if len(lines) > 1:
            blocks.append("\n".join(lines))
    if not blocks:
        sys.exit(f"{path} has no readable cell values.")
    return "\n\n".join(blocks)


def read_csv(path: str) -> str:
    import csv

    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        sys.exit(f"{path} is empty.")
    truncated = len(rows) > MAX_CSV_ROWS + 1
    kept = rows[: MAX_CSV_ROWS + 1]
    text = "\n".join(" | ".join(cell.strip() for cell in row) for row in kept)
    if truncated:
        text += f"\n... {len(rows) - 1 - MAX_CSV_ROWS} further rows omitted"
    return text


READERS = {".pdf": read_pdf, ".xlsx": read_xlsx, ".xlsm": read_xlsx, ".csv": read_csv,
           ".txt": lambda p: open(p, encoding="utf-8").read(),
           ".md": lambda p: open(p, encoding="utf-8").read()}


def read_document(path: str) -> str:
    extension = os.path.splitext(path)[1].lower()
    reader = READERS.get(extension)
    if reader is None:
        sys.exit(f"Unsupported file type '{extension}'. "
                 f"Supported: {', '.join(sorted(READERS))}")
    text = reader(path)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n... truncated"
    return text


# ------------------------------------------------------------------------------- api

def call_ai_extract(host: str, token: str, content: str, schema: dict,
                    citations: bool) -> dict:
    payload = {
        "content": content,
        "schema": schema,
        "options": {"enable_confidence_scores": True,
                    "enable_citations": bool(citations)},
    }
    request = urllib.request.Request(
        host.rstrip("/") + ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")
        hint = ""
        if error.code == 401:
            hint = ("\nThe credential was rejected. Check DATABRICKS_TOKEN is a current "
                    "token for this workspace (Settings > Developer > Access tokens).")
        elif error.code == 404:
            hint = ("\nEndpoint not found. ai_extract needs serverless compute and is not "
                    "available on every workspace or region.")
        elif error.code == 429:
            hint = "\nRate limited: the API allows 120 requests per minute per workspace."
        sys.exit(f"HTTP {error.code} from ai-extract:\n{body}{hint}")
    except urllib.error.URLError as error:
        sys.exit(f"Could not reach {host}: {error.reason}")


# --------------------------------------------------------------------------- display

def render(result: dict) -> None:
    """
    ai_extract 2.1 returns:

      {"response": {"field": {"value": ..., "confidence_score": 0.95,
                              "citation_ids": [0, 1]}},
       "metadata": {"citations": [{"id": 0, "start": 0, "stop": 29},
                                  {"id": 1, "bbox": [...], "page_id": 0}]},
       "error_message": null}

    Confidence only appears when enable_confidence_scores was requested, and
    citation_ids index into metadata.citations rather than carrying the span inline.
    """
    print(result)
    if result.get("error_message"):
        print(f"error_message: {result['error_message']}")

    fields = result.get("response")
    if not isinstance(fields, dict):
        # Older versions return the fields at the top level.
        fields = {k: v for k, v in result.items()
                  if k not in ("metadata", "error_message")}
    metadata = result.get("metadata") or {}
    citations = {c.get("id"): c for c in (metadata.get("citations") or [])}
    if metadata.get("version"):
        print(f"ai_extract version {metadata['version']}")

    width = max((len(k) for k in fields), default=0)
    print(f"--- {len(fields)} fields ---")
    for name, raw in fields.items():
        if isinstance(raw, dict) and "value" in raw:
            value = raw["value"]
            score = raw.get("confidence_score")
            ids = raw.get("citation_ids") or []
        else:
            value, score, ids = raw, None, []

        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        suffix = f"  (conf {score:.2f})" if isinstance(score, (int, float)) else ""
        print(f"  {name:{width}}  {value}{suffix}")

        for cid in ids:
            c = citations.get(cid, {})
            if "start" in c:
                where = f"chars {c['start']}-{c.get('stop')}"
            elif "bbox" in c:
                where = f"page {c.get('page_id')} bbox {c['bbox']}"
            else:
                where = f"citation {cid}"
            print(f"  {'':{width}}  \u21b3 {where}")


# ------------------------------------------------------------------------------ main

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract structured fields from a PDF, Excel or CSV via Databricks ai_extract.")
    parser.add_argument("path", help="Document to read (.pdf, .xlsx, .csv, .txt, .md).")
    parser.add_argument("schema", nargs="?", default="schemas/invoice.json",
                        help="JSON file describing the fields. Default: schemas/invoice.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the request without sending it.")
    parser.add_argument("--show-text", action="store_true",
                        help="Print the text read from the file and exit.")
    parser.add_argument("--citations", action="store_true",
                        help="Ask for the source span behind each value.")
    parser.add_argument("--json", dest="json_out", metavar="OUT",
                        help="Write the full response here.")
    args = parser.parse_args()

    content = read_document(args.path)
    if args.show_text:
        print(content)
        return

    with open(args.schema, encoding="utf-8") as handle:
        schema = json.load(handle)

    print(f"{args.path}  ->  {len(content)} chars of text, "
          f"{len(schema)} fields from {args.schema}")

    if args.dry_run:
        print("\n--- request that would be POSTed ---")
        print(json.dumps({"content": content[:300] + ("..." if len(content) > 300 else ""),
                          "schema": schema,
                          "options": {"enable_confidence_scores": True,
                                      "enable_citations": args.citations}},
                         indent=2)[:2400])
        return

    host = os.getenv("DATABRICKS_HOST")
    token = os.getenv("DATABRICKS_TOKEN")
    if not host or not token:
        sys.exit("Set DATABRICKS_HOST and DATABRICKS_TOKEN (env or .env).\n"
                 '  export DATABRICKS_HOST="https://dbc-xxxxxxxx-xxxx.cloud.databricks.com"\n'
                 '  export DATABRICKS_TOKEN="<token>"')

    result = call_ai_extract(host, token, content, schema, args.citations)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, ensure_ascii=False)
        print(f"Full response written to {args.json_out}")
    print()
    render(result)


if __name__ == "__main__":
    main()
