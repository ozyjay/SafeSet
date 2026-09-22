"""Strict local policy authoring for the desktop form."""

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from .classification import safe_category
from .errors import SafetyError
from .ingestion import read_excel
from .policy import load_policy, parse_policy
from .storage import output_destination, publish


@dataclass
class RuleDraft:
    action: str = ""
    classification: str = ""
    allowed_values: tuple[str, ...] = ()
    bins: tuple[tuple[int | float, int | float], ...] = ()
    bounds: tuple[int | float, int | float] | None = None
    max_decimal_places: int | None = None


def local_categories(
    source: Path, column: str, sheet: str | tuple[str, ...] | None = None
) -> tuple[str, ...]:
    """Return reviewed local labels only for bounded categorical domains."""
    table = read_excel(source, sheet, allow_cached_formulas=True, allow_source_dates=True)
    if column not in table.columns:
        raise SafetyError("Source headings changed; load the Excel workbook headings again.")
    values = set(row[column] for row in table.rows)
    if not values or len(values) > 1000 or any(not safe_category(value) for value in values):
        raise SafetyError("Column has too many or unsafe distinct values for a category allowlist.")
    return tuple(sorted(values))


def load_drafts(
    source: Path, policy_path: Path, sheet: str | tuple[str, ...] | None = None
) -> tuple[dict[str, RuleDraft], int]:
    """Load an existing strict policy for review and saving under a new filename."""
    table = read_excel(source, sheet, allow_cached_formulas=True, allow_source_dates=True)
    policy = load_policy(policy_path)
    if set(table.columns) != set(policy.columns):
        raise SafetyError("Policy and source headings differ.")

    def number(value):
        return int(value) if value == value.to_integral_value() else float(value)

    drafts = {}
    for name in table.columns:
        rule = policy.columns[name]
        drafts[name] = RuleDraft(
            action=rule.action,
            classification=rule.classification,
            allowed_values=rule.allowed_values,
            bins=tuple((number(lo), number(hi)) for lo, hi in rule.bins),
            bounds=None
            if rule.bounds is None
            else (number(rule.bounds[0]), number(rule.bounds[1])),
            max_decimal_places=rule.max_decimal_places if rule.action == "keep_numeric" else None,
        )
    return drafts, policy.min_group_size


def parse_pairs(text: str) -> tuple[tuple[int | float, int | float], ...]:
    """Read one numeric interval per line without echoing malformed input."""
    try:
        pairs = tuple(tuple(json.loads(f"[{line}]")) for line in text.splitlines())
    except (ValueError, TypeError):
        raise SafetyError("Use one numeric lower,upper pair per line.") from None
    if any(
        len(pair) != 2 or any(type(value) not in {int, float} for value in pair) for pair in pairs
    ):
        raise SafetyError("Use one numeric lower,upper pair per line.")
    return pairs


def parse_number(text: str) -> int | float:
    """Read a JSON-style number with a fixed error message."""
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        raise SafetyError("Enter a plain numeric bound.") from None
    if type(value) not in {int, float}:
        raise SafetyError("Enter a plain numeric bound.")
    return value


def policy_payload(drafts: dict[str, RuleDraft], threshold: str) -> dict:
    """Build a version 2 payload; the canonical parser enforces every safety rule."""
    if not threshold.isascii() or not threshold.isdecimal():
        raise SafetyError("Enter a whole-number minimum group size of at least 2.")
    columns = {}
    for name, draft in drafts.items():
        classification = draft.classification or ("unknown" if draft.action == "drop" else "")
        config: dict = {"action": draft.action, "classification": classification}
        if draft.action in {"keep", "code"}:
            config["allowed_values"] = list(draft.allowed_values)
        elif draft.action == "bin":
            config["bins"] = [list(pair) for pair in draft.bins]
        elif draft.action == "keep_numeric":
            config["bounds"] = list(draft.bounds) if draft.bounds is not None else None
            config["max_decimal_places"] = draft.max_decimal_places
        columns[name] = config
    payload = {"version": 2, "min_group_size": int(threshold), "columns": columns}
    parse_policy(payload)
    return payload


def save_policy(
    source: Path,
    destination: Path,
    drafts: dict[str, RuleDraft],
    threshold: str,
    sheet: str | tuple[str, ...] | None = None,
) -> Path:
    """Save a validated policy privately outside repositories, without overwriting."""
    table = read_excel(source, sheet, allow_cached_formulas=True, allow_source_dates=True)
    if set(table.columns) != set(drafts):
        raise SafetyError("Source headings changed; load the Excel workbook headings again.")
    payload = policy_payload(drafts, threshold)
    data = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False).encode("utf-8")
    if len(data) > 256 * 1024:
        raise SafetyError("Policy exceeds the supported size limit.")
    path = output_destination(destination, source)
    publish(path, data)
    return path
