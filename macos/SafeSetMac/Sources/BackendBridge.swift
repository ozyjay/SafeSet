import Foundation

enum BridgeFailure: Error {
    case unavailable
    case rejected(String)
    case textReviewRejected([String: [String]], [String: [TextReviewHighlight]])
}

struct TextReviewHighlight: Equatable, Identifiable {
    let reason: String
    let start: Int
    let end: Int
    var id: String { "\(reason):\(start):\(end)" }
    var range: NSRange { NSRange(location: start, length: end - start) }

    func valid(in text: String) -> Bool {
        let units = Array(text.utf16)
        guard start >= 0, end > start, end <= units.count else { return false }
        func boundary(_ offset: Int) -> Bool {
            offset == 0 || offset == units.count
                || !((0xD800...0xDBFF).contains(units[offset - 1])
                     && (0xDC00...0xDFFF).contains(units[offset]))
        }
        return boundary(start) && boundary(end)
    }
}

enum TextReviewFeedback {
    static let messages: [String: String] = [
        "email": "Remove or replace an email address in this response.",
        "date": "Remove or generalise a date in this response.",
        "time": "Remove or generalise a clock time in this response.",
        "long_digits": "Remove or replace a long number or phone-number pattern.",
        "known_identifier": "Remove or replace a name or identifier also found in this worksheet's identifier fields.",
        "formula_prefix": "The response starts with =, +, - or @. Rewrite the opening so it does not begin with a formula prefix.",
        "control_character": "Remove unsupported control characters; ordinary tabs and line breaks are allowed.",
        "whitespace_only": "This response contains only whitespace. Clear it completely to exclude its text.",
        "too_long": "Shorten this response to 4,096 characters or fewer.",
        "unsupported_text": "Use plain text for this response.",
        "review_incomplete": "The response review is incomplete. Open a new review of this field.",
        "identifier_field": "This heading indicates an identifier field. Remove it or use it as the linking identifier; it cannot be retained as reviewed narrative text.",
        "source_changed": "The source responses changed. Cancel and open a new review of this field.",
        "source_controls": "The original field contains unsupported control characters. Correct the source workbook, then review it again.",
        "review_limit": "The reviewed field exceeds the local review size limit. Shorten or clear responses."
    ]

    static func decode(_ raw: [String: [String]]) -> [String: [String]] {
        var result: [String: [String]] = [:]
        for (digest, codes) in raw {
            guard digest.isEmpty || (digest.count == 64 && digest.allSatisfy({
                "0123456789abcdef".contains($0)
            })) else { continue }
            let descriptions = codes.compactMap { messages[$0] }
            if !descriptions.isEmpty { result[digest] = descriptions }
        }
        return result
    }

    static func decodeHighlights(_ raw: Any?) -> [String: [TextReviewHighlight]] {
        guard let payload = raw as? [String: [[String: Any]]] else { return [:] }
        var result: [String: [TextReviewHighlight]] = [:]
        for (digest, ranges) in payload {
            guard digest.count == 64 && digest.allSatisfy({ "0123456789abcdef".contains($0) })
                else { continue }
            result[digest] = ranges.prefix(128).compactMap { range in
                guard let reason = range["reason"] as? String, messages[reason] != nil,
                      let start = range["start"] as? Int, let end = range["end"] as? Int,
                      start >= 0, end > start, end <= 1_048_576 else { return nil }
                return TextReviewHighlight(reason: reason, start: start, end: end)
            }
        }
        return result
    }
}

final class BackendBridge: @unchecked Sendable {
    private let process = Process()
    private let input = Pipe()
    private let output = Pipe()
    private let lock = NSLock()
    private let limit = 1_048_576

    init() throws {
        let executable = Bundle.main.bundleURL
            .appendingPathComponent("Contents/Helpers/SafeSetBackend/safeset-backend")
        guard FileManager.default.isExecutableFile(atPath: executable.path) else {
            throw BridgeFailure.unavailable
        }
        process.executableURL = executable
        process.standardInput = input
        process.standardOutput = output
        process.standardError = FileHandle.nullDevice
        process.environment = [
            "HOME": NSHomeDirectory(), "TMPDIR": NSTemporaryDirectory(), "LANG": "en_AU.UTF-8"
        ]
        try process.run()
    }

    deinit {
        input.fileHandleForWriting.closeFile()
        if process.isRunning { process.terminate() }
    }

    func request(_ command: String, _ payload: [String: Any]) throws -> [String: Any] {
        lock.lock()
        defer { lock.unlock() }
        guard process.isRunning else { throw BridgeFailure.unavailable }
        let id = UUID().uuidString
        let request: [String: Any] = [
            "version": 1, "id": id, "command": command, "payload": payload
        ]
        guard JSONSerialization.isValidJSONObject(request),
              let data = try? JSONSerialization.data(withJSONObject: request),
              data.count < limit else { throw BridgeFailure.rejected("Invalid local request.") }
        input.fileHandleForWriting.write(data + Data([10]))
        var line = Data()
        while line.count <= limit {
            let byte = output.fileHandleForReading.readData(ofLength: 1)
            guard !byte.isEmpty else { throw BridgeFailure.unavailable }
            if byte == Data([10]) { break }
            line.append(byte)
        }
        guard line.count <= limit,
              let response = try? JSONSerialization.jsonObject(with: line) as? [String: Any],
              response["version"] as? Int == 1,
              response["id"] as? String == id else { throw BridgeFailure.unavailable }
        if response["ok"] as? Bool == true {
            guard let result = response["result"] as? [String: Any] else {
                throw BridgeFailure.unavailable
            }
            return result
        }
        let code = response["error"] as? String ?? "invalid_request"
        if code == "text_review_required", let raw = response["issues"] as? [String: [String]] {
            let feedback = TextReviewFeedback.decode(raw)
            if !feedback.isEmpty {
                throw BridgeFailure.textReviewRejected(
                    feedback, TextReviewFeedback.decodeHighlights(response["highlights"])
                )
            }
        }
        let message: String
        switch code {
        case "review_expired": message = "This review is no longer active. Select Validate and review again, then update your field selections before approving restoration."
        case "safety_rejected": message = "SafeSet rejected this operation. Review the files and decisions."
        case "result_workbook_invalid": message = "The result workbook contains an unknown or mismatched pseudonymous ID, an unsafe value, or an unsupported structure. Keep result cells to short safe values and use only IDs from the protected workbook."
        case "result_workbook_join": message = "Choose source fields and a matching source worksheet for each participant result sheet. Every result ID must have one unambiguous source match. Correct the selection, then validate again."
        case "result_workbook_approval": message = "Review and approve every result field and new category before creating the restored workbook."
        case "edit_configuration": message = "Select editable fields that keep short categories, replace categories with random codes or keep exact numbers. Identifiers, removed fields, grouped ranges and reviewed long-form text cannot be edited."
        case "edit_formula": message = "An editable field contains a formula or date. Keep that field as reference data; select direct category or numeric values for editing."
        case "edit_domain": message = "An edited value is outside its approved categories, known codes or numeric bounds. Use an existing permitted value, or start a new protection run with revised decisions."
        case "edit_structure": message = "This workbook permits edits to selected existing fields. Preserve its original protected sheets and headings. Put narrative findings in the ChatGPT reply rather than extra columns or sheets."
        case "edit_approval": message = "Review and approve every changed field before restoration."
        case "participant_configuration": message = "Participant comparison settings are incomplete. Recheck the target and membership sheets, additions sheet name and selected field sources."
        case "participant_sheet_selection": message = "Choose different worksheets for the target and membership list."
        case "participant_sheet_bundle": message = "A selected worksheet was not included in this private bundle. Protect the workbook again with both the target and membership sheets selected."
        case "participant_target_permissions": message = "The target sheet has no editable fields in this private bundle. Select an editable target or protect the workbook again with the needed fields editable."
        case "participant_membership_permissions": message = "This private bundle reports editable fields for the selected membership sheet. The Restore picker cannot change saved permissions. If the protection review showed this sheet as reference only, its saved permissions need investigation."
        case "participant_proposal_name": message = "The additions sheet name is already used by a protected worksheet. Choose a different proposal sheet name."
        case "participant_field_source": message = "A saved new-participant field source no longer matches this comparison. Recheck the field source menus and update the review."
        case "participant_proposals": message = "Keep every original sheet and record intact. The selected additions sheet must contain only entity_id and the target's editable fields, with each new reference participant at most once. Use the reconciliation prompt."
        case "participant_approval": message = "Review every participant addition, removal and changed field before restoration."
        case "participant_layout": message = "Participant changes need one plain range or Excel table, with empty space below it. Formulas, merged data cells, comments, links, hidden data, totals, validation rules and conditional formatting in the target are not supported for participant changes."
        case "participant_bundle": message = "Participant comparison requires a bundle created with editable workbook permissions."
        case "participant_unique": message = "Each participant must occur once on the target sheet and once on the membership sheet for this comparison."
        case "participant_limits": message = "Participant changes must leave at least one target row and remain within the workbook row limit."
        case "edit_layout": message = "SafeSet could not safely apply edits to the original workbook layout. No restored workbook was created."
        case "edit_precision": message = "An edited numeric cell exceeds Excel's 15 significant-digit precision. Use a value Excel can store accurately, or keep that field as reference data."
        case "policy_configuration": message = "One or more field decisions are incomplete or incompatible. Check the identifier, classifications, approved categories and numeric settings on every selected worksheet."
        case "field_decisions": message = "Every field on every selected worksheet needs an explicit protection decision."
        case "text_review_required": message = "Review every response in this long-form text field, remove identifying details and approve the reviewed text. Changed source responses need a new review. Each response supports up to 4,096 characters; each field supports up to 1,000 distinct responses within the local review size limit."
        case "source_key_invalid": message = "A selected worksheet contains a blank or unsafe source identifier. Source identifiers must be non-empty text."
        case "reserved_heading": message = "A selected worksheet already uses record_id or entity_id, which are reserved output headings."
        case "empty_worksheet": message = "A selected worksheet has no data rows."
        case "category_domain": message = "A source category is outside the reviewed value list. Review the category values again."
        case "numeric_domain": message = "A non-blank numeric value does not fit the reviewed bounds, plain-number format or ranges. Genuine blank cells remain blank; whitespace-only cells are rejected."
        case "analysis_sheet": message = "An added analysis worksheet contains unsupported content. Use one table per sheet with unique headings in row 1. Keep non-blank cells to short categories (at most four words and 64 characters); remove narrative text and identifiers, then try again."
        case "analysis_sheet_approval": message = "Every added analysis worksheet must be explicitly approved before restoration."
        case "formula_result": message = "A source formula has no saved value. Recalculate and save the workbook locally, then try again."
        case "hidden_data": message = "A selected data range contains hidden rows or columns. Unhide them or select a clean table."
        case "hidden_worksheet": message = "The returned workbook contains a hidden worksheet. Unhide or remove it so every worksheet can be reviewed explicitly."
        case "merged_data": message = "A selected data range contains merged cells. On an added analysis worksheet, place each table on its own sheet with unique headings in row 1, and remove merged titles and spacer rows."
        case "active_content": message = "The workbook contains unsupported active or externally linked content."
        case "cell_features": message = "A selected data range contains unsupported comments or hyperlinks."
        case "cell_type": message = "A selected worksheet contains an unsupported cell type."
        case "destination_exists": message = "The selected output or bundle already exists. Choose a new filename."
        case "output_directory": message = "The selected output directory does not exist."
        case "repository_destination": message = "Operational data cannot be written inside a source-code repository."
        case "destination_separation": message = "The protected workbook and private bundle must use separate directories."
        case "shared_code_configuration": message = "Each shared category-code field must have the same heading and use Replace categories with random codes on at least two selected worksheets."
        case "bundle_authentication": message = "The private bundle could not be unlocked. Check that it belongs to this protected workbook and enter its passphrase again."
        case "bundle_unavailable": message = "SafeSet could not read the selected private bundle. Check its location and access permissions."
        case "bundle_incompatible": message = "The selected private bundle has an unsupported version or structure. Use the matching SafeSet app version and bundle."
        case "source_mismatch": message = "The original source workbook does not match the private bundle. Select the exact source used to create this protected workbook."
        case "worksheet_coverage": message = "A required protected worksheet is missing or changed. Restore every original protected worksheet in the returned workbook."
        case "protected_schema": message = "A protected worksheet is missing an original heading or has renamed it. Keep every heading from the SafeSet protected copy exactly, including spelling and case. You may reorder columns or place new result columns anywhere."
        case "result_schema": message = "The returned workbook has an unexpected or conflicting result heading. Give each new result column a unique heading that does not reuse an original source heading."
        case "record_ids": message = "A returned record ID is malformed or repeated. Restore the original record IDs."
        case "record_coverage": message = "The returned record_id values do not match this bundle. Use its original SafeSet-protected copy and keep every record_id exactly once on the same worksheet. If an analysis tool changed IDs or rows, regenerate the file; SafeSet cannot match rows by position."
        case "entity_linkage": message = "A returned entity ID or its record linkage changed. Restore the original entity IDs."
        case "protected_value": message = "A protected source value changed in the returned workbook. Restore the original protected values."
        case "result_text": message = "A new result cell is blank, too long or contains unsupported text. Use short, safe categorical labels."
        case "source_text": message = "The original source matches the private bundle, but a cell contains text unsafe for a restored workbook. Use Locate unsafe source cells to see its worksheet and cell coordinate. Correct the source locally and create a new protected workbook and bundle before restoring."
        case "stale_review": message = "A workbook changed after the restoration review. Review the current files again before authorising restoration."
        case "result_approval": message = "Every new result field needs explicit approval before restoration."
        case "input_unavailable": message = "SafeSet could not read a selected local file. Check that it still exists and is a regular file."
        case "workbook_invalid": message = "A selected workbook is not a supported, safe .xlsx file. Save a clean .xlsx copy locally and try again."
        case "workbook_limit": message = "A selected workbook exceeds SafeSet's size, row or column limit."
        case "workbook_headings": message = "A selected worksheet has missing, repeated or unsupported headings."
        case "workbook_structure": message = "A selected worksheet has an unsupported row or cell structure."
        case "sheet_selection": message = "A selected worksheet is missing, hidden or repeated. Review the worksheet selections."
        case "sheet_schema": message = "Selected worksheets do not have identical headings. Check that every selected worksheet contains the same fields."
        case "table_schema": message = "Excel tables within a selected worksheet do not have identical headings. Check that each table contains the same fields."
        case "output_format": message = "Choose a new output filename ending in .xlsx."
        case "bundle_permissions": message = "The private bundle does not have the required local file permissions. Keep it outside the repository in private storage."
        case "document_invalid": message = "Choose a clean local .docx Word document."
        case "document_limit": message = "The Word document exceeds SafeSet's current DOCX limits."
        case "document_tracked_changes": message = "Resolve tracked changes before protecting or restoring this document."
        case "document_hidden_text": message = "The document contains hidden text. Remove or explicitly resolve it before continuing."
        case "document_active_content": message = "The document contains embedded or active content that SafeSet does not process."
        case "document_comments": message = "This document contains comments. Remove them during protection or resolve them locally first."
        case "document_split_identifier": message = "A protected identity spans multiple formatted Word runs. Simplify that text locally before protecting it."
        case "document_protection_incomplete": message = "SafeSet could not remove every protected identity from the DOCX."
        case "document_token_integrity": message = "The returned document changed or removed one or more SafeSet protection tokens."
        case "document_original_identifier": message = "The returned document contains an original protected identifier."
        case "local_io_failure": message = "A local file operation failed."
        case "response_limit": message = "The local review is too large to display."
        default: message = "The local request was invalid."
        }
        throw BridgeFailure.rejected(message)
    }
}
