from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .classification import formula_or_control
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
    for row in source.rows:
        record_id = new_id()
        if record_id in records:
            raise SafetyError("Random ID collision; no export produced.")
        records[record_id] = row[policy.source_key]
        result = {"record_id": record_id}
        for name, rule in policy.columns.items():
            if rule.action == "keep":
                result[name] = row[name]
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
