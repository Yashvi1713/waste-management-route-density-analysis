from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_documents_aws_architecture():
    readme = (ROOT / "README.md").read_text()
    required = [
        "## Problem statement",
        "## AWS architecture",
        "AWS Glue 4.0",
        "Amazon Athena",
        "## Data model",
        "## Data quality",
        "## Streamlit dashboard",
        "docs/streamlit-dashboard.svg",
        "synthetic",
    ]
    assert all(item in readme for item in required)
    assert "## Local workflow" not in readme
    assert (ROOT / "docs/streamlit-dashboard.svg").is_file()
