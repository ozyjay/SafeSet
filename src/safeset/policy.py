"""Strict versioned policy parsing. No permissive schema defaults."""

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

from .classification import inferred_classification, safe_category
from .errors import SafetyError
from .ingestion import read_bounded

NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
CLASSES = {
    "direct_identifier",
    "pseudonymous_identifier",
    "quasi_identifier",
    "analytical_attribute",
    "free_text",
    "unknown",
}


class StrictLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise SafetyError("YAML aliases are not supported.")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise SafetyError("Policy keys must be unique strings.")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


@dataclass(frozen=True)
class ColumnRule:
    action: str
    classification: str
    allowed_values: tuple[str, ...] = ()
    bins: tuple[tuple[Decimal, Decimal], ...] = ()

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(
            f"[{lo}, {hi}{']' if i == len(self.bins) - 1 else ')'}"
            for i, (lo, hi) in enumerate(self.bins)
        )


@dataclass(frozen=True)
class Policy:
    columns: dict[str, ColumnRule]
    min_group_size: int

    @property
    def source_key(self) -> str:
        return next(k for k, v in self.columns.items() if v.action == "pseudonymise")

    @property
    def output_columns(self) -> tuple[str, ...]:
        return ("record_id", *(k for k, v in self.columns.items() if v.action in {"keep", "bin"}))


def parse_policy(raw: object) -> Policy:
    def require(condition: bool) -> None:
        if not condition:
            raise SafetyError(
                "Policy schema or safety constraints are invalid; see policy-format.md."
            )

    require(isinstance(raw, dict))
    require(set(raw) == {"version", "columns", "min_group_size"})
    require(type(raw["version"]) is int and raw["version"] == 1)
    require(type(raw["min_group_size"]) is int and 2 <= raw["min_group_size"] <= 50_000)
    require(isinstance(raw["columns"], dict) and 1 <= len(raw["columns"]) <= 128)
    columns = {}
    for name, config in raw["columns"].items():
        require(isinstance(name, str) and bool(NAME.fullmatch(name)) and name != "record_id")
        require(isinstance(config, dict))
        action = config.get("action")
        classification = config.get("classification")
        require(isinstance(action, str) and action in {"drop", "keep", "bin", "pseudonymise"})
        require(isinstance(classification, str) and classification in CLASSES)
        extra = {"allowed_values"} if action == "keep" else {"bins"} if action == "bin" else set()
        require(set(config) == {"action", "classification"} | extra)
        if action in {"keep", "bin"}:
            require(classification in {"quasi_identifier", "analytical_attribute"})
            require(inferred_classification(name) not in {"direct_identifier", "free_text"})
        if action == "pseudonymise":
            require(classification == "direct_identifier")
        allowed = ()
        bins = []
        if action == "keep":
            values = config["allowed_values"]
            require(isinstance(values, list) and 1 <= len(values) <= 1000)
            require(all(isinstance(v, str) and safe_category(v) for v in values))
            require(len(set(values)) == len(values))
            allowed = tuple(values)
        if action == "bin":
            pairs = config["bins"]
            require(isinstance(pairs, list) and 2 <= len(pairs) <= 100)
            for pair in pairs:
                require(isinstance(pair, list) and len(pair) == 2)
                require(all(type(n) in {int, float} for n in pair))
                lo, hi = (Decimal(str(n)) for n in pair)
                require(lo.is_finite() and hi.is_finite() and lo < hi)
                require(not bins or bins[-1][1] == lo)
                bins.append((lo, hi))
        columns[name] = ColumnRule(action, classification, allowed, tuple(bins))
        require(all(len(label) <= 64 for label in columns[name].labels))
    require(sum(r.action == "pseudonymise" for r in columns.values()) == 1)
    return Policy(columns, raw["min_group_size"])


def load_policy(path: Path) -> Policy:
    try:
        raw = yaml.load(read_bounded(path, 256 * 1024).decode("utf-8"), Loader=StrictLoader)
        return parse_policy(raw)
    except (yaml.YAMLError, UnicodeError, RecursionError, ValueError, TypeError):
        raise SafetyError("Policy could not be parsed safely; see policy-format.md.") from None
