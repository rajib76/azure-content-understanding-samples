# coding=utf-8
"""
FILE: create_analyzer.py

DESCRIPTION:
    Creates a custom analyzer that extends the invoice extraction we got from
    prebuilt-invoice, and demonstrates all three field generation methods.

    The schema targets three things prebuilt-invoice missed on sample_invoice.pdf:

    - ShippingAmount      - prebuilt-invoice has no header field for it
    - RemittanceAccount   - the remit-to account number
    - RemittanceRouting   - the remit-to routing number

    Generation methods:

    - EXTRACT  - copy a value that is literally present in the document. These are the
                 fields worth setting estimate_source_and_confidence on, since a literal
                 value has a location on the page to point at.
    - GENERATE - have the model write something that is not in the document, such as a
                 summary. There is no source span to cite, so no confidence estimate.
    - CLASSIFY - choose one of an explicit enum. Use enum_descriptions to disambiguate
                 categories whose names alone are ambiguous.

    A custom analyzer names its models directly rather than through the prebuilt-analyzer-*
    aliases, so "gpt-5.4" below resolves through the concrete entries that create_setup.py
    wrote. Run show_defaults.py if you are unsure what is mapped.

    Custom analyzers cost nothing to keep on the resource; you are billed per analyze call.

USAGE:
    python create_analyzer.py [--analyzer-id ID] [--recreate]

    Then analyze a document with it using the existing script:
      python analyze_document.py sample_invoice.pdf custom_invoice_extended
"""

import argparse
import os

from dotenv import load_dotenv
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.ai.contentunderstanding.models import (
    ContentAnalyzer,
    ContentAnalyzerConfig,
    ContentFieldDefinition,
    ContentFieldSchema,
    ContentFieldType,
    GenerationMethod,
)
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential

load_dotenv()

# The service rejects "-" in an analyzerId, so use underscores.
DEFAULT_ANALYZER_ID = "custom_invoice_extended"


def extract(field_type, description: str) -> ContentFieldDefinition:
    """A value copied verbatim from the document, with its page location tracked."""
    return ContentFieldDefinition(
        type=field_type,
        method=GenerationMethod.EXTRACT,
        description=description,
        estimate_source_and_confidence=True,
    )


def build_field_schema() -> ContentFieldSchema:
    line_item = ContentFieldDefinition(
        type=ContentFieldType.OBJECT,
        properties={
            "ProductCode": extract(ContentFieldType.STRING, "Item or SKU code."),
            "Description": extract(ContentFieldType.STRING, "Item description."),
            "Quantity": extract(ContentFieldType.INTEGER, "Units ordered."),
            "UnitPrice": extract(ContentFieldType.NUMBER, "Price per unit, digits only."),
            "Amount": extract(ContentFieldType.NUMBER, "Line total, digits only."),
        },
    )

    return ContentFieldSchema(
        name="ExtendedInvoice",
        description="Invoice fields including shipping and remittance details.",
        fields={
            # --- EXTRACT: literally present on the page ---
            "InvoiceId": extract(ContentFieldType.STRING, "The invoice number."),
            "InvoiceDate": extract(ContentFieldType.DATE, "Date the invoice was issued."),
            "DueDate": extract(ContentFieldType.DATE, "Date payment is due."),
            "PurchaseOrder": extract(ContentFieldType.STRING, "Customer purchase order number."),
            "VendorName": extract(ContentFieldType.STRING, "Name of the company issuing the invoice."),
            "CustomerName": extract(ContentFieldType.STRING, "Name of the company being billed."),
            "SubtotalAmount": extract(ContentFieldType.NUMBER, "Subtotal before shipping and tax."),
            "ShippingAmount": extract(
                ContentFieldType.NUMBER,
                "Shipping, freight or delivery charge. Digits only, no currency symbol. "
                "Leave empty if the invoice has no shipping line.",
            ),
            "TaxAmount": extract(ContentFieldType.NUMBER, "Total sales tax charged."),
            "TotalAmount": extract(ContentFieldType.NUMBER, "Final amount due."),
            # GENERATE, not EXTRACT: an invoice that writes "$4,153.97" never spells out
            # "USD", so there is no literal token to copy. The code has to be inferred.
            "Currency": ContentFieldDefinition(
                type=ContentFieldType.STRING,
                method=GenerationMethod.GENERATE,
                description=(
                    "The ISO 4217 currency code for the amounts on this invoice, such as "
                    "USD, EUR or GBP. Infer it from the currency symbol, any currency code "
                    "printed on the document, and the vendor's country. A '$' on an invoice "
                    "from a US address means USD."
                ),
            ),
            "RemittanceAccount": extract(
                ContentFieldType.STRING,
                "Bank account number given in the remit-to or payment instructions.",
            ),
            "RemittanceRouting": extract(
                ContentFieldType.STRING,
                "Bank routing or ABA number given in the remit-to or payment instructions.",
            ),
            "LineItems": ContentFieldDefinition(
                type=ContentFieldType.ARRAY,
                method=GenerationMethod.EXTRACT,
                description="One entry per billed line item.",
                item_definition=line_item,
            ),
            # --- GENERATE: written by the model, not present in the document ---
            "Summary": ContentFieldDefinition(
                type=ContentFieldType.STRING,
                method=GenerationMethod.GENERATE,
                description=(
                    "One sentence stating who is billing whom, for what kind of goods, "
                    "and the total due."
                ),
            ),
            # --- CLASSIFY: pick exactly one of the listed categories ---
            "DocumentType": ContentFieldDefinition(
                type=ContentFieldType.STRING,
                method=GenerationMethod.CLASSIFY,
                description="What kind of commercial document this is.",
                enum=["invoice", "creditMemo", "purchaseOrder", "receipt", "statement", "other"],
                enum_descriptions={
                    "invoice": "A request for payment for goods or services already supplied.",
                    "creditMemo": "A refund or credit issued against a previous invoice.",
                    "purchaseOrder": "A buyer's order placed before goods are supplied.",
                    "receipt": "Proof that payment has already been made.",
                    "statement": "A periodic summary of multiple transactions.",
                },
            ),
            "PaymentTerms": ContentFieldDefinition(
                type=ContentFieldType.STRING,
                method=GenerationMethod.CLASSIFY,
                description="The payment window stated on the invoice.",
                enum=["dueOnReceipt", "net15", "net30", "net45", "net60", "other", "notStated"],
            ),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a custom Content Understanding analyzer.")
    parser.add_argument("--analyzer-id", default=DEFAULT_ANALYZER_ID)
    parser.add_argument("--recreate", action="store_true",
                        help="Delete the analyzer first if it already exists.")
    args = parser.parse_args()

    endpoint = os.environ["CONTENTUNDERSTANDING_ENDPOINT"]
    key = os.getenv("CONTENTUNDERSTANDING_KEY")
    credential = AzureKeyCredential(key) if key else DefaultAzureCredential()

    client = ContentUnderstandingClient(endpoint=endpoint, credential=credential)

    if args.recreate:
        try:
            client.delete_analyzer(args.analyzer_id)
            print(f"Deleted existing analyzer {args.analyzer_id}.")
        except ResourceNotFoundError:
            pass

    # [START create_analyzer]
    analyzer = ContentAnalyzer(
        base_analyzer_id="prebuilt-document",
        description="Invoice extraction including shipping and remittance details.",
        config=ContentAnalyzerConfig(
            enable_ocr=True,
            enable_layout=True,
            return_details=True,
            estimate_field_source_and_confidence=True,
        ),
        field_schema=build_field_schema(),
        # Concrete model names, resolved by the resource defaults. A prebuilt analyzer
        # would use the prebuilt-analyzer-* aliases here instead.
        models={
            "completion": "gpt-5.4",
            "embedding": "text-embedding-3-large",
        },
    )

    print(f"Creating analyzer {args.analyzer_id}...")
    try:
        poller = client.begin_create_analyzer(analyzer_id=args.analyzer_id, resource=analyzer)
        poller.result()
    except ResourceExistsError:
        print(f"Analyzer {args.analyzer_id} already exists. Pass --recreate to replace it.")
    # [END create_analyzer]

    created = client.get_analyzer(args.analyzer_id)
    definition = created.as_dict() if hasattr(created, "as_dict") else dict(created)
    fields = (definition.get("fieldSchema") or {}).get("fields") or {}

    print(f"\nstatus  : {definition.get('status')}")
    print(f"base    : {definition.get('baseAnalyzerId')}")
    print(f"models  : {definition.get('models')}")
    for warning in definition.get("warnings") or []:
        print(f"warning : {warning}")

    print(f"\nfieldSchema ({len(fields)} fields):")
    for name, spec in fields.items():
        method = spec.get("method") or "extract"
        enum = spec.get("enum")
        suffix = f"  enum={enum}" if enum else ""
        print(f"  {name:20} {method:9} {spec.get('type')}{suffix}")

    print(f"\nRun it with:\n  python analyze_document.py sample_invoice.pdf {args.analyzer_id}")


if __name__ == "__main__":
    main()
