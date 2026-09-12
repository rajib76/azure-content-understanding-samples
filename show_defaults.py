# coding=utf-8
"""
FILE: show_defaults.py

DESCRIPTION:
    Read-only companion to create_setup.py. Prints the model deployment mapping
    currently saved on your Microsoft Foundry resource. Writes nothing.

    The mapping lives server-side on the resource, not in any local file, so this is
    the authoritative view of what analyzers will actually use.

USAGE:
    python show_defaults.py

    Reads CONTENTUNDERSTANDING_ENDPOINT and, optionally, CONTENTUNDERSTANDING_KEY
    from the environment or .env. See create_setup.py for details.
"""

import os

from dotenv import load_dotenv
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential

load_dotenv()


def main() -> None:
    endpoint = os.environ["CONTENTUNDERSTANDING_ENDPOINT"]
    key = os.getenv("CONTENTUNDERSTANDING_KEY")
    credential = AzureKeyCredential(key) if key else DefaultAzureCredential()

    client = ContentUnderstandingClient(endpoint=endpoint, credential=credential)

    print(f"Resource: {endpoint}\n")
    defaults = client.get_defaults()
    mapping = defaults.model_deployments or {}

    if not mapping:
        print("No model deployments configured yet. Run create_setup.py first.")
        return

    # Prebuilt analyzers resolve through the aliases; the concrete model names are for
    # custom analyzers that name a model explicitly.
    aliases = {k: v for k, v in mapping.items() if k.startswith("prebuilt-analyzer-")}
    concrete = {k: v for k, v in mapping.items() if k not in aliases}
    width = max(len(k) for k in mapping)

    print("Aliases (used by prebuilt analyzers):")
    for name in sorted(aliases):
        print(f"  {name:{width}} -> {aliases[name]}")

    print("\nConcrete model names (used by custom analyzers):")
    for name in sorted(concrete):
        print(f"  {name:{width}} -> {concrete[name]}")


if __name__ == "__main__":
    main()
