"""Run repository-shape checks that do not require Azure credentials."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
NOTEBOOK_NAMES = [
    "part1-standard-foundry-iq-kb.ipynb",
    "part2-search-mcp-kb.ipynb",
    "part3-fabric-iq-to-kb.ipynb",
    "part4-work-iq-to-kb.ipynb",
    "part5-work-iq-fabric-iq-to-kb.ipynb",
]


def validate_notebooks() -> None:
    """Verify that every required notebook is valid, clean notebook JSON."""
    notebook_dir = ROOT / "notebooks"
    actual_names = sorted(path.name for path in notebook_dir.glob("*.ipynb"))
    assert actual_names == NOTEBOOK_NAMES, f"Unexpected notebook set: {actual_names}"

    for notebook_name in NOTEBOOK_NAMES:
        notebook = json.loads((notebook_dir / notebook_name).read_text(encoding="utf-8"))
        assert notebook["nbformat"] == 4
        for cell in notebook["cells"]:
            if cell["cell_type"] == "code":
                assert cell.get("execution_count") is None
                assert cell.get("outputs", []) == []


def validate_azure_yaml() -> None:
    """Verify the unified azd project contains only the retained services and hook."""
    config = yaml.safe_load((ROOT / "azure.yaml").read_text(encoding="utf-8"))
    assert set(config["services"]) == {"ai-project", "hr-agent"}
    assert config["services"]["ai-project"]["host"] == "azure.ai.project"

    agent = config["services"]["hr-agent"]
    assert agent["host"] == "azure.ai.agent"
    assert agent["project"] == "src/hr-agent"
    assert agent["kind"] == "hosted"
    assert agent["codeConfiguration"]["dependencyResolution"] == "remote_build"
    assert set(config["hooks"]) == {"postprovision"}


def main() -> None:
    """Run all checks."""
    validate_notebooks()
    validate_azure_yaml()
    print("Repository shape is valid.")


if __name__ == "__main__":
    main()
