"""Explicit, local review of bounded narrative cells; no anonymity inference."""

import hashlib
from collections import Counter

from .classification import DATE, EMAIL, LONG_DIGITS, TIME, inferred_classification
from .errors import SafetyError
from .ingestion import MAX_FIELD, Table

TEXT_REVIEW_ERROR = "Long-form text needs complete current review with identifying details removed."
TEXT_BUNDLE_ERROR = "Long-form text protection requires a restoration bundle."
MAX_TEXT_REVIEWS = 1000
MAX_REVIEW_BYTES = 200_000


class TextReviewRejection(SafetyError):
    """Fixed reason codes keyed only by existing local review bindings."""

    def __init__(self, issues: dict[str, list[str]]) -> None:
        super().__init__(TEXT_REVIEW_ERROR)
        self.issues = issues


def unsafe_text_controls(value: str) -> bool:
    return any((ord(ch) < 32 and ch not in "\t\r\n") or ord(ch) == 127 for ch in value)


def text_digest(value: str) -> str:
    """Content binding only: never an identity or exported pseudonym."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def reviewed_text_issues(value: object) -> list[str]:
    if not isinstance(value, str):
        return ["unsupported_text"]
    issues = []
    if len(value) > MAX_FIELD:
        issues.append("too_long")
    if value and not value.strip():
        issues.append("whitespace_only")
    if value.lstrip().startswith(("=", "+", "-", "@")):
        issues.append("formula_prefix")
    if unsafe_text_controls(value):
        issues.append("control_character")
    for code, pattern in (
        ("email", EMAIL),
        ("date", DATE),
        ("time", TIME),
        ("long_digits", LONG_DIGITS),
    ):
        if pattern.search(value):
            issues.append(code)
    return issues


def reviewed_text_valid(value: object) -> bool:
    return not reviewed_text_issues(value)


def validate_text_reviews(value: object) -> bool:
    return (
        isinstance(value, dict)
        and 1 <= len(value) <= MAX_TEXT_REVIEWS
        and all(
            isinstance(key, str)
            and len(key) == 64
            and all(ch in "0123456789abcdef" for ch in key)
            and reviewed_text_valid(text)
            for key, text in value.items()
        )
        and sum(len(text.encode("utf-8")) for text in value.values()) <= MAX_REVIEW_BYTES
    )


def reviewed_value(value: str, reviews: tuple[tuple[str, str], ...]) -> str:
    try:
        result = dict(reviews)[text_digest(value)]
    except KeyError:
        raise SafetyError(TEXT_REVIEW_ERROR) from None
    if not reviewed_text_valid(result):
        raise SafetyError(TEXT_REVIEW_ERROR)
    return result


def check_text_review_source(source: Table, policy) -> None:
    """Bind every approved version to exact source content and known identifiers."""
    rules = [(name, rule) for name, rule in policy.columns.items() if rule.action == "review_text"]
    if not rules:
        return
    identifiers = {
        row[name].strip().casefold()
        for name, rule in policy.columns.items()
        if rule.classification == "direct_identifier"
        or rule.action == "pseudonymise"
        or inferred_classification(name) == "direct_identifier"
        for row in source.rows
        if row[name].strip()
    }
    for name, rule in rules:
        approve_text_reviews(source, name, dict(rule.text_reviews), identifiers)


def check_text_candidate(source: Table, policy, protected: Table) -> None:
    check_text_review_source(source, policy)
    for name, rule in policy.columns.items():
        if rule.action == "review_text" and (
            len(source.rows) != len(protected.rows)
            or any(
                reviewed_value(original[name], rule.text_reviews) != result[name]
                for original, result in zip(source.rows, protected.rows, strict=True)
            )
        ):
            raise SafetyError(TEXT_REVIEW_ERROR)


def approve_text_reviews(
    source: Table, column: str, reviews: object, identifiers: set[str] | None = None
) -> None:
    if (
        column not in source.columns
        or not isinstance(reviews, dict)
        or not 1 <= len(reviews) <= MAX_TEXT_REVIEWS
        or any(
            not isinstance(key, str)
            or len(key) != 64
            or any(ch not in "0123456789abcdef" for ch in key)
            for key in reviews
        )
    ):
        raise TextReviewRejection({"": ["review_incomplete"]})
    issues = {
        key: codes for key, value in reviews.items() if (codes := reviewed_text_issues(value))
    }
    global_issues = []
    if set(reviews) != {text_digest(row[column]) for row in source.rows}:
        global_issues.append("source_changed")
    if any(unsafe_text_controls(row[column]) for row in source.rows):
        global_issues.append("source_controls")
    if (
        sum(len(text.encode("utf-8")) for text in reviews.values() if isinstance(text, str))
        > MAX_REVIEW_BYTES
    ):
        global_issues.append("review_limit")
    if identifiers is None:
        identifiers = {
            row[name].strip().casefold()
            for name in source.columns
            if inferred_classification(name) == "direct_identifier"
            for row in source.rows
            if row[name].strip()
        }
    for key, output in reviews.items():
        if not isinstance(output, str):
            continue
        folded = output.casefold()
        for identifier in identifiers:
            start = 0
            while (position := folded.find(identifier, start)) >= 0:
                end = position + len(identifier)
                if (
                    position == 0
                    or not (folded[position - 1].isalnum() or folded[position - 1] == "_")
                ) and (end == len(folded) or not (folded[end].isalnum() or folded[end] == "_")):
                    if "known_identifier" not in issues.setdefault(key, []):
                        issues[key].append("known_identifier")
                    break
                start = position + 1
    if global_issues:
        issues[""] = global_issues
    if issues:
        raise TextReviewRejection(issues)


def review_entries(table: Table, column: str) -> list[dict]:
    """Only a dedicated operator action may send these paragraphs to the local UI."""
    if column not in table.columns:
        raise SafetyError(TEXT_REVIEW_ERROR)
    counts = Counter(row[column] for row in table.rows)
    if (
        not counts
        or len(counts) > MAX_TEXT_REVIEWS
        or sum(len(text.encode("utf-8")) for text in counts) > MAX_REVIEW_BYTES
    ):
        raise SafetyError(TEXT_REVIEW_ERROR)
    return [
        {"digest": text_digest(text), "original": text, "count": count}
        for text, count in counts.items()
    ]
