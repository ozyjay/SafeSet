import Foundation

enum BridgeFailure: Error {
    case unavailable
    case rejected(String)
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
        let message: String
        switch code {
        case "safety_rejected": message = "SafeSet rejected this operation. Review the files and decisions."
        case "policy_configuration": message = "One or more field decisions are incomplete or incompatible. Check the identifier, classifications, approved categories and numeric settings on every selected worksheet."
        case "field_decisions": message = "Every field on every selected worksheet needs an explicit protection decision."
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
        case "shared_code_configuration": message = "Each shared obfuscation field must have the same heading and use Obfuscate values on at least two selected worksheets."
        case "bundle_authentication": message = "The private bundle could not be unlocked. Check that it belongs to this release and enter its passphrase again."
        case "bundle_unavailable": message = "SafeSet could not read the selected private bundle. Check its location and access permissions."
        case "bundle_incompatible": message = "The selected private bundle has an unsupported version or structure. Use the matching SafeSet release and bundle."
        case "source_mismatch": message = "The original source workbook does not match the private bundle. Select the exact source used to create this protected release."
        case "worksheet_coverage": message = "A required protected worksheet is missing or changed. Restore every original protected worksheet in the returned workbook."
        case "protected_schema": message = "A protected worksheet is missing an original heading or has renamed it. Keep every heading from the SafeSet protected copy exactly, including spelling and case. You may reorder columns or place new result columns anywhere."
        case "result_schema": message = "The returned workbook has an unexpected or conflicting result heading. Give each new result column a unique heading that does not reuse an original source heading."
        case "record_ids": message = "A returned record ID is malformed or repeated. Restore the original record IDs."
        case "record_coverage": message = "The returned record_id values do not match this bundle. Use its original SafeSet-protected copy and keep every record_id exactly once on the same worksheet. If an analysis tool changed IDs or rows, regenerate the file; SafeSet cannot match rows by position."
        case "entity_linkage": message = "A returned entity ID or its record linkage changed. Restore the original entity IDs."
        case "protected_value": message = "A protected source value changed in the returned workbook. Restore the original protected values."
        case "result_text": message = "A new result cell is blank, too long or contains unsupported text. Use short, safe categorical labels."
        case "source_text": message = "The original source matches the private bundle, but a cell contains text unsafe for a restored workbook. Use Locate unsafe source cells to see its worksheet and cell coordinate. Correct the source locally and create a new protected release and bundle before restoring."
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
