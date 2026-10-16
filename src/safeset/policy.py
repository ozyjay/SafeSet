"""Strict versioned policy parsing. No permissive schema defaults."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

from .classification import inferred_classification, safe_category
from .errors import SafetyError
from .ingestion import read_bounded, valid_heading
from .text_review import validate_text_reviews

CLASSES = {
    "direct_identifier",
    "pseudonymous_identifier",
    "quasi_identifier",
    "analytical_attribute",
    "free_text",
    "unknown",
}


class PolicyConfigurationError(SafetyError):
    """Local authoring context, never part of exception text or diagnostic logs."""

    def __init__(self, reason: str, field: str | None = None) -> None:
        super().__init__("Policy schema or safety constraints are invalid; see policy-format.md.")
        self.fields = {field: [reason]} if field is not None else {}
        self.issues = [] if field is not None else [reason]
        self.sheet: str | None = None


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
    bounds: tuple[Decimal, Decimal] | None = None
    max_decimal_places: int | None = None
    text_reviews: tuple[tuple[str, str], ...] = ()

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
    version: int

    @property
    def source_key(self) -> str:
        return next(k for k, v in self.columns.items() if v.action == "pseudonymise")

    @property
    def output_columns(self) -> tuple[str, ...]:
        return (
            "record_id",
            *(
                k
                for k, v in self.columns.items()
                if v.action in {"keep", "bin", "code", "keep_numeric", "review_text"}
            ),
        )


def parse_policy(raw: object) -> Policy:
    current_field = None

    def require(condition: bool, reason: str = "schema") -> None:
        if not condition:
            raise PolicyConfigurationError(reason, current_field)

    require(isinstance(raw, dict))
    require(set(raw) == {"version", "columns", "min_group_size"})
    require(type(raw["version"]) is int and raw["version"] in {1, 2, 3, 4, 5})
    version = raw["version"]
    require(
        type(raw["min_group_size"]) is int and 2 <= raw["min_group_size"] <= 50_000, "group_size"
    )
    require(isinstance(raw["columns"], dict) and 1 <= len(raw["columns"]) <= 128)
    columns = {}
    for name, config in raw["columns"].items():
        current_field = name if isinstance(name, str) else None
        require(valid_heading(name) and name != "record_id", "heading")
        require(isinstance(config, dict))
        action = config.get("action")
        classification = config.get("classification")
        actions = {"drop", "keep", "bin", "pseudonymise"}
        if version in {2, 3, 4, 5}:
            actions |= {"code", "keep_numeric"}
        if version in {4, 5}:
            actions.add("review_text")
        require(isinstance(action, str) and action in actions, "action")
        require(isinstance(classification, str) and classification in CLASSES, "classification")
        if action in {"keep", "code"}:
            extra = {"allowed_values"}
        elif action == "bin":
            extra = {"bins"}
        elif action == "keep_numeric":
            extra = {"bounds", "max_decimal_places"} if version == 2 else {"bounds"}
        elif action == "review_text":
            extra = {"text_reviews"}
        else:
            extra = set()
        require(set(config) == {"action", "classification"} | extra)
        coded_identifier = (
            version == 5 and action == "code" and classification == "direct_identifier"
        )
        if action in {"keep", "bin", "code", "keep_numeric"}:
            require(
                coded_identifier or classification in {"quasi_identifier", "analytical_attribute"},
                "classification",
            )
            require(
                inferred_classification(name) != "direct_identifier" or coded_identifier,
                "identifier_retention",
            )
            require(
                inferred_classification(name) != "free_text" or coded_identifier, "narrative_action"
            )
        if action == "pseudonymise":
            require(classification == "direct_identifier", "source_key_classification")
        text_reviews = ()
        if action == "review_text":
            require(classification == "free_text", "classification")
            require(inferred_classification(name) != "direct_identifier", "identifier_retention")
            require(validate_text_reviews(config["text_reviews"]), "text_review")
            text_reviews = tuple(config["text_reviews"].items())
        allowed = ()
        bins = []
        if action in {"keep", "code"}:
            values = config["allowed_values"]
            require(isinstance(values, list) and 1 <= len(values) <= 1000, "categories")
            require(all(isinstance(v, str) and safe_category(v) for v in values), "categories")
            require(len(set(values)) == len(values), "categories")
            allowed = tuple(values)
        if action == "bin":
            pairs = config["bins"]
            require(isinstance(pairs, list) and 2 <= len(pairs) <= 100, "bins")
            for pair in pairs:
                require(isinstance(pair, list) and len(pair) == 2, "bins")
                require(all(type(n) in {int, float} for n in pair), "bins")
                lo, hi = (Decimal(str(n)) for n in pair)
                require(lo.is_finite() and hi.is_finite() and lo < hi, "bins")
                require(not bins or bins[-1][1] == lo, "bins")
                bins.append((lo, hi))
        bounds = None
        max_decimal_places = None
        if action == "keep_numeric":
            pair = config["bounds"]
            require(isinstance(pair, list) and len(pair) == 2, "bounds")
            require(all(type(n) in {int, float} for n in pair), "bounds")
            lo, hi = (Decimal(str(n)) for n in pair)
            require(lo.is_finite() and hi.is_finite() and 0 <= lo < hi, "bounds")
            bounds = (lo, hi)
            if version == 2:
                max_decimal_places = config["max_decimal_places"]
                require(type(max_decimal_places) is int and 0 <= max_decimal_places <= 6, "bounds")
        columns[name] = ColumnRule(
            action, classification, allowed, tuple(bins), bounds, max_decimal_places, text_reviews
        )
        require(all(len(label) <= 64 for label in columns[name].labels), "bins")
    current_field = None
    require(sum(r.action == "pseudonymise" for r in columns.values()) == 1, "source_key_count")
    return Policy(columns, raw["min_group_size"], version)


def load_policy(path: Path) -> Policy:
    try:
        raw = yaml.load(read_bounded(path, 256 * 1024).decode("utf-8"), Loader=StrictLoader)
        return parse_policy(raw)
    except (yaml.YAMLError, UnicodeError, RecursionError, ValueError, TypeError):
        raise SafetyError("Policy could not be parsed safely; see policy-format.md.") from None
