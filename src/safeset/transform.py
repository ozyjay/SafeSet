from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .classification import canonical_numeric, formula_or_control
from .errors import SafetyError
from .ingestion import Table
from .policy import Policy
from .pseudonyms import new_id


@dataclass(frozen=True)
class Candidate:
    table: Table
    mapping: dict


def sanitise(source: Table, policy: Policy) -> Candidate:
    if set(source.columns) != set(policy.columns):
        raise SafetyError("Source schema differs from policy; missing or unexpected columns.")
    if not source.rows:
        raise SafetyError("Empty datasets cannot be exported.")
    identities = [r[policy.source_key] for r in source.rows]
    if any(not v.strip() or formula_or_control(v) for v in identities) or len(
        set(identities)
    ) != len(identities):
        raise SafetyError("Source keys must be non-empty and unique.")
    records = {}
    rows = []
    codes: dict[str, dict[str, str]] = {}
    issued: set[str] = set()
    for row in source.rows:
        record_id = new_id()
        if record_id in issued:
            raise SafetyError("Random ID collision; no export produced.")
        issued.add(record_id)
        records[record_id] = row[policy.source_key]
        result = {"record_id": record_id}
        for name, rule in policy.columns.items():
            if rule.action == "keep":
                result[name] = row[name]
            elif rule.action == "code":
                value = row[name]
                if value not in rule.allowed_values:
                    raise SafetyError("Source category is outside the approved domain.")
                column_codes = codes.setdefault(name, {})
                if value not in column_codes:
                    token = new_id()
                    if token in issued:
                        raise SafetyError("Random code collision; no export produced.")
                    issued.add(token)
                    column_codes[value] = token
                result[name] = column_codes[value]
            elif rule.action == "keep_numeric":
                value = canonical_numeric(row[name], rule.bounds, rule.max_decimal_places)
                if value is None:
                    raise SafetyError("Numeric input violates approved bounds or precision.")
                result[name] = value
            elif rule.action == "bin":
                try:
                    value = Decimal(row[name])
                except InvalidOperation:
                    raise SafetyError("A numeric input cannot be binned.") from None
                if not value.is_finite():
                    raise SafetyError("Non-finite numeric input is prohibited.")
                for i, (lo, hi) in enumerate(rule.bins):
                    if lo <= value < hi or (i == len(rule.bins) - 1 and value == hi):
                        result[name] = rule.labels[i]
                        break
                else:
                    raise SafetyError("Numeric input falls outside approved bins.")
        rows.append(result)
    return Candidate(
        Table(policy.output_columns, tuple(rows)),
        {"version": 1, "source_column": policy.source_key, "records": records},
    )
