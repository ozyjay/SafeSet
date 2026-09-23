import AppKit
import Combine
import Foundation
import SwiftUI
import UniformTypeIdentifiers

let actionOptions: [(String, String)] = [
    ("Remove", "drop"), ("Replace with random record ID", "pseudonymise"),
    ("Obfuscate values", "code"), ("Keep", "keep"),
    ("Group into ranges", "bin"), ("Keep exact number", "keep_numeric")
]
private let classOptions: [(String, String)] = [
    ("Direct identifier", "direct_identifier"), ("Quasi-identifier", "quasi_identifier"),
    ("Analytical attribute", "analytical_attribute"), ("Free text", "free_text"),
    ("Unknown", "unknown"), ("Existing pseudonym", "pseudonymous_identifier")
]

let restorationAnalysisGuidance = "Ask the analysis tool to preserve every original worksheet, row, heading, record_id, entity_id and protected value exactly. It may add short result columns or separate analysis worksheets instead of changing fields such as campus."
let restorationResultExample = "For result columns, give every row a short value such as Campus mismatch or No change; blank result cells are not supported. Added worksheets may contain blank cells and formulas with saved results. SafeSet does not calculate or preserve formulas: after approval, it copies their saved results into new static tables. Formatting and drawings are not preserved."

private struct AppTextScaleKey: EnvironmentKey {
    static let defaultValue = 1.0
}

private extension EnvironmentValues {
    var appTextScale: Double {
        get { self[AppTextScaleKey.self] }
        set { self[AppTextScaleKey.self] = newValue }
    }
}

private struct AppFont: ViewModifier {
    @Environment(\.appTextScale) private var scale
    let size: Double
    var weight: Font.Weight = .regular
    var design: Font.Design = .default

    func body(content: Content) -> some View {
        content.font(.system(size: size * scale, weight: weight, design: design))
    }
}

private extension View {
    func appFont(_ size: Double, weight: Font.Weight = .regular,
                 design: Font.Design = .default) -> some View {
        modifier(AppFont(size: size, weight: weight, design: design))
    }
}

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
        case "analysis_sheet": message = "An added analysis worksheet is not a safe static table. Remove formulas, unsafe text, invalid headings or unsupported worksheet content, then try again."
        case "analysis_sheet_approval": message = "Every added analysis worksheet must be explicitly approved before restoration."
        case "formula_result": message = "A source formula has no saved value. Recalculate and save the workbook locally, then try again."
        case "hidden_data": message = "A selected data range contains hidden rows or columns. Unhide them or select a clean table."
        case "merged_data": message = "A selected data range contains merged cells, which SafeSet cannot process safely."
        case "active_content": message = "The workbook contains unsupported active or externally linked content."
        case "cell_features": message = "A selected data range contains unsupported comments or hyperlinks."
        case "cell_type": message = "A selected worksheet contains an unsupported cell type."
        case "destination_exists": message = "The selected output or bundle already exists. Choose a new filename."
        case "output_directory": message = "The selected output directory does not exist."
        case "repository_destination": message = "Operational data cannot be written inside a source-code repository."
        case "destination_separation": message = "The protected workbook and private bundle must use separate directories."
        case "shared_code_configuration": message = "Each shared obfuscation field must have the same heading and use Obfuscate values on at least two selected worksheets."
        case "local_io_failure": message = "A local file operation failed."
        case "response_limit": message = "The local review is too large to display."
        default: message = "The local request was invalid."
        }
        throw BridgeFailure.rejected(message)
    }
}

struct FieldDraft: Identifiable, Equatable {
    let id: String
    var type = ""
    var cardinality = 0
    var blankCount = 0
    var hint = ""
    var flags: [String] = []
    var action = ""
    var classification = ""
    var allowedValues: [String] = []
    var binsText = ""
    var lower = ""
    var upper = ""

    func payload() -> [String: Any] {
        let bins: [[Double]] = binsText.split(separator: "\n").compactMap { line in
            let parts = line.split(separator: ",", omittingEmptySubsequences: false)
            guard parts.count == 2,
                  let first = Double(parts[0].trimmingCharacters(in: .whitespaces)),
                  let second = Double(parts[1].trimmingCharacters(in: .whitespaces)) else { return nil }
            return [first, second]
        }
        let bounds: Any = (Double(lower) != nil && Double(upper) != nil)
            ? [Double(lower)!, Double(upper)!] : NSNull()
        return [
            "action": action, "classification": classification, "allowed_values": allowedValues,
            "bins": bins, "bounds": bounds
        ]
    }
}

struct CategorySheet: Identifiable {
    let id = UUID()
    let field: String
    let sheets: [String]
    let action: String
    let values: [String]
    let valuesBySheet: [String: [String]]
    let blankCount: Int
}

struct ConsolidatedField: Identifiable {
    let id: String
    let sheets: [String]
    let draft: FieldDraft
    let metadata: String
}

@MainActor final class AppModel: ObservableObject {
    private static let recentRestoreBundleKey = "recentRestoreBundlePath"
    enum Page: String { case home, protect, restore, advanced, help }
    @Published var page: Page = .home
    @Published var busy = false
    @Published var alert = ""
    @Published var source = ""
    @Published var sourceSheets: [String] = []
    @Published var sourceSheet = ""
    @Published var selectedSourceSheets: Set<String> = []
    @Published var fieldsBySheet: [String: [FieldDraft]] = [:]
    @Published var fields: [FieldDraft] = []
    @Published var sharedCodeFields: Set<String> = []
    @Published var threshold = "2"
    @Published var validationProfile = "strict"
    @Published var protectedOutput = ""
    @Published var bundleOutput = ""
    @Published var protectionReview: [String: Any]?
    @Published var categorySheet: CategorySheet?
    @Published var returned = ""
    @Published var returnedSheets: [String] = []
    @Published var returnedSheet = ""
    @Published var selectedReturnedSheets: Set<String> = []
    @Published var original = ""
    @Published var originalSheets: [String] = []
    @Published var originalSheet = ""
    @Published var selectedOriginalSheets: Set<String> = []
    @Published var restoreBundle = ""
    @Published var restoredOutput = ""
    @Published var restorationReview: [String: Any]?
    @Published var approvedResults: Set<String> = []
    @Published var approvedSheets: Set<String> = []
    @Published var relationalRestore = false
    @Published var legacyPolicy = ""
    @Published var legacyMap = ""
    @Published var legacyOutput = ""
    @Published var legacyReturned = ""
    @Published var legacyResultColumns: [String] = []
    @Published var legacyApproved: Set<String> = []
    @Published var legacyReview: [String: Any]?
    private var bridge: BackendBridge?
    private let preferences: UserDefaults
    private let worker = DispatchQueue(label: "org.ozyjay.SafeSet.bridge", qos: .userInitiated)

    var orderedReturnedRestoreSheets: [String] {
        returnedSheets.filter { selectedReturnedSheets.contains($0) }
    }

    var orderedOriginalRestoreSheets: [String] {
        originalSheets.filter { selectedOriginalSheets.contains($0) }
    }

    var orderedSelectedSourceSheets: [String] {
        sourceSheets.filter { selectedSourceSheets.contains($0) }
    }

    var consolidatedFields: [ConsolidatedField] {
        var headings: [String] = []
        var occurrences: [String: [(String, FieldDraft)]] = [:]
        for sheet in orderedSelectedSourceSheets {
            for field in fieldsBySheet[sheet] ?? [] {
                if occurrences[field.id] == nil { headings.append(field.id) }
                occurrences[field.id, default: []].append((sheet, field))
            }
        }
        return headings.compactMap { heading in
            guard let matches = occurrences[heading], var draft = matches.first?.1 else { return nil }
            let types = Set(matches.map { $0.1.type })
            let cardinalities = matches.map { $0.1.cardinality }
            let hints = Set(matches.map { $0.1.hint })
            draft.type = types.count == 1 ? (types.first ?? "") : "mixed types"
            draft.cardinality = cardinalities.max() ?? 0
            draft.blankCount = matches.reduce(0) { $0 + $1.1.blankCount }
            draft.hint = hints.count == 1 ? (hints.first ?? "") : "mixed — review carefully"
            draft.flags = Array(Set(matches.flatMap { $0.1.flags })).sorted()
            draft.allowedValues = matches.allSatisfy { !$0.1.allowedValues.isEmpty }
                ? Array(Set(matches.flatMap { $0.1.allowedValues })).sorted()
                : []
            let metadata: String
            if matches.count == 1 {
                metadata = "\(draft.type) · \(draft.cardinality) values"
            } else if Set(cardinalities).count == 1 {
                metadata = "\(matches.count) worksheets · \(draft.type) · \(draft.cardinality) values per sheet"
            } else {
                metadata = "\(matches.count) worksheets · \(draft.type) · \(cardinalities.min() ?? 0)–\(cardinalities.max() ?? 0) values per sheet"
            }
            return ConsolidatedField(
                id: heading,
                sheets: matches.map(\.0),
                draft: draft,
                metadata: metadata
            )
        }
    }

    func decisionProblem(_ configured: [FieldDraft]) -> String? {
        if configured.isEmpty { return "Inspect every selected worksheet before review." }
        if configured.filter({ $0.action == "pseudonymise" }).count != 1 {
            return "Each selected worksheet must replace exactly one direct identifier."
        }
        for field in configured {
            if field.action.isEmpty {
                return "Choose an action for every field in every selected worksheet."
            }
            if field.action != "drop" && field.classification.isEmpty {
                return "Classify every field that is kept, transformed or replaced."
            }
            if field.action == "pseudonymise" && field.classification != "direct_identifier" {
                return "The replaced source identifier must be classified as a direct identifier."
            }
            if ["keep", "code", "bin", "keep_numeric"].contains(field.action)
                && !["quasi_identifier", "analytical_attribute"].contains(field.classification) {
                return "Retained and transformed fields must be quasi-identifiers or analytical attributes."
            }
            if ["keep", "code"].contains(field.action) && field.allowedValues.isEmpty {
                return "Review and approve the source-value list for every kept or obfuscated field."
            }
            if ["keep", "code"].contains(field.action) && field.blankCount > 0 {
                return "Remove blank categorical cells or drop the affected field before protection."
            }
            if field.action == "bin" {
                let validPairs = field.binsText.split(separator: "\n").filter { line in
                    let parts = line.split(separator: ",", omittingEmptySubsequences: false)
                    return parts.count == 2
                        && Double(parts[0].trimmingCharacters(in: .whitespaces)) != nil
                        && Double(parts[1].trimmingCharacters(in: .whitespaces)) != nil
                }
                if validPairs.count < 2 {
                    return "Enter at least two valid lower,upper ranges for every grouped field."
                }
            }
            if field.action == "keep_numeric" {
                guard let lower = Double(field.lower), let upper = Double(field.upper),
                      lower >= 0, lower < upper else {
                    return "Enter valid bounds for every exact numeric field."
                }
            }
        }
        return nil
    }

    var canPrepareProtection: Bool {
        if selectedSourceSheets.isEmpty {
            return decisionProblem(fields) == nil
        }
        return selectedSourceSheets.allSatisfy { sheet in
            let configured = sheet == sourceSheet ? fields : (fieldsBySheet[sheet] ?? [])
            return decisionProblem(configured) == nil
        }
    }

    var sharedCodeCandidates: [String] {
        var counts: [String: Int] = [:]
        for sheet in selectedSourceSheets {
            let configured = sheet == sourceSheet ? fields : (fieldsBySheet[sheet] ?? [])
            for field in configured where field.action == "code" {
                counts[field.id, default: 0] += 1
            }
        }
        return counts.filter { $0.value >= 2 }.map(\.key).sorted()
    }

    var canApproveRestoration: Bool {
        guard let review = restorationReview, review["review_id"] is String else { return false }
        let sheets = Set(review["new_sheets"] as? [String] ?? [])
        guard sheets == approvedSheets else { return false }
        if relationalRestore, let groups = review["new_columns"] as? [String: [String]] {
            let names = Set(groups.flatMap { sheet, columns in
                columns.map { "\(sheet)::\($0)" }
            })
            return names == approvedResults
        }
        guard let names = review["new_columns"] as? [String] else { return false }
        return Set(names) == approvedResults
    }

    init(preferences: UserDefaults = .standard) {
        self.preferences = preferences
        if let remembered = preferences.string(forKey: Self.recentRestoreBundleKey),
           Self.isUsableRestoreBundlePath(remembered) {
            restoreBundle = remembered
        } else {
            preferences.removeObject(forKey: Self.recentRestoreBundleKey)
        }
        do { bridge = try BackendBridge() }
        catch { alert = "The bundled SafeSet engine could not start." }
    }

    private static func isUsableRestoreBundlePath(_ path: String) -> Bool {
        guard URL(fileURLWithPath: path).pathExtension.lowercased() == "enc" else { return false }
        var isDirectory: ObjCBool = false
        return FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory)
            && !isDirectory.boolValue
    }

    func rememberRestoreBundle(_ path: String) {
        guard Self.isUsableRestoreBundlePath(path) else { return }
        restoreBundle = path
        preferences.set(path, forKey: Self.recentRestoreBundleKey)
    }

    func forgetRestoreBundle() {
        restoreBundle = ""
        preferences.removeObject(forKey: Self.recentRestoreBundleKey)
        invalidate()
    }

    func send(_ command: String, _ payload: [String: Any],
              completion: @escaping ([String: Any]) -> Void) {
        guard let bridge else { alert = "The bundled SafeSet engine is unavailable."; return }
        busy = true
        worker.async {
            do {
                let result = try bridge.request(command, payload)
                DispatchQueue.main.async { self.busy = false; completion(result) }
            } catch {
                let message: String
                if case BridgeFailure.rejected(let text) = error { message = text }
                else { message = "The bundled SafeSet engine is unavailable." }
                DispatchQueue.main.async { self.busy = false; self.alert = message }
            }
        }
    }

    func invalidate() {
        protectionReview = nil
        restorationReview = nil
        legacyReview = nil
    }

    func cancelReview() {
        invalidate()
        send("cancel", [:]) { _ in }
    }

    func chooseSource(_ url: URL) {
        source = url.path; fields = []; fieldsBySheet = [:]; sharedCodeFields = []
        selectedSourceSheets = []; invalidate()
        send("list_sheets", ["path": source]) { result in
            self.sourceSheets = result["sheets"] as? [String] ?? []
            self.sourceSheet = self.sourceSheets.count == 1 ? self.sourceSheets[0] : ""
            self.selectedSourceSheets = Set(self.sourceSheet.isEmpty ? [] : [self.sourceSheet])
            if !self.sourceSheet.isEmpty { self.inspect() }
        }
    }

    func toggleSourceSheet(_ sheet: String, selected: Bool) {
        if !sourceSheet.isEmpty { fieldsBySheet[sourceSheet] = fields }
        if selected {
            selectedSourceSheets.insert(sheet)
        } else {
            selectedSourceSheets.remove(sheet)
            fieldsBySheet.removeValue(forKey: sheet)
            if sourceSheet == sheet {
                sourceSheet = ""
                fields = []
            }
        }
        if selected && sourceSheet.isEmpty {
            selectSourceSheet(sheet)
        } else if selected && fieldsBySheet[sheet] == nil {
            inspect(sheet: sheet)
        } else if sourceSheet.isEmpty, let next = orderedSelectedSourceSheets.first {
            selectSourceSheet(next)
        }
        invalidate()
    }

    func selectSourceSheet(_ sheet: String) {
        if !sourceSheet.isEmpty { fieldsBySheet[sourceSheet] = fields }
        sourceSheet = sheet
        guard !sheet.isEmpty else { fields = []; return }
        if let saved = fieldsBySheet[sheet] { fields = saved }
        else { fields = []; inspect() }
    }

    func inspect() {
        guard !source.isEmpty, !sourceSheet.isEmpty else { return }
        inspect(sheet: sourceSheet)
    }

    func inspect(sheet inspectedSheet: String) {
        guard !source.isEmpty, !inspectedSheet.isEmpty else { return }
        invalidate()
        send("inspect", ["source": source, "sheet": inspectedSheet]) { result in
            let data = result["columns"] as? [[String: Any]] ?? []
            var inspectedFields = data.map { item in
                var field = FieldDraft(id: item["column"] as? String ?? "")
                field.type = item["type"] as? String ?? ""
                field.cardinality = item["cardinality"] as? Int ?? 0
                field.blankCount = item["blank_count"] as? Int ?? 0
                field.hint = item["inferred_classification"] as? String ?? ""
                field.flags = item["flags"] as? [String] ?? []
                return field
            }
            for index in inspectedFields.indices {
                guard let existing = self.fieldsBySheet
                    .filter({ $0.key != inspectedSheet })
                    .compactMap({ $0.value.first(where: { $0.id == inspectedFields[index].id }) })
                    .first else { continue }
                inspectedFields[index].action = existing.action
                inspectedFields[index].classification = existing.classification
                inspectedFields[index].binsText = existing.binsText
                inspectedFields[index].lower = existing.lower
                inspectedFields[index].upper = existing.upper
                if !existing.allowedValues.isEmpty {
                    for sheet in self.selectedSourceSheets {
                        guard var sheetFields = self.fieldsBySheet[sheet],
                              let match = sheetFields.firstIndex(where: {
                                  $0.id == inspectedFields[index].id
                              }) else { continue }
                        sheetFields[match].allowedValues = []
                        self.fieldsBySheet[sheet] = sheetFields
                    }
                }
            }
            self.fieldsBySheet[inspectedSheet] = inspectedFields
            if self.sourceSheet == inspectedSheet { self.fields = inspectedFields }
        }
    }

    func updateConsolidatedField(_ heading: String, with decision: FieldDraft) {
        for sheet in selectedSourceSheets {
            guard var sheetFields = fieldsBySheet[sheet],
                  let index = sheetFields.firstIndex(where: { $0.id == heading }) else { continue }
            let actionChanged = sheetFields[index].action != decision.action
            sheetFields[index].action = decision.action
            sheetFields[index].classification = decision.classification
            if actionChanged { sheetFields[index].allowedValues = [] }
            sheetFields[index].binsText = decision.binsText
            sheetFields[index].lower = decision.lower
            sheetFields[index].upper = decision.upper
            fieldsBySheet[sheet] = sheetFields
            if sheet == sourceSheet { fields = sheetFields }
        }
        sharedCodeFields.formIntersection(sharedCodeCandidates)
        invalidate()
    }

    func categories(for field: String, sheets: [String]) {
        invalidate()
        let orderedSheets = orderedSelectedSourceSheets.filter { sheets.contains($0) }
        let action = consolidatedFields.first(where: { $0.id == field })?.draft.action ?? ""
        func collect(_ index: Int, valuesBySheet: [String: [String]], blankCount: Int) {
            guard index < orderedSheets.count else {
                let values = Set(valuesBySheet.values.flatMap { $0 })
                self.categorySheet = CategorySheet(
                    field: field,
                    sheets: orderedSheets,
                    action: action,
                    values: values.sorted(),
                    valuesBySheet: valuesBySheet,
                    blankCount: blankCount
                )
                return
            }
            let sheet = orderedSheets[index]
            send("categories", ["source": source, "sheet": sheet, "column": field]) { result in
                var collected = valuesBySheet
                collected[sheet] = result["values"] as? [String] ?? []
                collect(
                    index + 1,
                    valuesBySheet: collected,
                    blankCount: blankCount + (result["blank_count"] as? Int ?? 0)
                )
            }
        }
        collect(0, valuesBySheet: [:], blankCount: 0)
    }

    func approveCategories(_ category: CategorySheet) {
        guard category.blankCount == 0 else {
            alert = "Blank categorical cells cannot be approved. Remove them or drop this field."
            return
        }
        for sheet in category.sheets {
            guard var sheetFields = fieldsBySheet[sheet],
                  let index = sheetFields.firstIndex(where: { $0.id == category.field }) else { continue }
            sheetFields[index].allowedValues = category.valuesBySheet[sheet] ?? []
            fieldsBySheet[sheet] = sheetFields
            if sheet == sourceSheet { fields = sheetFields }
        }
        categorySheet = nil
        invalidate()
    }

    func draftPayload() -> [String: Any] {
        Dictionary(uniqueKeysWithValues: fields.map { ($0.id, $0.payload()) })
    }

    func prepareProtection() {
        fieldsBySheet[sourceSheet] = fields
        sharedCodeFields.formIntersection(sharedCodeCandidates)
        for sheet in selectedSourceSheets.sorted() {
            let configured = sheet == sourceSheet ? fields : (fieldsBySheet[sheet] ?? [])
            if let problem = decisionProblem(configured) { alert = problem; return }
        }
        guard canPrepareProtection else { alert = "Complete every selected worksheet."; return }
        let output = protectedOutput.isEmpty
            ? (source as NSString).deletingPathExtension + "-protected.xlsx" : protectedOutput
        let relational = selectedSourceSheets.count > 1
        var payload: [String: Any]
        if relational {
            let drafts = Dictionary(uniqueKeysWithValues: selectedSourceSheets.map { sheet in
                (sheet, Dictionary(uniqueKeysWithValues:
                    (fieldsBySheet[sheet] ?? []).map { ($0.id, $0.payload()) }))
            })
            payload = [
                "source": source, "sheets": selectedSourceSheets.sorted(), "output": output,
                "drafts": drafts, "threshold": threshold,
                "validation_profile": validationProfile,
                "shared_code_fields": sharedCodeFields.sorted()
            ]
        } else {
            payload = [
                "source": source, "sheet": sourceSheet, "output": output,
                "drafts": draftPayload(), "threshold": threshold,
                "validation_profile": validationProfile
            ]
        }
        payload["bundle"] = bundleOutput.isEmpty ? NSNull() : bundleOutput
        send(relational ? "prepare_relational_protection" : "prepare_protection", payload) {
            self.protectionReview = $0
        }
    }

    func approveProtection(passphrase: String) {
        guard let review = protectionReview,
              let token = review["review_id"] as? String else { return }
        let relational = review["worksheets"] != nil
        send(relational ? "approve_relational_protection" : "approve_protection",
             ["review_id": token, "passphrase": passphrase]) { _ in
            self.original = self.source
            self.originalSheets = self.sourceSheets
            self.originalSheet = self.sourceSheet
            self.selectedOriginalSheets = self.selectedSourceSheets
            self.rememberRestoreBundle(review["bundle"] as? String ?? "")
            self.protectionReview = nil
            self.alert = "Protected workbook and private restoration bundle created."
            self.page = .home
        }
    }

    func chooseRestoreFile(_ url: URL, sourceFile: Bool) {
        invalidate()
        let path = url.path
        if sourceFile { original = path } else { returned = path }
        send("list_sheets", ["path": path]) { result in
            let sheets = result["sheets"] as? [String] ?? []
            if sourceFile {
                self.originalSheets = sheets
                self.originalSheet = sheets.count == 1 ? sheets[0] : ""
                self.selectedOriginalSheets = Set(sheets.count == 1 ? sheets : [])
            } else {
                self.returnedSheets = sheets
                self.returnedSheet = sheets.count == 1 ? sheets[0] : ""
                self.selectedReturnedSheets = Set(
                    self.relationalRestore || sheets.count == 1 ? sheets : []
                )
            }
        }
    }

    func prepareRestoration(passphrase: String) {
        guard !returned.isEmpty, !original.isEmpty, !restoreBundle.isEmpty,
              !orderedReturnedRestoreSheets.isEmpty,
              relationalRestore || !orderedOriginalRestoreSheets.isEmpty
        else {
            alert = "Choose both workbooks, their worksheets and the private bundle."; return
        }
        let output = restoredOutput.isEmpty
            ? (returned as NSString).deletingPathExtension + "-restored.xlsx" : restoredOutput
        let command = relationalRestore ? "prepare_relational_reconstruction" : "prepare_reconstruction"
        var payload: [String: Any] = [
            "returned": returned, "source": original, "bundle": restoreBundle,
            "output": output, "passphrase": passphrase
        ]
        if !relationalRestore {
            payload["returned_sheet"] = orderedReturnedRestoreSheets
            payload["source_sheet"] = orderedOriginalRestoreSheets
        } else {
            payload["selected_sheets"] = orderedReturnedRestoreSheets
        }
        send(command, payload) { result in
            self.restorationReview = result
            self.approvedResults = []
            self.approvedSheets = []
        }
    }

    func approveRestoration() {
        guard canApproveRestoration,
              let review = restorationReview,
              let token = review["review_id"] as? String else {
            alert = "Approve every new result field and added worksheet, or remove it from the returned workbook."
            return
        }
        let command: String
        let approved: Any
        if relationalRestore, let groups = review["new_columns"] as? [String: [String]] {
            command = "approve_relational_reconstruction"
            approved = groups
        } else {
            guard let names = review["new_columns"] as? [String] else { return }
            command = "approve_reconstruction"
            approved = names
        }
        send(command, [
            "review_id": token,
            "approved_results": approved,
            "approved_sheets": Array(approvedSheets).sorted()
        ]) { _ in
            self.restorationReview = nil
            self.alert = "A new locally reidentified workbook was created. Keep it private."
            self.page = .home
        }
    }

    func loadPolicy() {
        guard !source.isEmpty, !sourceSheet.isEmpty, !legacyPolicy.isEmpty else {
            alert = "Choose a source workbook, worksheet and policy."; return
        }
        send("load_policy", [
            "source": source, "sheet": sourceSheet, "policy": legacyPolicy
        ]) { result in
            let drafts = result["drafts"] as? [String: [String: Any]] ?? [:]
            for index in self.fields.indices {
                guard let draft = drafts[self.fields[index].id] else { continue }
                self.fields[index].action = draft["action"] as? String ?? ""
                self.fields[index].classification = draft["classification"] as? String ?? ""
                self.fields[index].allowedValues = draft["allowed_values"] as? [String] ?? []
                if let bins = draft["bins"] as? [[Double]] {
                    self.fields[index].binsText = bins.map { "\($0[0]),\($0[1])" }.joined(separator: "\n")
                }
                if let bounds = draft["bounds"] as? [Double], bounds.count == 2 {
                    self.fields[index].lower = String(bounds[0])
                    self.fields[index].upper = String(bounds[1])
                }
            }
            self.threshold = String(result["threshold"] as? Int ?? 2)
            self.invalidate()
            self.alert = "Policy choices loaded for review."
        }
    }

    func savePolicy(_ destination: String) {
        send("save_policy", [
            "source": source, "sheet": sourceSheet, "destination": destination,
            "drafts": draftPayload(), "threshold": threshold
        ]) { _ in self.alert = "A new private YAML policy was saved." }
    }

    func prepareLegacyExport() {
        guard !legacyPolicy.isEmpty, !legacyOutput.isEmpty else {
            alert = "Choose a policy and a new output location."; return
        }
        send("prepare_export", [
            "source": source, "sheet": sourceSheet, "policy": legacyPolicy,
            "output": legacyOutput, "map": legacyMap.isEmpty ? NSNull() : legacyMap
        ]) { self.legacyReview = $0 }
    }

    func approveLegacyExport(passphrase: String) {
        guard let token = legacyReview?["review_id"] as? String else { return }
        send("approve_export", ["review_id": token, "passphrase": passphrase]) { result in
            self.legacyMap = self.legacyReview?["map"] as? String ?? ""
            self.legacyReview = nil
            self.alert = result["created"] as? Bool == true
                ? "Legacy export and private map created." : "Export was not created."
        }
    }

    func inspectLegacyReturned() {
        guard !legacyReturned.isEmpty else { return }
        send("inspect_returned", ["path": legacyReturned, "sheet": NSNull()]) { result in
            self.legacyResultColumns = result["result_columns"] as? [String] ?? []
            self.legacyApproved = []
        }
    }

    func restoreLegacy(passphrase: String) {
        guard !legacyReturned.isEmpty, !legacyMap.isEmpty, !restoredOutput.isEmpty,
              Set(legacyResultColumns) == legacyApproved else {
            alert = "Approve all returned fields and choose a new output location."; return
        }
        send("restore_results", [
            "returned": legacyReturned, "sheet": NSNull(), "map": legacyMap,
            "output": restoredOutput, "results": legacyResultColumns,
            "passphrase": passphrase, "source": original.isEmpty ? NSNull() : original,
            "policy": legacyPolicy.isEmpty ? NSNull() : legacyPolicy,
            "source_sheet": originalSheet.isEmpty ? NSNull() : originalSheet
        ]) { _ in self.alert = "Legacy results restored locally. Keep the output private." }
    }
}

private func chooseOpen(extension suffix: String, completion: @escaping (URL?) -> Void) {
    let panel = NSOpenPanel()
    if let contentType = UTType(filenameExtension: suffix) {
        panel.allowedContentTypes = [contentType]
    }
    panel.canChooseDirectories = false
    panel.canChooseFiles = true
    panel.allowsMultipleSelection = false
    present(panel, completion: completion)
}

private func chooseSave(extension suffix: String, completion: @escaping (URL?) -> Void) {
    let panel = NSSavePanel()
    if let contentType = UTType(filenameExtension: suffix) {
        panel.allowedContentTypes = [contentType]
    }
    present(panel, completion: completion)
}

private func present(_ panel: NSSavePanel, completion: @escaping (URL?) -> Void) {
    let finish: (NSApplication.ModalResponse) -> Void = { response in
        completion(response == .OK ? panel.url : nil)
    }
    if let window = NSApp.keyWindow ?? NSApp.mainWindow {
        panel.beginSheetModal(for: window, completionHandler: finish)
    } else {
        panel.begin(completionHandler: finish)
    }
}

struct PathRow: View {
    @Environment(\.appTextScale) private var textScale
    let title: String
    @Binding var path: String
    let save: Bool
    let fileExtension: String
    var onChoose: ((URL) -> Void)? = nil

    var body: some View {
        HStack {
            Text(title).frame(width: 180 * textScale, alignment: .leading)
            TextField("Choose a local file", text: $path)
                .appFont(13)
                .textFieldStyle(.roundedBorder)
                .disabled(!save)
            Button("Choose…") {
                let selected: (URL?) -> Void = { url in
                    guard let url else { return }
                    path = url.path
                    onChoose?(url)
                }
                if save {
                    chooseSave(extension: fileExtension, completion: selected)
                } else {
                    chooseOpen(extension: fileExtension, completion: selected)
                }
            }
            .appFont(13)
        }
    }
}

struct FieldCard: View {
    @Binding var field: FieldDraft
    var scope: String? = nil
    var metadata: String? = nil
    let categories: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(field.id).appFont(13, weight: .semibold)
                Spacer()
                Text(metadata ?? "\(field.type) · \(field.cardinality) values")
                    .foregroundStyle(.secondary)
            }
            if let scope {
                Text(scope).appFont(12).foregroundStyle(.secondary)
            }
            if field.blankCount > 0 {
                Label(
                    "\(field.blankCount) blank or whitespace-only cells",
                    systemImage: "exclamationmark.triangle.fill"
                )
                .appFont(13)
                .foregroundStyle(.red)
            }
            HStack {
                Picker("Appearance", selection: $field.action) {
                    Text("Choose…").tag("")
                    ForEach(actionOptions, id: \.1) { item in Text(item.0).tag(item.1) }
                }
                .appFont(13)
                if field.action != "drop" {
                    Picker("Classification", selection: $field.classification) {
                        Text("Choose…").tag("")
                        ForEach(classOptions, id: \.1) { item in Text(item.0).tag(item.1) }
                    }
                    .appFont(13)
                }
            }
            if field.action == "keep" || field.action == "code" {
                VStack(alignment: .leading, spacing: 5) {
                    Text(field.action == "code"
                         ? "Review the distinct source values before SafeSet replaces each one with a fresh random code."
                         : "Review the distinct source values that will remain unchanged in the protected copy.")
                        .appFont(12)
                        .foregroundStyle(.secondary)
                    HStack {
                        Button("Review values found in this field…") { categories(field.id) }
                            .appFont(13)
                        Text("\(field.allowedValues.count) source values approved")
                        .foregroundStyle(.secondary)
                    }
                }
            }
            if field.action == "bin" {
                TextField("One lower,upper range per line", text: $field.binsText, axis: .vertical)
                    .appFont(13)
                    .lineLimit(2...5)
            }
            if field.action == "keep_numeric" {
                Text("Genuine blank cells remain blank and are included in the disclosure-risk checks.")
                    .appFont(12)
                    .foregroundStyle(.secondary)
                HStack {
                    TextField("Lower bound", text: $field.lower).appFont(13)
                    TextField("Upper bound", text: $field.upper).appFont(13)
                }
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("Decision details").appFont(11, weight: .semibold)
                Text("Suggested classification: \(field.hint.replacingOccurrences(of: "_", with: " "))")
                if field.action != "drop" && !field.flags.isEmpty {
                    Label("Warnings: \(field.flags.joined(separator: ", "))",
                          systemImage: "exclamationmark.triangle")
                        .appFont(13)
                        .foregroundStyle(.orange)
                }
            }
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 4)
        }
        .padding(14)
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 12))
    }
}

struct RootView: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.appTextScale) private var textScale

    var body: some View {
        NavigationSplitView {
            List(selection: Binding(
                get: { model.page }, set: { model.page = $0 ?? .home; model.invalidate() }
            )) {
                Label("Home", systemImage: "house").appFont(13).tag(AppModel.Page.home)
                Label("Protect workbook", systemImage: "lock.doc")
                    .appFont(13).tag(AppModel.Page.protect)
                Label("Restore workbook", systemImage: "lock.open")
                    .appFont(13).tag(AppModel.Page.restore)
                Label("Advanced", systemImage: "slider.horizontal.3")
                    .appFont(13).tag(AppModel.Page.advanced)
                Divider()
                Label("Help", systemImage: "questionmark.circle")
                    .appFont(13).tag(AppModel.Page.help)
            }
            .navigationTitle("SafeSet")
            .frame(minWidth: 190 * textScale)
            .navigationSplitViewColumnWidth(min: 190 * textScale,
                                            ideal: 220 * textScale)
        } detail: {
            Group {
                switch model.page {
                case .home: HomeView()
                case .protect: ProtectView()
                case .restore: RestoreView()
                case .advanced: AdvancedView()
                case .help: HelpView()
                }
            }
            .frame(minWidth: 680, minHeight: 540)
            .overlay { if model.busy { ProgressView().padding().background(.regularMaterial) } }
        }
        .font(.system(size: 13 * textScale))
        .alert("SafeSet", isPresented: Binding(
            get: { !model.alert.isEmpty }, set: { if !$0 { model.alert = "" } }
        )) { Button("OK") { model.alert = "" } } message: { Text(model.alert) }
        .onChange(of: model.fields) {
            if !model.sourceSheet.isEmpty { model.fieldsBySheet[model.sourceSheet] = model.fields }
            model.sharedCodeFields.formIntersection(model.sharedCodeCandidates)
            model.invalidate()
        }
        .onChange(of: model.source) { model.invalidate() }
        .onChange(of: model.protectedOutput) { model.invalidate() }
        .onChange(of: model.bundleOutput) { model.invalidate() }
        .onChange(of: model.threshold) { model.invalidate() }
        .onChange(of: model.validationProfile) { model.invalidate() }
        .onChange(of: model.sharedCodeFields) { model.invalidate() }
        .onChange(of: model.returned) { model.invalidate() }
        .onChange(of: model.returnedSheet) { model.invalidate() }
        .onChange(of: model.selectedReturnedSheets) { model.invalidate() }
        .onChange(of: model.original) { model.invalidate() }
        .onChange(of: model.originalSheet) { model.invalidate() }
        .onChange(of: model.selectedOriginalSheets) { model.invalidate() }
        .onChange(of: model.restoreBundle) { model.invalidate() }
        .onChange(of: model.restoredOutput) { model.invalidate() }
        .onChange(of: model.relationalRestore) {
            if model.relationalRestore {
                model.selectedReturnedSheets = Set(model.returnedSheets)
            }
            model.invalidate()
        }
        .onChange(of: model.legacyPolicy) { model.invalidate() }
        .onChange(of: model.legacyMap) { model.invalidate() }
        .onChange(of: model.legacyOutput) { model.invalidate() }
    }
}

struct HomeView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Text("Protect, work, restore").appFont(26, weight: .bold)
            Text("Create a protected working copy, analyse it, then reconstruct a new identifiable workbook locally.")
                .appFont(16).foregroundStyle(.secondary)
            HStack(spacing: 16) {
                Button { model.page = .protect } label: {
                    Label("Protect a workbook", systemImage: "lock.doc")
                        .appFont(13)
                        .frame(maxWidth: .infinity, minHeight: 100)
                }.buttonStyle(.borderedProminent)
                Button { model.page = .restore } label: {
                    Label("Restore a workbook", systemImage: "lock.open")
                        .appFont(13)
                        .frame(maxWidth: .infinity, minHeight: 100)
                }.buttonStyle(.bordered)
            }
            Text("Passing checks reduces some disclosure risks. It does not establish anonymity or recipient suitability.")
                .foregroundStyle(.secondary)
            Spacer()
        }
        .padding(28)
    }
}

struct HelpBlock: Identifiable {
    enum Kind {
        case heading(Int, String)
        case paragraph(String)
        case list(Bool, [String])
        case code(String)
        case table([String], [[String]])
    }

    let id = UUID()
    let kind: Kind
}

private func helpTableCells(_ line: String) -> [String] {
    line.trimmingCharacters(in: .whitespaces)
        .trimmingCharacters(in: CharacterSet(charactersIn: "|"))
        .split(separator: "|", omittingEmptySubsequences: false)
        .map { $0.trimmingCharacters(in: .whitespaces) }
}

private func helpOrderedItem(_ line: String) -> String? {
    let value = line.trimmingCharacters(in: .whitespaces)
    guard let dot = value.firstIndex(of: "."), dot != value.startIndex,
          value[..<dot].allSatisfy(\.isNumber) else { return nil }
    let remainder = value[value.index(after: dot)...]
    guard remainder.first == " " else { return nil }
    return remainder.trimmingCharacters(in: .whitespaces)
}

private func helpBulletItem(_ line: String) -> String? {
    let value = line.trimmingCharacters(in: .whitespaces)
    guard value.hasPrefix("- ") else { return nil }
    return String(value.dropFirst(2)).trimmingCharacters(in: .whitespaces)
}

func parseHelpMarkdown(_ markdown: String) -> [HelpBlock] {
    let lines = markdown.components(separatedBy: .newlines)
    var blocks: [HelpBlock] = []
    var index = 0

    func isBlockStart(_ line: String) -> Bool {
        let value = line.trimmingCharacters(in: .whitespaces)
        return value.hasPrefix("#") || value.hasPrefix("```") ||
            value.hasPrefix("|") || helpOrderedItem(value) != nil ||
            helpBulletItem(value) != nil
    }

    while index < lines.count {
        let trimmed = lines[index].trimmingCharacters(in: .whitespaces)
        if trimmed.isEmpty { index += 1; continue }

        if trimmed.hasPrefix("```") {
            index += 1
            var code: [String] = []
            while index < lines.count &&
                    !lines[index].trimmingCharacters(in: .whitespaces).hasPrefix("```") {
                code.append(lines[index]); index += 1
            }
            if index < lines.count { index += 1 }
            blocks.append(HelpBlock(kind: .code(code.joined(separator: "\n"))))
            continue
        }

        if trimmed.hasPrefix("#") {
            let level = min(trimmed.prefix(while: { $0 == "#" }).count, 3)
            let title = trimmed.dropFirst(level).trimmingCharacters(in: .whitespaces)
            blocks.append(HelpBlock(kind: .heading(level, title)))
            index += 1
            continue
        }

        if trimmed.hasPrefix("|"), index + 1 < lines.count,
           lines[index + 1].contains("---") {
            let headers = helpTableCells(trimmed)
            index += 2
            var rows: [[String]] = []
            while index < lines.count &&
                    lines[index].trimmingCharacters(in: .whitespaces).hasPrefix("|") {
                rows.append(helpTableCells(lines[index])); index += 1
            }
            blocks.append(HelpBlock(kind: .table(headers, rows)))
            continue
        }

        if let first = helpOrderedItem(trimmed) {
            var items = [first]
            index += 1
            while index < lines.count {
                if let item = helpOrderedItem(lines[index]) {
                    items.append(item); index += 1
                } else if !lines[index].trimmingCharacters(in: .whitespaces).isEmpty &&
                            !isBlockStart(lines[index]) {
                    items[items.count - 1] += " " + lines[index].trimmingCharacters(in: .whitespaces)
                    index += 1
                } else { break }
            }
            blocks.append(HelpBlock(kind: .list(true, items)))
            continue
        }

        if let first = helpBulletItem(trimmed) {
            var items = [first]
            index += 1
            while index < lines.count {
                if let item = helpBulletItem(lines[index]) {
                    items.append(item); index += 1
                } else if !lines[index].trimmingCharacters(in: .whitespaces).isEmpty &&
                            !isBlockStart(lines[index]) {
                    items[items.count - 1] += " " + lines[index].trimmingCharacters(in: .whitespaces)
                    index += 1
                } else { break }
            }
            blocks.append(HelpBlock(kind: .list(false, items)))
            continue
        }

        var paragraph = [trimmed]
        index += 1
        while index < lines.count &&
                !lines[index].trimmingCharacters(in: .whitespaces).isEmpty &&
                !isBlockStart(lines[index]) {
            paragraph.append(lines[index].trimmingCharacters(in: .whitespaces)); index += 1
        }
        blocks.append(HelpBlock(kind: .paragraph(paragraph.joined(separator: " "))))
    }
    return blocks
}

private func helpInline(_ markdown: String) -> AttributedString {
    let options = AttributedString.MarkdownParsingOptions(
        interpretedSyntax: .inlineOnlyPreservingWhitespace
    )
    return (try? AttributedString(markdown: markdown, options: options)) ?? AttributedString(markdown)
}

struct HelpView: View {
    @Environment(\.appTextScale) private var textScale
    private let blocks: [HelpBlock]

    private var sections: [HelpBlock] {
        blocks.filter {
            if case .heading(2, _) = $0.kind { return true }
            return false
        }
    }

    init(bundle: Bundle = .main) {
        let fallback = "The SafeSet guide is unavailable in this build. See `HOWTO.md` in the project or rebuild the app with `scripts/build-macos-app.ps1`."
        let markdown: String
        if let url = bundle.url(forResource: "HOWTO", withExtension: "md"),
           let bundled = try? String(contentsOf: url, encoding: .utf8) {
            markdown = bundled
        } else { markdown = fallback }
        blocks = parseHelpMarkdown(markdown)
    }

    @ViewBuilder private func render(_ block: HelpBlock) -> some View {
        switch block.kind {
        case .heading(let level, let text):
            Text(helpInline(text))
                .appFont(level == 1 ? 28 : level == 2 ? 21 : 17,
                         weight: level == 3 ? .semibold : .bold)
                .padding(.top, level == 1 ? 0 : level == 2 ? 16 : 8)
        case .paragraph(let text):
            Text(helpInline(text))
                .appFont(15)
                .lineSpacing(5 * textScale)
        case .list(let ordered, let items):
            VStack(alignment: .leading, spacing: 12 * textScale) {
                ForEach(Array(items.enumerated()), id: \.offset) { offset, item in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(ordered ? "\(offset + 1)." : "•")
                            .appFont(15, weight: .semibold)
                            .frame(width: 28 * textScale, alignment: .trailing)
                            .foregroundStyle(.secondary)
                        Text(helpInline(item))
                            .appFont(15)
                            .lineSpacing(5 * textScale)
                    }
                }
            }
        case .code(let code):
            ScrollView(.horizontal) {
                Text(verbatim: code)
                    .appFont(14, design: .monospaced)
                    .textSelection(.enabled)
                    .padding(12)
            }
            .background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
        case .table(let headers, let rows):
            ScrollView(.horizontal) {
                Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 10) {
                    GridRow {
                        ForEach(Array(headers.enumerated()), id: \.offset) { _, cell in
                            Text(helpInline(cell)).appFont(15, weight: .semibold)
                        }
                    }
                    Divider()
                    ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                        GridRow {
                            ForEach(Array(row.enumerated()), id: \.offset) { _, cell in
                                Text(helpInline(cell))
                                    .appFont(15)
                                    .frame(maxWidth: 300, alignment: .leading)
                            }
                        }
                    }
                }
                .padding(12)
            }
            .background(.quaternary.opacity(0.45), in: RoundedRectangle(cornerRadius: 8))
        }
    }

    var body: some View {
        ScrollViewReader { reader in
            ScrollView {
                VStack(alignment: .leading, spacing: 20 * textScale) {
                    if let first = blocks.first { render(first) }
                    Text("Jump to a section")
                        .appFont(13, weight: .semibold)
                        .foregroundStyle(.secondary)
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 280 * textScale),
                                                   alignment: .leading)],
                              alignment: .leading, spacing: 8) {
                        ForEach(sections) { section in
                            if case .heading(_, let title) = section.kind {
                                Button(title) {
                                    withAnimation { reader.scrollTo(section.id, anchor: .top) }
                                }
                                .appFont(13)
                                .buttonStyle(.bordered)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }
                    }
                    Divider()
                    ForEach(Array(blocks.dropFirst())) { block in
                        render(block).id(block.id)
                    }
                }
                .frame(maxWidth: 680, alignment: .leading)
                .padding(32)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .navigationTitle("Help")
    }
}

struct ProtectView: View {
    @EnvironmentObject var model: AppModel
    @State private var passphrase = ""
    @State private var confirmation = ""
    @State private var showApproval = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Protect a workbook").appFont(26, weight: .bold)
                PathRow(title: "Original workbook", path: $model.source, save: false,
                        fileExtension: "xlsx") { model.chooseSource($0) }
                if model.sourceSheets.count > 1 {
                    GroupBox("Related worksheets") {
                        VStack(alignment: .leading) {
                            Text("Select every worksheet that belongs to this linked release.")
                                .foregroundStyle(.secondary)
                            ForEach(model.sourceSheets, id: \.self) { sheet in
                                Toggle(sheet, isOn: Binding(
                                    get: { model.selectedSourceSheets.contains(sheet) },
                                    set: { model.toggleSourceSheet(sheet, selected: $0) }
                                ))
                                .appFont(13)
                            }
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                if !model.consolidatedFields.isEmpty {
                    Text("Review fields across selected worksheets").appFont(18, weight: .bold)
                    Text("A repeated heading appears once and its decision applies to every listed worksheet. Sheet-specific headings remain separate. Classify fields you keep or replace; removed fields need no classification.")
                        .foregroundStyle(.secondary)
                    ForEach(model.consolidatedFields) { item in
                        FieldCard(
                            field: Binding(
                                get: {
                                    model.consolidatedFields.first(where: { $0.id == item.id })?.draft
                                        ?? item.draft
                                },
                                set: { model.updateConsolidatedField(item.id, with: $0) }
                            ),
                            scope: item.sheets.count == model.selectedSourceSheets.count
                                ? "All selected worksheets"
                                : "Worksheet\(item.sheets.count == 1 ? "" : "s"): \(item.sheets.joined(separator: ", "))",
                            metadata: item.metadata
                        ) { model.categories(for: $0, sheets: item.sheets) }
                    }
                    HStack {
                        Text("Minimum group size")
                        TextField("2", text: $model.threshold)
                            .appFont(13).frame(width: 75)
                    }
                    Picker("Validation profile", selection: $model.validationProfile) {
                        Text("Strict — rare groups block export").tag("strict")
                        Text("Controlled pseudonymisation — rare groups warn")
                            .tag("controlled_pseudonymisation")
                    }
                    .appFont(13)
                    Text(model.validationProfile == "strict"
                         ? "Strict mode blocks small marginal and joint groups."
                         : "Controlled pseudonymisation keeps structural checks mandatory and requires explicit review of rare-group and linkage warnings.")
                        .foregroundStyle(.secondary)
                    if model.selectedSourceSheets.count > 1,
                       !model.sharedCodeCandidates.isEmpty {
                        GroupBox("Shared obfuscation") {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Confirm which same-named fields represent the same category domain. Matching source values will receive the same random code across selected worksheets.")
                                    .foregroundStyle(.secondary)
                                ForEach(model.sharedCodeCandidates, id: \.self) { field in
                                    Toggle(field, isOn: Binding(
                                        get: { model.sharedCodeFields.contains(field) },
                                        set: { selected in
                                            if selected { model.sharedCodeFields.insert(field) }
                                            else { model.sharedCodeFields.remove(field) }
                                        }
                                    ))
                                    .appFont(13)
                                }
                                Text("This deliberately exposes cross-worksheet category equality and frequency. Unconfirmed fields use independent codebooks, even when their headings match.")
                                    .foregroundStyle(.orange)
                            }.frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    PathRow(title: "Protected workbook", path: $model.protectedOutput,
                            save: true, fileExtension: "xlsx")
                    DisclosureGroup("Advanced settings") {
                        PathRow(title: "Private bundle location", path: $model.bundleOutput,
                                save: true, fileExtension: "enc")
                    }
                    Button("Review protection") { model.prepareProtection() }
                        .appFont(13)
                        .buttonStyle(.borderedProminent)
                }
                if let review = model.protectionReview,
                   let validation = review["validation"] as? [String: Any] {
                    Divider()
                    Text("Final review").appFont(18, weight: .bold)
                    if let worksheets = review["worksheets"] as? Int {
                        Text("\(review["rows"] as? Int ?? 0) records · \(worksheets) related worksheets · \(review["entities"] as? Int ?? 0) linked entities")
                        if let shared = review["shared_code_fields"] as? [String], !shared.isEmpty {
                            Text("Shared obfuscation codebooks: \(shared.joined(separator: ", "))")
                        }
                    } else {
                        Text("\(review["rows"] as? Int ?? 0) records · \(review["removed"] as? Int ?? 0) removed · 1 identifier replaced · \(review["obfuscated"] as? Int ?? 0) obfuscated · \(review["retained"] as? Int ?? 0) retained")
                    }
                    Text("Protected copy: \(review["output"] as? String ?? "")")
                    Text("Private restoration bundle: \(review["bundle"] as? String ?? "")")
                    Text((validation["passed"] as? Bool == true) ? "Mandatory validation passed" : "Mandatory validation blocked")
                        .foregroundStyle((validation["passed"] as? Bool == true) ? .green : .red)
                    if let warnings = validation["warnings"] as? [String] {
                        ForEach(warnings, id: \.self) { Text("Warning: \($0)") }
                    }
                    if let errors = validation["errors"] as? [String] {
                        ForEach(errors, id: \.self) { Text("Blocked: \($0)") }
                    }
                    DisclosureGroup("Technical validation") {
                        if review["worksheets"] != nil {
                            Text("Minimum linked group: \(validation["minimum_linked_group_size"] as? Int ?? 0)")
                            Text("Entities in small linked classes: \(validation["linked_small_entities"] as? Int ?? 0)")
                        } else {
                            Text("Minimum joint group: \(validation["minimum_class_size"] as? Int ?? 0)")
                            Text("Records in small classes: \(validation["small_class_records"] as? Int ?? 0)")
                        }
                    }
                    Text("Passing validation does not establish anonymity or recipient suitability.")
                        .foregroundStyle(.secondary)
                    Button("Approve and create") { showApproval = true }
                        .appFont(13)
                        .disabled(validation["passed"] as? Bool != true)
                        .buttonStyle(.borderedProminent)
                    Button("Cancel review") { model.cancelReview() }.appFont(13)
                }
            }
            .padding(28)
            .frame(maxWidth: 850, alignment: .leading)
        }
        .sheet(item: $model.categorySheet) { category in
            VStack(alignment: .leading, spacing: 12) {
                Text("Review values found in this field").appFont(18, weight: .bold)
                Text(category.field).appFont(13, weight: .semibold)
                Text("Worksheet\(category.sheets.count == 1 ? "" : "s"): \(category.sheets.joined(separator: ", "))")
                    .foregroundStyle(.secondary)
                Text("SafeSet found \(category.values.count) distinct source values. Confirm that this is the complete set you expect in this field.")
                    .foregroundStyle(.secondary)
                if category.blankCount > 0 {
                    Label(
                        "\(category.blankCount) blank or whitespace-only cells were found. Blank categories cannot be approved; correct the source workbook or remove this field.",
                        systemImage: "exclamationmark.triangle.fill"
                    )
                    .appFont(13)
                    .foregroundStyle(.red)
                }
                if category.action == "code" {
                    Text("After approval, SafeSet will replace each value below with a fresh random code. These are the original values, not the replacement codes.")
                } else {
                    Text("After approval, these original values will remain unchanged in the protected workbook.")
                }
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 6) {
                        ForEach(category.values, id: \.self) { Text($0) }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(10)
                .background(.quaternary.opacity(0.35), in: RoundedRectangle(cornerRadius: 8))
                HStack {
                    Button("Cancel") { model.categorySheet = nil }.appFont(13)
                    Button("Approve this source-value list") {
                        model.approveCategories(category)
                    }
                        .appFont(13)
                        .disabled(category.blankCount > 0 || category.values.isEmpty)
                        .buttonStyle(.borderedProminent)
                }
            }.padding(24).frame(minWidth: 500, minHeight: 390)
        }
        .sheet(isPresented: $showApproval) {
            VStack(alignment: .leading, spacing: 14) {
                Text("Approve protection").appFont(18, weight: .bold)
                Text("Create the reviewed protected workbook and private encrypted bundle?")
                SecureField("Restoration passphrase", text: $passphrase).appFont(13)
                SecureField("Confirm passphrase", text: $confirmation).appFont(13)
                HStack {
                    Button("Cancel") { showApproval = false; passphrase = ""; confirmation = "" }
                        .appFont(13)
                    Button("Create") {
                        guard passphrase.count >= 16, passphrase == confirmation else {
                            model.alert = "Passphrases must match and contain at least 16 characters."
                            return
                        }
                        let secret = passphrase
                        passphrase = ""; confirmation = ""; showApproval = false
                        model.approveProtection(passphrase: secret)
                    }.appFont(13).buttonStyle(.borderedProminent)
                }
            }.padding(24).frame(width: 430)
        }
    }
}

struct RestoreView: View {
    @EnvironmentObject var model: AppModel
    @State private var passphrase = ""
    @State private var showAuthorise = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Restore a workbook").appFont(26, weight: .bold)
                Toggle("Multi-sheet relational bundle", isOn: $model.relationalRestore)
                    .appFont(13)
                Text(model.relationalRestore
                     ? "All bundle-bound worksheets are required. Select any added analysis worksheets to include."
                     : "Restore one or more same-schema worksheets from a version 2 bundle.")
                    .foregroundStyle(.secondary)
                GroupBox("Returning analysis findings") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(restorationAnalysisGuidance)
                        Text(restorationResultExample)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .foregroundStyle(.secondary)
                }
                PathRow(title: "Modified protected copy", path: $model.returned,
                        save: false, fileExtension: "xlsx") {
                    model.chooseRestoreFile($0, sourceFile: false)
                }
                if model.returnedSheets.count > 1 {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(model.relationalRestore
                             ? "Worksheets to include"
                             : "Protected worksheets")
                            .appFont(13, weight: .semibold)
                        ForEach(model.returnedSheets, id: \.self) { sheet in
                            Toggle(sheet, isOn: Binding(
                                get: { model.selectedReturnedSheets.contains(sheet) },
                                set: { selected in
                                    if selected { model.selectedReturnedSheets.insert(sheet) }
                                    else { model.selectedReturnedSheets.remove(sheet) }
                                }
                            ))
                            .appFont(13)
                        }
                    }
                }
                PathRow(title: "Original source", path: $model.original,
                        save: false, fileExtension: "xlsx") {
                    model.chooseRestoreFile($0, sourceFile: true)
                }
                if !model.relationalRestore && model.originalSheets.count > 1 {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Original source worksheets").appFont(13, weight: .semibold)
                        ForEach(model.originalSheets, id: \.self) { sheet in
                            Toggle(sheet, isOn: Binding(
                                get: { model.selectedOriginalSheets.contains(sheet) },
                                set: { selected in
                                    if selected { model.selectedOriginalSheets.insert(sheet) }
                                    else { model.selectedOriginalSheets.remove(sheet) }
                                }
                            ))
                            .appFont(13)
                        }
                    }
                }
                PathRow(title: "Private bundle", path: $model.restoreBundle,
                        save: false, fileExtension: "enc") {
                    model.rememberRestoreBundle($0.path)
                }
                HStack {
                    Text("SafeSet remembers the most recently created or selected bundle on this Mac.")
                        .foregroundStyle(.secondary)
                    Spacer()
                    if !model.restoreBundle.isEmpty {
                        Button("Forget remembered bundle") { model.forgetRestoreBundle() }
                            .appFont(13)
                            .buttonStyle(.link)
                    }
                }
                PathRow(title: "New restored workbook", path: $model.restoredOutput,
                        save: true, fileExtension: "xlsx")
                Text("Unlocking the private bundle is required to validate exact record coverage.")
                    .foregroundStyle(.secondary)
                SecureField("Restoration passphrase", text: $passphrase).appFont(13)
                Button("Validate and review") {
                    let secret = passphrase; passphrase = ""
                    model.prepareRestoration(passphrase: secret)
                }.appFont(13).buttonStyle(.borderedProminent)
                if let review = model.restorationReview {
                    Divider()
                    Text("Restoration review").appFont(18, weight: .bold)
                    Text("Exact coverage: \(review["rows"] as? Int ?? 0) records")
                    Text("Original identity and removed fields will be restored from the source.")
                    if let coded = review["coded_columns"] as? [String], !coded.isEmpty {
                        Text("Coded fields restored from source: \(coded.joined(separator: ", "))")
                    }
                    if let columns = review["source_columns"] as? [String] {
                        DisclosureGroup("Source fields restored") {
                            ForEach(columns, id: \.self) { Text($0) }
                        }
                    }
                    if let names = review["new_columns"] as? [String] {
                        Text("Approve each new result field")
                        ForEach(names, id: \.self) { name in
                            Toggle(name, isOn: Binding(
                                get: { model.approvedResults.contains(name) },
                                set: { if $0 { model.approvedResults.insert(name) }
                                       else { model.approvedResults.remove(name) } }
                            ))
                            .appFont(13)
                        }
                    }
                    if let groups = review["new_columns"] as? [String: [String]] {
                        Text("Approve each new result field in every worksheet")
                        ForEach(groups.keys.sorted(), id: \.self) { sheet in
                            Text(sheet).appFont(13, weight: .semibold)
                            ForEach(groups[sheet] ?? [], id: \.self) { name in
                                let key = "\(sheet)::\(name)"
                                Toggle(name, isOn: Binding(
                                    get: { model.approvedResults.contains(key) },
                                    set: { if $0 { model.approvedResults.insert(key) }
                                           else { model.approvedResults.remove(key) } }
                                ))
                                .appFont(13)
                            }
                        }
                    }
                    if let sheets = review["new_sheets"] as? [String], !sheets.isEmpty {
                        Text("Approve each added analysis worksheet")
                        ForEach(sheets, id: \.self) { sheet in
                            Toggle(sheet, isOn: Binding(
                                get: { model.approvedSheets.contains(sheet) },
                                set: { if $0 { model.approvedSheets.insert(sheet) }
                                       else { model.approvedSheets.remove(sheet) } }
                            ))
                            .appFont(13)
                        }
                        Text("Approved worksheet cell text is copied into static tables; formatting and drawings are not preserved.")
                            .foregroundStyle(.secondary)
                    }
                    Text("New sensitive workbook: \(review["output"] as? String ?? "")")
                    Button("Authorise local restoration") { showAuthorise = true }
                        .appFont(13)
                        .buttonStyle(.borderedProminent)
                    Button("Cancel review") { model.cancelReview() }.appFont(13)
                }
            }.padding(28).frame(maxWidth: 850, alignment: .leading)
        }
        .confirmationDialog("Create a new locally reidentified workbook?",
                            isPresented: $showAuthorise) {
            Button("Authorise restoration") { model.approveRestoration() }.appFont(13)
        }
    }
}

struct AdvancedView: View {
    @EnvironmentObject var model: AppModel
    @State private var secret = ""
    @State private var confirmation = ""
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Advanced tools").appFont(26, weight: .bold)
                Text("These local workflows use explicit YAML policies and legacy version 1 maps.")
                    .foregroundStyle(.secondary)
                GroupBox("Policy YAML") {
                    VStack(alignment: .leading, spacing: 10) {
                        PathRow(title: "Source workbook", path: $model.source,
                                save: false, fileExtension: "xlsx") { model.chooseSource($0) }
                        if model.sourceSheets.count > 1 {
                            Picker("Worksheet", selection: $model.sourceSheet) {
                                Text("Choose…").tag("")
                                ForEach(model.sourceSheets, id: \.self) { Text($0).tag($0) }
                            }
                            .appFont(13)
                            Button("Inspect") { model.inspect() }.appFont(13)
                        }
                        PathRow(title: "Policy", path: $model.legacyPolicy,
                                save: false, fileExtension: "yaml")
                        HStack {
                            Button("Load policy choices") { model.loadPolicy() }.appFont(13)
                            Button("Review and edit fields") { model.page = .protect }
                                .appFont(13)
                            Button("Save revised policy…") {
                                chooseSave(extension: "yaml") { url in
                                    guard let url else { return }
                                    model.savePolicy(url.path)
                                }
                            }
                            .appFont(13)
                        }
                    }.padding(8)
                }
                GroupBox("Legacy version 1 export") {
                    VStack(alignment: .leading, spacing: 10) {
                        PathRow(title: "Export workbook", path: $model.legacyOutput,
                                save: true, fileExtension: "xlsx")
                        PathRow(title: "Private map (optional)", path: $model.legacyMap,
                                save: true, fileExtension: "enc")
                        Button("Prepare export review") { model.prepareLegacyExport() }
                            .appFont(13)
                        if let review = model.legacyReview,
                           let validation = review["validation"] as? [String: Any] {
                            Text("\(review["rows"] as? Int ?? 0) records. Validation: \((validation["passed"] as? Bool == true) ? "passed" : "blocked")")
                            Text("Export: \(review["output"] as? String ?? "")")
                            Text("Private map: \(review["map"] as? String ?? "")")
                            if let warnings = validation["warnings"] as? [String] {
                                ForEach(warnings, id: \.self) { Text($0) }
                            }
                            SecureField("New map passphrase", text: $secret).appFont(13)
                            SecureField("Confirm map passphrase", text: $confirmation)
                                .appFont(13)
                            Button("Approve export and create map") {
                                guard secret.count >= 16, secret == confirmation else {
                                    model.alert = "Passphrases must match and contain at least 16 characters."
                                    return
                                }
                                let value = secret; secret = ""
                                confirmation = ""
                                model.approveLegacyExport(passphrase: value)
                            }.appFont(13).disabled(validation["passed"] as? Bool != true)
                            Button("Cancel review") { model.cancelReview() }.appFont(13)
                        }
                    }.padding(8)
                }
                GroupBox("Legacy selected-result restoration") {
                    VStack(alignment: .leading, spacing: 10) {
                        PathRow(title: "Returned workbook", path: $model.legacyReturned,
                                save: false, fileExtension: "xlsx")
                        Button("Read returned columns") { model.inspectLegacyReturned() }
                            .appFont(13)
                        ForEach(model.legacyResultColumns, id: \.self) { name in
                            Toggle(name, isOn: Binding(
                                get: { model.legacyApproved.contains(name) },
                                set: { if $0 { model.legacyApproved.insert(name) }
                                       else { model.legacyApproved.remove(name) } }
                            ))
                            .appFont(13)
                        }
                        PathRow(title: "New restored workbook", path: $model.restoredOutput,
                                save: true, fileExtension: "xlsx")
                        SecureField("Map passphrase", text: $secret).appFont(13)
                        Button("Authorise legacy restoration") {
                            let value = secret; secret = ""
                            model.restoreLegacy(passphrase: value)
                        }
                        .appFont(13)
                    }.padding(8)
                }
            }.padding(28).frame(maxWidth: 850, alignment: .leading)
        }
    }
}

private enum AppTextSize {
    static let levels = [0.85, 0.92, 1.0, 1.12, 1.25, 1.4, 1.6]
    static let defaultIndex = 2

    static func level(at index: Int) -> Double {
        levels[min(max(index, 0), levels.count - 1)]
    }
}

@main struct SafeSetMacApp: App {
    @StateObject private var model = AppModel()
    @AppStorage("appTextSizeIndex") private var textSizeIndex = AppTextSize.defaultIndex

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .environment(\.appTextScale, AppTextSize.level(at: textSizeIndex))
        }
            .windowStyle(.titleBar)
            .commands {
                CommandGroup(after: .toolbar) {
                    Button("Increase Text Size") {
                        textSizeIndex = min(textSizeIndex + 1, AppTextSize.levels.count - 1)
                    }
                    .keyboardShortcut("+", modifiers: .command)
                    .disabled(textSizeIndex >= AppTextSize.levels.count - 1)

                    Button("Decrease Text Size") {
                        textSizeIndex = max(textSizeIndex - 1, 0)
                    }
                    .keyboardShortcut("-", modifiers: .command)
                    .disabled(textSizeIndex <= 0)

                    Button("Reset Text Size") {
                        textSizeIndex = AppTextSize.defaultIndex
                    }
                    .keyboardShortcut("0", modifiers: .command)
                    .disabled(textSizeIndex == AppTextSize.defaultIndex)
                }
            }
    }
}
