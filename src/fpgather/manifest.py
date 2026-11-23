"""Strict loading of syntax version 1; no expression execution."""

import math
import re
from pathlib import Path

import yaml

from .model import SourcesError


class UniqueLoader(yaml.SafeLoader):
    """Load YAML mappings with unique string keys."""

    def construct_mapping(self, node, deep=False):
        """Construct a mapping with unique string keys."""
        self.flatten_mapping(node)
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise SourcesError("YAML mapping keys must be strings")
            if key in result:
                raise SourcesError(f"Duplicate YAML key: {key}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def is_scalar(value: object) -> bool:
    """Return whether a value is an allowed scalar definition."""
    return type(value) in (bool, str, int) or (
        type(value) is float and math.isfinite(value)
    )


def normalize_library_name(value: str) -> str:
    """Validate a library identifier and normalize it to lowercase."""
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*", value
    ):
        raise SourcesError(f"Invalid library name: {value!r}")
    return value.lower()


def require_mapping(value, label):
    """Require a mapping and label any validation error."""
    if not isinstance(value, dict):
        raise SourcesError(f"{label} must be a mapping")
    return value


def validate_condition(condition):
    """Validate a definition name or scalar comparison mapping."""
    if isinstance(condition, str) and condition:
        return
    if (
        isinstance(condition, dict)
        and condition
        and all(
            isinstance(name, str) and name and is_scalar(expected)
            for name, expected in condition.items()
        )
    ):
        return
    raise SourcesError(
        "if must be a definition name or a nonempty scalar comparison mapping"
    )


def condition_matches(condition, defines):
    """Evaluate a condition without coercing scalar types."""
    if isinstance(condition, str):
        return defines.get(condition) is True
    for name, expected in condition.items():
        if name not in defines:
            return False
        actual = defines[name]
        # Keep booleans distinct: Python otherwise treats True == 1.
        if (
            isinstance(actual, bool) != isinstance(expected, bool)
            or actual != expected
        ):
            return False
    return True


def parse_entries(value, label, *, is_source):
    """Validate entries and return their path/option pairs."""
    if not isinstance(value, list):
        raise SourcesError(f"{label} must be a list")
    result = []
    for entry in value:
        if isinstance(entry, str):
            path, options = entry, {}
        elif isinstance(entry, dict) and len(entry) == 1:
            path, options = next(iter(entry.items()))
            require_mapping(options, f"Options for {path}")
        else:
            raise SourcesError(f"Invalid entry in {label}: {entry!r}")
        if not isinstance(path, str) or not path or Path(path).is_absolute():
            raise SourcesError(
                f"{label} paths must be nonempty relative paths: {path!r}"
            )
        allowed_options = {"if", "language_version"} if is_source else {"if"}
        unknown_options = options.keys() - allowed_options
        if unknown_options:
            raise SourcesError(
                f"Unknown options for {path}: {sorted(unknown_options)}"
            )
        if "if" in options:
            validate_condition(options["if"])
        if "language_version" in options and (
            not isinstance(options["language_version"], str)
            or not options["language_version"]
        ):
            raise SourcesError(
                f"language_version for {path} must be a nonempty string"
            )
        result.append((path, options))
    return result


def load_manifest(path: Path):
    """Load a manifest and add its path to validation errors."""
    try:
        data = require_mapping(
            yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader),
            "Manifest",
        )
        allowed = {
            "syntax_version",
            "language_defaults",
            "defines",
            "sources",
            "dependencies",
        }
        if data.keys() - allowed:
            raise SourcesError(
                f"Unknown fields: {sorted(data.keys() - allowed)}"
            )
        syntax_version = data.get("syntax_version", 1)
        if type(syntax_version) is not int or syntax_version != 1:
            raise SourcesError(
                "Unsupported syntax_version; expected integer 1"
            )
        defines = require_mapping(data.get("defines", {}), "defines")
        if not all(
            isinstance(name, str) and name and is_scalar(value)
            for name, value in defines.items()
        ):
            raise SourcesError(
                "defines must contain named booleans, strings "
                "or finite numbers"
            )
        defaults = require_mapping(
            data.get("language_defaults", {}), "language_defaults"
        )
        normalized_defaults = {}
        for suffix, version in defaults.items():
            if (
                not re.fullmatch(r"\.[A-Za-z0-9]+", suffix)
                or not isinstance(version, str)
                or not version
            ):
                raise SourcesError(
                    "language_defaults requires suffix keys "
                    "and nonempty string versions"
                )
            if suffix.lower() in normalized_defaults:
                raise SourcesError(f"Duplicate suffix: {suffix}")
            normalized_defaults[suffix.lower()] = version
        sources = parse_entries(
            data.get("sources", []), "sources", is_source=True
        )
        dependencies = []
        dependency_mapping = require_mapping(
            data.get("dependencies", {}), "dependencies"
        )
        for library, dependency_entries in dependency_mapping.items():
            normalized_library = normalize_library_name(library)
            dependencies.extend(
                (normalized_library, path, options)
                for path, options in parse_entries(
                    dependency_entries, "dependencies", is_source=False
                )
            )
        return {
            "defines": defines,
            "language_defaults": normalized_defaults,
            "sources": sources,
            "dependencies": dependencies,
        }
    except (
        OSError,
        UnicodeError,
        yaml.YAMLError,
        SourcesError,
        RecursionError,
    ) as exc:
        raise SourcesError(f"{path}: {exc}") from exc
