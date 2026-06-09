"""Runtime validation helpers for control-plane API boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from neevai.errors import NeevAIError

T = TypeVar("T", bound=BaseModel)


class ResponseValidationError(NeevAIError):
    """Raised when an API response fails Pydantic validation."""

    def __init__(self, model: type[BaseModel], data: object, cause: PydanticValidationError):
        self.model = model
        self.data = data
        self.errors = cause.errors()
        super().__init__(f"Invalid {model.__name__} response: {cause}")


def coerce_model(model: type[T], data: object) -> T:
    """Validate ``data`` against a Pydantic model, mapping failures to :class:`ResponseValidationError`."""
    try:
        return model.model_validate(data)
    except PydanticValidationError as exc:
        raise ResponseValidationError(model, data, exc) from exc


def coerce_params(model: type[T], params: T | Mapping[str, Any]) -> T:
    """Accept a model instance or dict for backward-compatible ``create({...})`` calls."""
    if isinstance(params, model):
        return params
    if isinstance(params, Mapping):
        try:
            return model.model_validate(params)
        except PydanticValidationError as exc:
            raise ResponseValidationError(model, params, exc) from exc
    raise TypeError(f"Expected {model.__name__} or mapping, got {type(params).__name__}")
