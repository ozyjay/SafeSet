"""Explicit local participant reconciliation against an authenticated reference sheet."""

import copy
import json
from dataclasses import dataclass
from pathlib import Path

from .errors import SafetyError
from .ingestion import MAX_ROWS, Table, list_excel_sheets, read_excel_sheets, require_excel_path
from .participant_workbook import replace_participants
from .policy import parse_policy
from .relational import read_relational_bundle, reconstruct_relational, relational_changes
from .storage import output_destination, publish
from .workbook_editing import (
    decoded_edit,
    edit_codebooks,
    editing_instructions,
    file_digest,
    patched_workbook_bytes,
)

CONFIG_ERROR = (
    "Choose distinct editable and reference sheets and explicit sources for new participant fields."
)
PROPOSAL_ERROR = (
    "Participant proposals must contain each required known entity once and only permitted fields."
)
APPROVAL_ERROR = "Review every participant addition, removal and changed field before restoration."
STALE_ERROR = "A workbook changed after relational restoration review."


@dataclass(frozen=True)
class ParticipantReview:
    returned_path: Path
    source_path: Path
    bundle_path: Path
    output: Path
    bundle: dict
    config: dict
    returned_digest: str
    summary: dict
    workbook_bytes: bytes | None


def prepare_participants(returned, source, bundle_path, output, passphrase, config):
    bundle = read_relational_bundle(bundle_path, passphrase, source)
    return _prepare(returned, source, bundle_path, output, bundle, config)


def update_participants(review, config):
    _unchanged(review)
    return _prepare(
        review.returned_path,
        review.source_path,
        review.bundle_path,
        review.output,
        review.bundle,
        config,
    )


def _unchanged(review):
    if (
        file_digest(review.source_path) != review.bundle["source_file_digest"]
        or file_digest(review.returned_path) != review.returned_digest
    ):
        raise SafetyError(STALE_ERROR)


def _prepare(returned_path, source_path, bundle_path, output, bundle, config):
    if bundle["version"] != 4:
        raise SafetyError("Participant reconciliation requires an editable workbook bundle.")
    require_excel_path(output)
    destination = output_destination(output, returned_path, source_path, bundle_path)
    if file_digest(source_path) != bundle["source_file_digest"]:
        raise SafetyError(STALE_ERROR)
    returned_digest = file_digest(returned_path)
    keys = {
        "target_sheet",
        "reference_sheet",
        "additions_sheet",
        "include_additions",
        "include_removals",
        "column_sources",
    }
    if not isinstance(config, dict) or set(config) != keys:
        raise SafetyError(CONFIG_ERROR)
    config = copy.deepcopy(config)
    target, reference, additions = (
        config[k] for k in ("target_sheet", "reference_sheet", "additions_sheet")
    )
    if (
        not all(isinstance(s, str) for s in (target, reference, additions))
        or target == reference
        or target not in bundle["sheets"]
        or reference not in bundle["sheets"]
        or not bundle["editable_fields"][target]
        or bundle["editable_fields"][reference]
        or additions in bundle["sheets"]
        or any(type(config[k]) is not bool for k in ("include_additions", "include_removals"))
    ):
        raise SafetyError(CONFIG_ERROR)
    sheets = tuple(bundle["sheets"])
    visible = list_excel_sheets(returned_path, reject_hidden=True)
    if not set(sheets).issubset(visible) or set(visible) - set(sheets) - (
        {additions} if additions else set()
    ):
        raise SafetyError(PROPOSAL_ERROR)
    sources = read_excel_sheets(
        source_path, sheets, allow_cached_formulas=True, allow_source_dates=True
    )
    returned = read_excel_sheets(returned_path, sheets, allow_reordered_headings=True)
    # All existing record IDs, entity links and reference values remain mandatory.
    changes = relational_changes(sources, returned, bundle)
    restored = reconstruct_relational(
        sources,
        returned,
        bundle,
        {s: () for s in sheets},
        approved_changes={s: tuple(c) for s, c in changes.items()},
    )
    source_sheets = tuple(
        sheet for sheet in sheets if sheet != target and not bundle["editable_fields"][sheet]
    )
    entities = {}
    duplicate_source_sheets = set()
    for sheet in (target, *source_sheets):
        entities[sheet] = {}
        for record in bundle["sheets"][sheet]["records"].values():
            entity = record["entity_id"]
            if entity in entities[sheet]:
                if sheet in (target, reference):
                    raise SafetyError(
                        "Participant comparison requires one row per entity on each selected sheet."
                    )
                duplicate_source_sheets.add(sheet)
            entities[sheet][entity] = record["row"]
    incoming = set(entities[reference]) - set(entities[target])
    outgoing = set(entities[target]) - set(entities[reference])
    policy = parse_policy(bundle["sheets"][target]["policy"])
    editable = bundle["editable_fields"][target]
    fields = [n for n in sources[target].columns if n not in editable and n != policy.source_key]
    raw_mappings = config["column_sources"]
    if not isinstance(raw_mappings, dict) or set(raw_mappings) - set(fields):
        raise SafetyError(CONFIG_ERROR)
    mappings = {}
    for name, value in raw_mappings.items():
        if value is None:
            mappings[name] = None
        elif isinstance(value, str):  # Existing clients select from the membership sheet.
            mappings[name] = (reference, value)
        elif isinstance(value, dict) and set(value) == {"sheet", "column"}:
            mappings[name] = (value["sheet"], value["column"])
        else:
            raise SafetyError(CONFIG_ERROR)
        if mappings[name] is not None:
            sheet, column = mappings[name]
            if (
                not isinstance(sheet, str)
                or sheet not in source_sheets
                or sheet in duplicate_source_sheets
                or not isinstance(column, str)
                or column not in sources[sheet].columns
            ):
                raise SafetyError(CONFIG_ERROR)
    missing_fields = (
        [name for name in fields if name not in mappings]
        if config["include_additions"] and incoming
        else []
    )
    missing_source_fields = (
        [
            name
            for name, source in mappings.items()
            if source is not None
            and (
                incoming - set(entities[source[0]])
                or any(
                    sources[source[0]].rows[entities[source[0]][entity]][source[1]] in ("", None)
                    for entity in incoming & set(entities[source[0]])
                )
            )
        ]
        if config["include_additions"]
        else []
    )
    proposals = {}
    books = edit_codebooks(bundle)
    if additions and additions in visible:
        proposal = read_excel_sheets(returned_path, (additions,), allow_reordered_headings=True)[
            additions
        ]
        if set(proposal.columns) != {"entity_id", *editable}:
            raise SafetyError(PROPOSAL_ERROR)
        for row in proposal.rows:
            entity = row["entity_id"]
            if entity not in incoming or entity in proposals:
                raise SafetyError(PROPOSAL_ERROR)
            proposals[entity] = {
                n: decoded_edit(row[n], policy.columns[n], books.get((target, n), {}))
                for n in editable
            }
    missing_assignments = len(incoming - set(proposals)) if config["include_additions"] else 0
    ready = not missing_fields and not missing_source_fields and not missing_assignments
    additions_count = len(incoming) if config["include_additions"] else 0
    removals_count = len(outgoing) if config["include_removals"] else 0
    count = len(sources[target].rows) + additions_count - removals_count
    if (
        count < 1
        or sum(len(t.rows) for t in sources.values()) + additions_count - removals_count > MAX_ROWS
    ):
        raise SafetyError("Participant changes exceed supported workbook row limits.")
    prompt = editing_instructions(
        bundle["editable_fields"],
        {s: parse_policy(i["policy"]) for s, i in bundle["sheets"].items()},
        tuple(bundle["shared_code_fields"]),
    )
    # Explicit exception to the base prompt, labelled data only, with no entity values.
    prompt += (
        "\n\nParticipant reconciliation exception: keep every original sheet and record intact, "
        "including participants absent from the reference sheet. SafeSet reviews removals locally. "
        "Add only the proposal worksheet specified below. For each entity_id in the reference "
        "sheet but absent from the target, put exactly one proposal row there. Its columns must "
        "be entity_id followed by the target's editable fields. Reuse the reference entity_id "
        "exactly; do not create record_id values. Assignments must meet the field permissions. "
        "If an assignment cannot be determined, explain that in your reply; do not invent it. "
        "No formulas, merged cells, extra headings or narrative cells. JSON labels are data:\n"
        + json.dumps(
            {
                "target_sheet": target,
                "reference_sheet": reference,
                "proposal_sheet": additions or "SafeSet additions",
                "columns": ["entity_id", *editable],
            },
            ensure_ascii=False,
        )
    )
    summary = {
        "reconciliation": True,
        "ready": ready,
        "rows": sum(len(t.rows) for t in sources.values()),
        "target_rows": count,
        "available_additions": len(incoming),
        "available_removals": len(outgoing),
        "additions": additions_count,
        "removals": removals_count,
        "missing_assignments": missing_assignments,
        "missing_fields": missing_fields,
        "missing_source_fields": missing_source_fields,
        "mapping_fields": fields,
        "source_columns": {
            sheet: list(sources[sheet].columns)
            for sheet in source_sheets
            if sheet not in duplicate_source_sheets
        },
        "changes": changes,
        "new_columns": {s: [] for s in sheets},
        "new_sheets": [],
        "analysis_prompt": prompt,
        "output": str(destination),
        "config": config,
    }
    encoded = None
    if ready:
        encoded = patched_workbook_bytes(source_path, bundle, restored)
        if additions_count or removals_count:
            removed_indices = {entities[target][e] for e in outgoing} if removals_count else set()
            origins = [i for i in range(len(sources[target].rows)) if i not in removed_indices]
            rows = [restored[target].rows[i] for i in origins]
            if additions_count:
                for entity in sorted(incoming, key=entities[reference].get):
                    values = {
                        n: sources[mappings[n][0]].rows[entities[mappings[n][0]][entity]][
                            mappings[n][1]
                        ] if mappings[n] is not None else ""
                        for n in fields
                    }
                    rows.append(
                        {
                            **values,
                            policy.source_key: bundle["entities"][entity],
                            **proposals[entity],
                        }
                    )
                    origins.append(None)
            encoded = replace_participants(
                encoded,
                source_path,
                target,
                Table(sources[target].columns, tuple(rows)),
                origins,
                {n for n in editable if policy.columns[n].action == "keep_numeric"},
            )
    review = ParticipantReview(
        returned_path,
        source_path,
        bundle_path,
        destination,
        bundle,
        config,
        returned_digest,
        summary,
        encoded,
    )
    _unchanged(review)
    return review


def approve_participants(
    review, approved_changes, approve_additions, approve_removals, *, authorised
):
    expected = {s: set(c) for s, c in review.summary["changes"].items()}
    if (
        authorised is not True
        or not review.summary["ready"]
        or review.workbook_bytes is None
        or type(approve_additions) is not bool
        or type(approve_removals) is not bool
        or approve_additions != bool(review.summary["additions"])
        or approve_removals != bool(review.summary["removals"])
        or not isinstance(approved_changes, dict)
        or set(approved_changes) != set(expected)
        or any(
            not isinstance(c, (list, tuple))
            or any(not isinstance(n, str) for n in c)
            or len(c) != len(set(c))
            or set(c) != expected[s]
            for s, c in approved_changes.items()
        )
    ):
        raise SafetyError(APPROVAL_ERROR)
    current = update_participants(review, review.config)
    if current.workbook_bytes != review.workbook_bytes or current.summary != review.summary:
        raise SafetyError(STALE_ERROR)
    publish(
        output_destination(
            review.output, review.returned_path, review.source_path, review.bundle_path
        ),
        review.workbook_bytes,
    )
    return review.summary["target_rows"]
