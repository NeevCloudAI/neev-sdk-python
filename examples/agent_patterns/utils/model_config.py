"""Shared model configuration for the agent examples."""

from __future__ import annotations

import os

NEEV_MODEL = os.environ.get("NEEV_MODEL", "gpt-oss-120b")

NEEV_INFERENCE_BASE_URL = os.environ.get(
    "NEEV_INFERENCE_BASE_URL", "https://inference.ai.neevcloud.com/v1"
)


def neev_inference_api_key() -> str:
    key = os.environ.get("NEEV_INFERENCE_API_KEY")
    if not key:
        key = os.environ.get("NEEV_API_KEY")
    if not key:
        raise RuntimeError(
            "Missing model API key. Set NEEV_INFERENCE_API_KEY "
            "(or NEEV_API_KEY) for the inference endpoint."
        )
    return key
