"""Coerce neutral JSON parameters into Albumentations constructor values."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import NoReturn

from albumentationsx_plugin.core import FieldKind, FormFieldSchema, InvalidParameterError, TransformConfig


def coerce_transform_params(transform: TransformConfig, schema: tuple[FormFieldSchema, ...]) -> dict[str, object]:
    """Return constructor parameters validated against a neutral parameter schema."""

    schema_by_name = {field.name: field for field in schema}
    unknown_parameters = sorted(set(transform.params) - set(schema_by_name))
    if unknown_parameters:
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name=unknown_parameters[0],
            message=f"{transform.name} received unsupported parameters.",
            context={
                "unknown_parameters": unknown_parameters,
                "allowed_parameters": sorted(schema_by_name),
            },
        )

    coerced_params: dict[str, object] = {}
    for field in schema:
        if field.name in transform.params:
            value = _coerce_field_value(transform, field, transform.params[field.name])
        elif field.default is not None:
            value = _coerce_field_value(transform, field, field.default)
        elif field.required:
            raise InvalidParameterError(
                transform_name=transform.name,
                parameter_name=field.name,
                message=f"{field.name} is required.",
                context={"reason_code": "missing_required_parameter"},
            )
        else:
            continue
        coerced_params[field.name] = value
    return coerced_params


def _coerce_field_value(transform: TransformConfig, field: FormFieldSchema, value: object) -> object:
    if _is_unsupported_required_schema(field):
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name=field.name,
            message=f"{field.name} cannot be represented safely yet.",
            context={"reason_code": "unsupported_required_parameter"},
        )

    match field.kind:
        case FieldKind.BOOLEAN:
            return _bool_value(transform, field, value)
        case FieldKind.INTEGER:
            return _bounded_number(transform, field, _int_value(transform, field, value))
        case FieldKind.FLOAT:
            return _bounded_number(transform, field, _float_value(transform, field, value))
        case FieldKind.STRING:
            return _str_value(transform, field, value)
        case FieldKind.ENUM:
            return _enum_value(transform, field, value)
        case FieldKind.NUMBER_RANGE:
            return _number_range_value(transform, field, value)
        case FieldKind.LIST:
            return _list_value(transform, field, value)
        case FieldKind.JSON:
            return _json_value(transform, field, value)
        case _:
            raise InvalidParameterError(
                transform_name=transform.name,
                parameter_name=field.name,
                message=f"{field.kind.value} parameters are not supported by the pipeline factory.",
                context={"reason_code": "unsupported_field_kind"},
            )


def _bool_value(transform: TransformConfig, field: FormFieldSchema, value: object) -> bool:
    if not isinstance(value, bool):
        _raise_type_error(transform, field, value, expected="boolean")
    return value


def _int_value(transform: TransformConfig, field: FormFieldSchema, value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        _raise_type_error(transform, field, value, expected="integer")
    return value


def _float_value(transform: TransformConfig, field: FormFieldSchema, value: object) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        _raise_type_error(transform, field, value, expected="number")
    return float(value)


def _str_value(transform: TransformConfig, field: FormFieldSchema, value: object) -> str:
    if not isinstance(value, str):
        _raise_type_error(transform, field, value, expected="string")
    if field.required and not value.strip():
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name=field.name,
            message=f"{field.name} cannot be empty.",
            context={"reason_code": "empty_required_parameter"},
        )
    return value


def _enum_value(transform: TransformConfig, field: FormFieldSchema, value: object) -> object:
    if value not in field.choices:
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name=field.name,
            message=f"{field.name} must be one of the supported choices.",
            context={
                "value": value,
                "choices": list(field.choices),
            },
        )
    return value


def _number_range_value(
    transform: TransformConfig, field: FormFieldSchema, value: object
) -> tuple[float, float] | tuple[int, int]:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name=field.name,
            message=f"{field.name} must be a two-value numeric range.",
            context={"value": value},
        )

    if _item_kind(field) == FieldKind.INTEGER:
        lower = _int_value(transform, field, value[0])
        upper = _int_value(transform, field, value[1])
    else:
        lower = _float_value(transform, field, value[0])
        upper = _float_value(transform, field, value[1])

    _validate_lower_upper(transform, field, lower=lower, upper=upper)
    return (lower, upper)


def _list_value(transform: TransformConfig, field: FormFieldSchema, value: object) -> list[object]:
    if not isinstance(value, list | tuple):
        _raise_type_error(transform, field, value, expected="list")

    expected_length = _list_length(field)
    if expected_length is not None and len(value) != expected_length:
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name=field.name,
            message=f"{field.name} must contain exactly {expected_length} items.",
            context={"value": list(value), "expected_length": expected_length},
        )

    item_kind = _item_kind(field)
    return [_coerce_list_item(transform, field, item, item_kind=item_kind) for item in value]


def _json_value(transform: TransformConfig, field: FormFieldSchema, value: object) -> object:
    if isinstance(value, str):
        if not value.strip() and not field.required:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError as error:
            raise InvalidParameterError(
                transform_name=transform.name,
                parameter_name=field.name,
                message=f"{field.name} must be valid JSON.",
                context={"value": value, "reason_code": "invalid_json_parameter"},
            ) from error
    return value


def _coerce_list_item(
    transform: TransformConfig,
    field: FormFieldSchema,
    value: object,
    *,
    item_kind: FieldKind | None,
) -> object:
    match item_kind:
        case FieldKind.BOOLEAN:
            return _bool_value(transform, field, value)
        case FieldKind.INTEGER:
            return _int_value(transform, field, value)
        case FieldKind.FLOAT:
            return _float_value(transform, field, value)
        case FieldKind.STRING:
            return _str_value(transform, field, value)
        case _:
            return value


def _bounded_number(transform: TransformConfig, field: FormFieldSchema, value: int | float) -> int | float:
    if field.min_value is not None and value < field.min_value:
        _raise_bound_error(transform, field, value, comparator="at least", bound=field.min_value)
    if field.max_value is not None and value > field.max_value:
        _raise_bound_error(transform, field, value, comparator="less than or equal to", bound=field.max_value)
    return value


def _validate_lower_upper(
    transform: TransformConfig,
    field: FormFieldSchema,
    *,
    lower: int | float,
    upper: int | float,
) -> None:
    _bounded_number(transform, field, lower)
    _bounded_number(transform, field, upper)
    if lower > upper:
        raise InvalidParameterError(
            transform_name=transform.name,
            parameter_name=field.name,
            message=f"{field.name} lower bound must be less than or equal to the upper bound.",
            context={"value": [lower, upper]},
        )


def _item_kind(field: FormFieldSchema) -> FieldKind | None:
    if not isinstance(field.item_schema, Mapping):
        return None
    kind = field.item_schema.get("kind")
    return FieldKind(kind) if isinstance(kind, str) else None


def _list_length(field: FormFieldSchema) -> int | None:
    if not isinstance(field.item_schema, Mapping):
        return None
    length = field.item_schema.get("length")
    return int(length) if isinstance(length, int | float) else None


def _is_unsupported_required_schema(field: FormFieldSchema) -> bool:
    return field.metadata.get("schema_status") == "unsupported_required"


def _raise_type_error(transform: TransformConfig, field: FormFieldSchema, value: object, *, expected: str) -> NoReturn:
    raise InvalidParameterError(
        transform_name=transform.name,
        parameter_name=field.name,
        message=f"{field.name} must be a {expected}.",
        context={"value": value, "expected": expected},
    )


def _raise_bound_error(
    transform: TransformConfig,
    field: FormFieldSchema,
    value: object,
    *,
    comparator: str,
    bound: float,
) -> NoReturn:
    raise InvalidParameterError(
        transform_name=transform.name,
        parameter_name=field.name,
        message=f"{field.name} must be {comparator} {bound}.",
        context={"value": value, "bound": bound},
    )
