"""Validate and activate the workstation LiteLLM provider inside OpenRAG.

Run this file inside the openrag-backend container. Check mode only reads the
LiteLLM API key from the container environment. Apply mode stores the provider
credential through OpenRAG's encrypted configuration and refuses to run without
OPENRAG_ENCRYPTION_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _request_json(
    base_url: str,
    api_key: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    data = None
    headers = {"Authorization": f"Bearer {api_key}"}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"LiteLLM request {path} failed with HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LiteLLM request {path} failed") from exc

    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"LiteLLM request {path} returned a non-object payload")
    return parsed


def _validate_remote(
    base_url: str,
    api_key: str,
    chat_model: str,
    embedding_model: str,
) -> None:
    models = _request_json(base_url, api_key, "/models")
    available = {
        str(item.get("id"))
        for item in models.get("data", [])
        if isinstance(item, dict) and item.get("id")
    }
    missing = [model for model in (chat_model, embedding_model) if model not in available]
    if missing:
        raise RuntimeError(
            "Workstation LiteLLM does not expose required model alias(es): "
            + ", ".join(missing)
        )

    embedding = _request_json(
        base_url,
        api_key,
        "/embeddings",
        payload={"model": embedding_model, "input": "openrag bootstrap probe"},
    )
    rows = embedding.get("data", [])
    if not rows or not isinstance(rows[0], dict) or not rows[0].get("embedding"):
        raise RuntimeError("Workstation LiteLLM embedding probe returned no vector")

    chat = _request_json(
        base_url,
        api_key,
        "/chat/completions",
        payload={
            "model": chat_model,
            "messages": [{"role": "user", "content": "Reply only OK"}],
            "max_tokens": 16,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "health_probe",
                        "description": "A no-op health probe",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            "tool_choice": "auto",
        },
    )
    if not chat.get("choices"):
        raise RuntimeError("Workstation LiteLLM chat probe returned no choices")


def _apply_openrag_config(chat_model: str, embedding_model: str) -> None:
    try:
        from config.config_manager import GenericProviderConfig
        from config.settings import config_manager
    except ImportError as exc:
        raise RuntimeError(
            "This OpenRAG image does not expose generic provider configuration; "
            "upgrade OpenRAG before applying the LiteLLM provider."
        ) from exc

    config = config_manager.get_config()
    provider = config.providers.custom.get("openai_like")
    if provider is None:
        provider = GenericProviderConfig()

    api_key = _required_env("LITELLM_IDE_API_KEY")
    api_base = os.getenv(
        "OPENRAG_LITELLM_API_BASE", "http://172.17.0.57:4000/v1"
    ).strip()
    if not os.getenv("OPENRAG_ENCRYPTION_KEY", "").strip():
        raise RuntimeError(
            "OPENRAG_ENCRYPTION_KEY is required before --apply so the "
            "LiteLLM credential is not persisted in plaintext"
        )

    config.providers.set_credentials(
        "openai_like",
        {"api_key": api_key, "api_base": api_base},
    )
    provider = config.providers.custom.get("openai_like", provider)
    provider.configured = True
    config.providers.custom["openai_like"] = provider
    config.agent.llm_provider = "openai_like"
    config.agent.llm_model = chat_model
    config.knowledge.embedding_provider = "openai_like"
    config.knowledge.embedding_model = embedding_model

    if not config_manager.save_config_file(config):
        raise RuntimeError("OpenRAG refused to persist the provider selection")
    config_manager.reload_config()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="persist openai_like as the selected OpenRAG chat and embedding provider",
    )
    args = parser.parse_args()

    base_url = os.getenv(
        "OPENRAG_LITELLM_API_BASE", "http://172.17.0.57:4000/v1"
    ).strip()
    api_key = _required_env("LITELLM_IDE_API_KEY")
    chat_model = os.getenv("OPENRAG_LITELLM_CHAT_MODEL", "qwen").strip()
    embedding_model = os.getenv(
        "OPENRAG_LITELLM_EMBEDDING_MODEL", "embedding"
    ).strip()

    _validate_remote(base_url, api_key, chat_model, embedding_model)
    print(
        "OK: workstation LiteLLM models, chat endpoint and embedding endpoint validated"
    )

    if args.apply:
        _apply_openrag_config(chat_model, embedding_model)
        print(
            "OK: OpenRAG provider selection persisted with encrypted LiteLLM credentials"
        )
    else:
        print("CHECK ONLY: rerun with --apply to persist the OpenRAG provider selection")

    return 0


if __name__ == "__main__":
    sys.exit(main())
