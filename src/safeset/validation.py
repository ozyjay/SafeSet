from collections import Counter
from dataclasses import asdict, dataclass, field

from .classification import canonical_numeric, inferred_classification, safe_category
from .errors import SafetyError
from .ingestion import Table
from .policy import Policy
from .pseudonyms import valid_id


@dataclass
class ValidationReport:
    rows: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    minimum_class_size: int = 0
    unique_records: int = 0
    unique_fraction: float = 0.0
    small_class_records: int = 0
    small_cells: int = 0
    classifications: dict[str, str] = field(default_factory=dict)
    rejected_field_classes: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.errors

    def require_pass(self) -> None:
        if not self.passed:
            raise SafetyError("Validation failed; no export is permitted.")

    def summary(self) -> dict:
        return {
            **asdict(self),
            "passed": self.passed,
            "notice": "Passing checks does not establish anonymity. Review export suitability.",
        }


def validate(table: Table, policy: Policy) -> ValidationReport:
    report = ValidationReport(len(table.rows))
    if len(set(table.columns)) != len(table.columns) or set(table.columns) != set(
        policy.output_columns
    ):
        report.errors.append("Unexpected or missing output columns.")
        rejected = Counter(
            policy.columns[name].classification
            if name in policy.columns
            else inferred_classification(name)
            for name in table.columns
            if name not in policy.output_columns
        )
        report.rejected_field_classes = dict(rejected)
        if rejected.get("direct_identifier"):
            report.errors.append("Direct identifier fields are prohibited in exports.")
        if rejected.get("free_text"):
            report.errors.append("Free-text fields are prohibited in exports.")
        if rejected.get("unknown"):
            report.errors.append("Unclassified fields are prohibited in exports.")
        return report
    if not table.rows:
        report.errors.append("Empty dataset.")
        return report
    if any(set(row) != set(table.columns) for row in table.rows):
        report.errors.append("Malformed record schema.")
        return report
    ids = [r["record_id"] for r in table.rows]
    if any(not valid_id(v) for v in ids) or len(set(ids)) != len(ids):
        report.errors.append("Malformed or duplicate pseudonymous IDs.")
    report.classifications = {"record_id": "pseudonymous_identifier"}
    attributes = policy.output_columns[1:]
    for name in attributes:
        rule = policy.columns[name]
        report.classifications[name] = rule.classification
        values = [r[name] for r in table.rows]
        if rule.action == "keep":
            valid_values = all(v in rule.allowed_values and safe_category(v) for v in values)
        elif rule.action == "bin":
            valid_values = all(v in rule.labels for v in values)
        elif rule.action == "code":
            valid_values = all(valid_id(v) for v in values)
        else:
            valid_values = all(
                canonical_numeric(v, rule.bounds, rule.max_decimal_places) == v for v in values
            )
        if not valid_values:
            report.errors.append(
                "Retained values violate an approved domain or contain unsafe text."
            )
        counts = Counter(values)
        report.small_cells += sum(n < policy.min_group_size for n in counts.values())
        if len(counts) / len(values) > 0.5:
            report.warnings.append("A retained attribute has high cardinality.")
    if any(policy.columns[name].action == "keep_numeric" for name in attributes):
        report.warnings.append("Exact numeric values are retained; review disclosure risk.")
    if any(policy.columns[name].action == "code" for name in attributes):
        report.warnings.append("Coded categories still reveal grouping and frequency patterns.")
    classes = Counter(tuple(r[n] for n in attributes) for r in table.rows)
    report.minimum_class_size = min(classes.values())
    report.unique_records = sum(n == 1 for n in classes.values())
    report.unique_fraction = report.unique_records / len(table.rows)
    report.small_class_records = sum(n for n in classes.values() if n < policy.min_group_size)
    if report.small_cells:
        report.errors.append("Small retained-value groups fall below the policy threshold.")
    if report.small_class_records:
        report.errors.append("Small joint equivalence classes fall below the policy threshold.")
    report.errors = list(dict.fromkeys(report.errors))
    return report
