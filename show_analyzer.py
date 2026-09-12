# coding=utf-8
"""
FILE: show_analyzer.py

DESCRIPTION:
    Prints an analyzer's definition. Read-only; writes nothing and bills no tokens.

    The useful parts of a prebuilt analyzer's definition are:

    - models          - which model each internal role asks for. Prebuilt analyzers name
                        an alias here (prebuilt-analyzer-completion), which your resource
                        defaults then resolve to a deployment. See show_defaults.py.
    - supportedModels - which concrete models are valid for each role. Worth checking
                        against your defaults: the service does not reject a mapping to
                        an unsupported model, it just uses it.
    - fieldSchema     - the fields the analyzer extracts.

USAGE:
    python show_analyzer.py [analyzer-id] [--json OUT] [--fields]

    Examples:
      python show_analyzer.py prebuilt-invoice
      python show_analyzer.py prebuilt-documentSearch
      python show_analyzer.py prebuilt-receipt --fields
      python show_analyzer.py prebuilt-invoice --json analyzer.json
      python show_analyzer.py --list
"""

import argparse
import json
import os

from dotenv import load_dotenv
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description="Show a Content Understanding analyzer definition.")
    parser.add_argument("analyzer_id", nargs="?", default="prebuilt-invoice")
    parser.add_argument("--list", action="store_true", help="List every analyzer id instead.")
    parser.add_argument("--fields", action="store_true", help="Also print the field schema.")
    parser.add_argument("--json", dest="json_out", metavar="OUT", help="Write the full definition here.")
    args = parser.parse_args()

    endpoint = os.environ["CONTENTUNDERSTANDING_ENDPOINT"]
    key = os.getenv("CONTENTUNDERSTANDING_KEY")
    credential = AzureKeyCredential(key) if key else DefaultAzureCredential()

    client = ContentUnderstandingClient(endpoint=endpoint, credential=credential)

    if args.list:
        ids = sorted(a.analyzer_id for a in client.list_analyzers())
        print(f"{len(ids)} analyzers on {endpoint}:")
        for analyzer_id in ids:
            print(f"  {analyzer_id}")
        return

    analyzer = client.get_analyzer(args.analyzer_id)
    definition = analyzer.as_dict() if hasattr(analyzer, "as_dict") else dict(analyzer)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(definition, handle, indent=2, default=str)
        print(f"Full definition written to {args.json_out}\n")

    print(f"analyzerId     : {definition.get('analyzerId')}")
    print(f"baseAnalyzerId : {definition.get('baseAnalyzerId')}")
    print(f"description    : {definition.get('description')}")

    print("\nmodels (what this analyzer asks for):")
    for role, model_name in (definition.get("models") or {}).items():
        print(f"  {role:12} -> {model_name}")

    print("\nsupportedModels (what is valid for each role):")
    for role, models in (definition.get("supportedModels") or {}).items():
        print(f"  {role:12} : {', '.join(models) if isinstance(models, list) else models}")

    if args.fields:
        schema = (definition.get("fieldSchema") or {}).get("fields") or {}
        print(f"\nfieldSchema ({len(schema)} fields):")
        for name, spec in sorted(schema.items()):
            print(f"  {name:28} {spec.get('type')}")


if __name__ == "__main__":
    main()
