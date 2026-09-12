# coding=utf-8
"""
FILE: analyze_document.py

DESCRIPTION:
    This sample demonstrates how to run a prebuilt (or custom) analyzer against a local
    file and print the extracted fields.

    Prebuilt analyzers resolve their models through the defaults configured by
    create_setup.py, so run that once per Microsoft Foundry resource first. Use
    client.list_analyzers() to see every analyzer available on your resource.

    Money fields come back as objects holding an Amount and a CurrencyCode rather than
    as plain numbers, and repeating sections (invoice line items, for example) come back
    as arrays of objects. The render() helper below unwraps both.

USAGE:
    python analyze_document.py <path> [analyzer-id] [--json OUT]

    Examples:
      python analyze_document.py invoice.pdf
      python analyze_document.py receipt.png prebuilt-receipt
      python analyze_document.py statement.pdf prebuilt-bankStatement.us --json out.json

    Set the environment variables with your own values before running the sample
    (see create_setup.py for the full list):
     1) CONTENTUNDERSTANDING_ENDPOINT (required) - the endpoint to your Content
        Understanding resource.
     2) CONTENTUNDERSTANDING_KEY (optional) - your Content Understanding API key. When
        unset, DefaultAzureCredential is used.
"""

import argparse
import json
import os

from dotenv import load_dotenv
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential

load_dotenv()

# Analyzers accept documents, images, audio and video. Anything unrecognized is sent as
# opaque bytes and sniffed by the service.
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".heif": "image/heif",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".html": "text/html",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
}

CURRENCY_KEYS = {"Amount", "CurrencyCode"}

SCALARS = (
    "valueString",
    "valueNumber",
    "valueDate",
    "valueInteger",
    "valueBoolean",
    "valueTime",
)


def render(value):
    """Flatten one field value into a scalar, list or dict."""
    if value is None:
        return None
    for key in SCALARS:
        if key in value:
            return value[key]
    if value.get("type") == "object":
        obj = value.get("valueObject") or {}
        if obj and set(obj) <= CURRENCY_KEYS:
            # A currency object, not a section that merely happens to carry an Amount.
            amount = render(obj["Amount"]) if "Amount" in obj else None
            if amount is None:
                return None
            currency = render(obj.get("CurrencyCode")) or ""
            return f"{amount} {currency}".strip()
        return {name: render(item) for name, item in obj.items()}
    if value.get("type") == "array":
        return [render(item) for item in (value.get("valueArray") or [])]
    return None


def confidence(value):
    """Confidence sits on the leaf, so reach into currency objects for it."""
    if not isinstance(value, dict):
        return None
    if "confidence" in value:
        return value["confidence"]
    obj = value.get("valueObject") or {}
    if obj and set(obj) <= CURRENCY_KEYS:
        return (obj.get("Amount") or {}).get("confidence")
    return None


def print_fields(fields: dict) -> None:
    scalars, tables = {}, {}
    for name, value in sorted(fields.items()):
        rendered = render(value)
        if isinstance(rendered, list) and rendered and isinstance(rendered[0], dict):
            tables[name] = rendered
        elif isinstance(rendered, dict):
            tables[name] = [rendered]
        elif rendered not in (None, {}, []):
            scalars[name] = (rendered, confidence(value))

    if scalars:
        print(f"--- {len(scalars)} fields ---")
        width = max(len(n) for n in scalars)
        for name, (rendered, conf) in scalars.items():
            # Office formats report an integer confidence of 1 (no OCR, so no
            # recognition uncertainty); accept int as well as float.
            suffix = f"  (conf {conf:.2f})" if isinstance(conf, (int, float)) and not isinstance(conf, bool) else ""
            print(f"  {name:{width}} {rendered}{suffix}")

    for name, rows in tables.items():
        print(f"\n--- {name} ({len(rows)} rows) ---")
        columns = [c for c in dict.fromkeys(k for r in rows for k in r) if any(r.get(c) is not None for r in rows)]
        print("  " + "  ".join(f"{c[:18]:18}" for c in columns))
        for row in rows:
            print("  " + "  ".join(f"{str(row.get(c) or '')[:18]:18}" for c in columns))


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a local file with a Content Understanding analyzer.")
    parser.add_argument("path", help="File to analyze.")
    parser.add_argument("analyzer_id", nargs="?", default="prebuilt-invoice",
                        help="Analyzer to run. Defaults to prebuilt-invoice.")
    parser.add_argument("--json", dest="json_out", metavar="OUT",
                        help="Also write the full analysis result to this file.")
    args = parser.parse_args()

    endpoint = os.environ["CONTENTUNDERSTANDING_ENDPOINT"]
    key = os.getenv("CONTENTUNDERSTANDING_KEY")
    credential = AzureKeyCredential(key) if key else DefaultAzureCredential()

    client = ContentUnderstandingClient(endpoint=endpoint, credential=credential)

    with open(args.path, "rb") as handle:
        data = handle.read()

    extension = os.path.splitext(args.path)[1].lower()
    content_type = CONTENT_TYPES.get(extension, "application/octet-stream")

    # [START analyze_binary]
    print(f"Analyzing {args.path} ({len(data)} bytes, {content_type}) with {args.analyzer_id}...")
    poller = client.begin_analyze_binary(args.analyzer_id, data, content_type=content_type)
    print(f"Operation id: {poller.operation_id}")
    result = poller.result()
    # [END analyze_binary]

    payload = result.as_dict() if hasattr(result, "as_dict") else dict(result)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str)
        print(f"Full result written to {args.json_out}")

    for content in payload.get("contents", []):
        print()
        print_fields(content.get("fields") or {})
        markdown = content.get("markdown") or ""
        if markdown:
            print(f"\n--- markdown content: {len(markdown)} chars ---")


if __name__ == "__main__":
    main()
