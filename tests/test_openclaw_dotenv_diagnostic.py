"""Dotenv syntax diagnostics must remain secret-free."""
from pathlib import Path
import importlib.util

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/openclaw-dotenv-diagnostic.py"
spec = importlib.util.spec_from_file_location("openclaw_dotenv_diagnostic", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_unexpanded_reference_and_trailing_quote() -> None:
    assert module.classify("${NABLA_PLUS_OPENAI_API_KEY}") == "unexpanded_reference"
    assert module.classify("sk-proj-example-value\"") == "trailing_quote"
    assert module.classify("\"sk-proj-example-value\"") == "configured_key_shaped"
    assert module.classify("\"sk-proj-example-value") == "unbalanced_quotes"


def test_no_secrets_exposed_by_classifier() -> None:
    for raw in ("sk-proj-confidential123", "free-form-sensitive-value"):
        output = module.classify(raw)
        assert raw not in output
        assert output in ("configured_key_shaped", "configured_unverified")
