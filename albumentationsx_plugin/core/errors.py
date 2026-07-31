"""Structured plugin errors that can be shown in host UIs and saved in manifests."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from albumentationsx_plugin.core.serialization import JSONDict, JSONValue, normalize_json_mapping


class ErrorCode(StrEnum):
    """Stable reason codes for user-facing plugin failures."""

    UNSUPPORTED_TRANSFORM = "unsupported_transform"
    INVALID_PARAMETER = "invalid_parameter"
    IO_ERROR = "io_error"
    HOST_ADAPTER_ERROR = "host_adapter_error"


class PluginError(Exception):
    """Base error with a user-facing message and JSON-serializable context."""

    code: ErrorCode
    message: str
    context: Mapping[str, JSONValue]

    def __init__(
        self,
        code: ErrorCode | str,
        message: str,
        context: Mapping[str, object] | None = None,
    ) -> None:
        if not message.strip():
            raise ValueError("message must be a non-empty string")

        self.code = ErrorCode(code)
        self.message = message
        self.context = normalize_json_mapping(context)
        super().__init__(message)

    @property
    def reason_code(self) -> str:
        return self.code.value

    def to_dict(self) -> JSONDict:
        return {
            "code": self.code.value,
            "message": self.message,
            "context": normalize_json_mapping(self.context),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> PluginError:
        code = value.get("code")
        message = value.get("message")
        if not isinstance(code, str):
            raise TypeError("code must be a string")
        if not isinstance(message, str):
            raise TypeError("message must be a string")
        context = value.get("context", {})
        if not isinstance(context, Mapping):
            raise TypeError("context must be a JSON object")
        return cls(code=ErrorCode(code), message=message, context=context)


class UnsupportedTransformError(PluginError):
    """Raised when a transform is unavailable or intentionally excluded."""

    def __init__(
        self,
        transform_name: str,
        message: str | None = None,
        context: Mapping[str, object] | None = None,
    ) -> None:
        merged_context = {"transform_name": transform_name, **dict(context or {})}
        super().__init__(
            ErrorCode.UNSUPPORTED_TRANSFORM,
            message or f"Transform {transform_name} is not supported by this plugin configuration.",
            merged_context,
        )


class InvalidParameterError(PluginError):
    """Raised when a transform parameter cannot be accepted."""

    def __init__(
        self,
        transform_name: str,
        parameter_name: str,
        message: str,
        context: Mapping[str, object] | None = None,
    ) -> None:
        merged_context = {
            "transform_name": transform_name,
            "parameter_name": parameter_name,
            **dict(context or {}),
        }
        super().__init__(ErrorCode.INVALID_PARAMETER, message, merged_context)


class MediaIOError(PluginError):
    """Raised when media cannot be read or written."""

    def __init__(
        self,
        filepath: str,
        message: str,
        context: Mapping[str, object] | None = None,
    ) -> None:
        merged_context = {"filepath": filepath, **dict(context or {})}
        super().__init__(ErrorCode.IO_ERROR, message, merged_context)


class HostAdapterError(PluginError):
    """Raised when a host adapter cannot translate host state into core data."""

    def __init__(
        self,
        host: str,
        message: str,
        context: Mapping[str, object] | None = None,
    ) -> None:
        merged_context = {"host": host, **dict(context or {})}
        super().__init__(ErrorCode.HOST_ADAPTER_ERROR, message, merged_context)
