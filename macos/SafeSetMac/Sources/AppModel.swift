import AppKit
import Combine
import Foundation

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

    var needsAttention: Bool {
        if action.isEmpty { return true }
        if action == "drop" { return false }
        if action == "pseudonymise" { return false }
        if !["quasi_identifier", "analytical_attribute"].contains(classification) { return true }
        if action == "keep" || action == "code" {
            return allowedValues.isEmpty || blankCount > 0
        }
        if action == "bin" {
            let validPairs = binsText.split(separator: "\n").filter { line in
                let parts = line.split(separator: ",", omittingEmptySubsequences: false)
                return parts.count == 2
                    && Double(parts[0].trimmingCharacters(in: .whitespaces)) != nil
                    && Double(parts[1].trimmingCharacters(in: .whitespaces)) != nil
            }
            return validPairs.count < 2
        }
        if action == "keep_numeric" {
            guard let lower = Double(lower), let upper = Double(upper) else { return true }
            return lower < 0 || lower >= upper
        }
        return false
    }

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
        let policyClassification: String
        if action == "pseudonymise" { policyClassification = "direct_identifier" }
        else if action == "drop" && classification.isEmpty { policyClassification = "unknown" }
        else { policyClassification = classification }
        return [
            "action": action, "classification": policyClassification,
            "allowed_values": allowedValues,
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

struct SourceCellLocation: Identifiable {
    let sheet: String
    let cell: String
    var id: String { sheet + ":" + cell }
}

@MainActor final class AppModel: ObservableObject {
    private static let recentRestoreBundleKey = "recentRestoreBundlePath"
    enum Page: String { case home, protect, protectDocument, restore, restoreDocument, advanced, help }
    @Published var page: Page = .home
    @Published var busy = false
    @Published var alert = ""
    @Published var showAnalysisPrompt = false
    @Published var hasRecentProtectedWorkbook = false
    @Published var source = ""
    @Published var sourceSheets: [String] = []
    @Published var sourceSheet = ""
    @Published var selectedSourceSheets: Set<String> = []
    @Published var fieldsBySheet: [String: [FieldDraft]] = [:]
    @Published var fields: [FieldDraft] = []
    @Published var sharedCodeFields: Set<String> = []
    @Published var workbookEditing = true
    @Published var editableFields: [String: Set<String>] = [:]
    @Published var latestAnalysisPrompt = restorationCopyText
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
    @Published var bundlePermissions: [String: [String]]?
    @Published var unsafeSourceCount: Int?
    @Published var unsafeSourceLocations: [SourceCellLocation] = []
    @Published var approvedResults: Set<String> = []
    @Published var approvedSheets: Set<String> = []
    @Published var approvedChanges: [String: Set<String>] = [:]
    @Published var relationalRestore = false
    @Published var reconcileParticipants = false
    @Published var participantTarget = ""
    @Published var participantReference = ""
    @Published var participantProposalSheet = "SafeSet additions"
    @Published var includeParticipantAdditions = true
    @Published var includeParticipantRemovals = false
    @Published var participantMappings: [String: String] = [:]
    @Published var participantConfigChanged = false
    @Published var approvedParticipantAdditions = false
    @Published var approvedParticipantRemovals = false
    @Published var legacyPolicy = ""
    @Published var legacyMap = ""
    @Published var legacyOutput = ""
    @Published var legacyReturned = ""
    @Published var legacyResultColumns: [String] = []
    @Published var legacyApproved: Set<String> = []
    @Published var legacyReview: [String: Any]?
    @Published var documentSource = ""
    @Published var documentProtectedOutput = ""
    @Published var documentBundleOutput = ""
    @Published var documentInspection: [String: Any]?
    @Published var documentProtectionReview: [String: Any]?
    @Published var documentReturned = ""
    @Published var documentRestoreBundle = ""
    @Published var documentRestoredOutput = ""
    @Published var documentRestorationReview: [String: Any]?
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

    func fieldNeedsAttention(_ heading: String) -> Bool {
        orderedSelectedSourceSheets.contains { sheet in
            fieldsBySheet[sheet]?.first(where: { $0.id == heading })?.needsAttention ?? false
        }
    }

    var undecidedFieldCount: Int {
        consolidatedFields.filter { item in
            item.sheets.allSatisfy { sheet in
                fieldsBySheet[sheet]?.first(where: { $0.id == item.id })?.action == ""
            }
        }.count
    }

    var hasSourceKeySelections: Bool {
        !selectedSourceSheets.isEmpty && selectedSourceSheets.allSatisfy { sheet in
            (fieldsBySheet[sheet] ?? []).filter { $0.action == "pseudonymise" }.count == 1
        }
    }

    func removeUndecidedFields() {
        guard hasSourceKeySelections else { return }
        let headings = consolidatedFields.filter { item in
            item.sheets.allSatisfy { sheet in
                fieldsBySheet[sheet]?.first(where: { $0.id == item.id })?.action == ""
            }
        }.map(\.id)
        for heading in headings {
            for sheet in selectedSourceSheets {
                guard var sheetFields = fieldsBySheet[sheet],
                      let index = sheetFields.firstIndex(where: { $0.id == heading }) else { continue }
                sheetFields[index].action = "drop"
                fieldsBySheet[sheet] = sheetFields
                if sheet == sourceSheet { fields = sheetFields }
            }
        }
        invalidate()
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
            if ["keep", "code", "bin", "keep_numeric"].contains(field.action)
                && !["quasi_identifier", "analytical_attribute"].contains(field.classification) {
                return "Choose why every retained or transformed field is needed. 'I'm not sure' still needs attention."
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

    func editableCandidates(_ sheet: String) -> [String] {
        let configured = sheet == sourceSheet ? fields : (fieldsBySheet[sheet] ?? [])
        return configured.filter { ["keep", "code", "keep_numeric"].contains($0.action) }
            .map(\.id)
    }

    var editingPermissions: [String: [String]] {
        Dictionary(uniqueKeysWithValues: selectedSourceSheets.map { sheet in
            (sheet, editableCandidates(sheet).filter { editableFields[sheet]?.contains($0) == true })
        })
    }

    var canApproveRestoration: Bool {
        guard let review = restorationReview, review["review_id"] is String else { return false }
        if review["reconciliation"] as? Bool == true {
            guard !participantConfigChanged, review["ready"] as? Bool == true,
                  approvedParticipantAdditions == ((review["additions"] as? Int ?? 0) > 0),
                  approvedParticipantRemovals == ((review["removals"] as? Int ?? 0) > 0)
            else { return false }
        }
        if let changes = review["changes"] as? [String: [String: Int]] {
            guard changes.allSatisfy({ sheet, columns in
                Set(columns.keys) == (approvedChanges[sheet] ?? [])
            }), approvedChanges.allSatisfy({ sheet, columns in
                columns == Set(changes[sheet]?.keys.map { $0 } ?? [])
            }) else { return false }
        }
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
        self.relationalRestore = preferences.bool(forKey: "recentRestoreBundleRelational")
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
        invalidate()
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
        documentProtectionReview = nil
        documentRestorationReview = nil
        bundlePermissions = nil
        unsafeSourceCount = nil
        unsafeSourceLocations = []
    }

    func cancelReview() {
        invalidate()
        send("cancel", [:]) { _ in }
    }

    func chooseSource(_ url: URL) {
        source = url.path; fields = []; fieldsBySheet = [:]; sharedCodeFields = []
        editableFields = [:]
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
            editableFields.removeValue(forKey: sheet)
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
        let relational = workbookEditing || selectedSourceSheets.count > 1
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
            if workbookEditing {
                payload["editable_fields"] = editingPermissions
            }
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
            self.relationalRestore = relational
            self.preferences.set(relational, forKey: "recentRestoreBundleRelational")
            self.latestAnalysisPrompt = review["analysis_prompt"] as? String ?? restorationCopyText
            self.original = self.source
            self.originalSheets = self.sourceSheets
            self.originalSheet = self.sourceSheet
            self.selectedOriginalSheets = self.selectedSourceSheets
            self.rememberRestoreBundle(review["bundle"] as? String ?? "")
            self.protectionReview = nil
            self.hasRecentProtectedWorkbook = true
            self.page = .home
            self.showAnalysisPrompt = true
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
                self.selectedReturnedSheets = Set(sheets.count == 1 ? sheets : [])
            }
        }
    }

    func prepareRestoration(passphrase: String) {
        guard !returned.isEmpty, !original.isEmpty, !restoreBundle.isEmpty,
              relationalRestore || !orderedReturnedRestoreSheets.isEmpty,
              relationalRestore || !orderedOriginalRestoreSheets.isEmpty
        else {
            alert = "Choose both workbooks, their worksheets and the private bundle."; return
        }
        let output = restoredOutput.isEmpty
            ? (returned as NSString).deletingPathExtension + "-restored.xlsx" : restoredOutput
        let command = relationalRestore
            ? (reconcileParticipants ? "prepare_participants" : "prepare_relational_reconstruction")
            : "prepare_reconstruction"
        var payload: [String: Any] = [
            "returned": returned, "source": original, "bundle": restoreBundle,
            "output": output, "passphrase": passphrase
        ]
        if !relationalRestore {
            payload["returned_sheet"] = orderedReturnedRestoreSheets
            payload["source_sheet"] = orderedOriginalRestoreSheets
        }
        if relationalRestore && reconcileParticipants { payload["config"] = participantConfig }
        if relationalRestore && reconcileParticipants {
            bundlePermissions = nil
            send("inspect_bundle_permissions", [
                "source": original, "bundle": restoreBundle, "passphrase": passphrase
            ]) { result in
                self.bundlePermissions = result["editable_fields"] as? [String: [String]]
                self.send(command, payload) { review in
                    self.acceptRestorationReview(review)
                }
            }
        } else {
            send(command, payload) { result in
                self.acceptRestorationReview(result)
            }
        }
    }

    var participantConfig: [String: Any] {
        var mappings: [String: Any] = [:]
        for (name, selection) in participantMappings {
            if selection == "blank" { mappings[name] = NSNull() }
            else if selection.hasPrefix("column:") { mappings[name] = String(selection.dropFirst(7)) }
            else if selection.hasPrefix("source:") {
                let parts = selection.dropFirst(7).split(separator: "\u{1F}", omittingEmptySubsequences: false)
                guard parts.count == 2 else { continue }
                let sheet = String(parts[0])
                let column = String(parts[1])
                mappings[name] = ["sheet": sheet, "column": column]
            }
        }
        return ["target_sheet": participantTarget, "reference_sheet": participantReference,
                "additions_sheet": participantProposalSheet,
                "include_additions": includeParticipantAdditions,
                "include_removals": includeParticipantRemovals, "column_sources": mappings]
    }

    func participantConfigurationChanged() {
        participantConfigChanged = true
        approvedParticipantAdditions = false
        approvedParticipantRemovals = false
        approvedChanges = [:]
    }

    func acceptRestorationReview(_ result: [String: Any]) {
        restorationReview = result
        latestAnalysisPrompt = result["analysis_prompt"] as? String ?? restorationCopyText
        approvedResults = []
        approvedSheets = []
        approvedChanges = [:]
        approvedParticipantAdditions = false
        approvedParticipantRemovals = false
        participantConfigChanged = false
    }

    func updateParticipantReview() {
        guard let token = restorationReview?["review_id"] as? String else { return }
        send("update_participants", ["review_id": token, "config": participantConfig]) { result in
            self.acceptRestorationReview(result)
        }
    }

    func locateUnsafeSourceCells(passphrase: String) {
        guard !original.isEmpty, !restoreBundle.isEmpty,
              relationalRestore || !orderedOriginalRestoreSheets.isEmpty else {
            alert = "Choose the original source, its worksheets and the private bundle."
            return
        }
        unsafeSourceCount = nil
        unsafeSourceLocations = []
        send("locate_unsafe_source_cells", [
            "source": original,
            "bundle": restoreBundle,
            "passphrase": passphrase,
            "relational": relationalRestore,
            "sheet": relationalRestore ? NSNull() : orderedOriginalRestoreSheets
        ]) { result in
            self.unsafeSourceCount = result["count"] as? Int
            self.unsafeSourceLocations = (result["cells"] as? [[String: String]] ?? []).compactMap {
                guard let sheet = $0["sheet"], let cell = $0["cell"] else { return nil }
                return SourceCellLocation(sheet: sheet, cell: cell)
            }
        }
    }

    func approveRestoration() {
        guard canApproveRestoration,
              let review = restorationReview,
              let token = review["review_id"] as? String else {
            alert = "Review and approve every changed field, new result field and added worksheet before restoration."
            return
        }
        let command: String
        let approved: Any
        if review["reconciliation"] as? Bool == true {
            send("approve_participants", [
                "review_id": token,
                "approved_changes": (review["changes"] as? [String: [String: Int]] ?? [:])
                    .mapValues { Array($0.keys).sorted() },
                "approve_additions": approvedParticipantAdditions,
                "approve_removals": approvedParticipantRemovals
            ]) { _ in
                self.restorationReview = nil
                self.alert = "A new locally reidentified workbook was created. Keep it private."
                self.page = .home
            }
            return
        }
        if relationalRestore, let groups = review["new_columns"] as? [String: [String]] {
            command = "approve_relational_reconstruction"
            approved = groups
        } else {
            guard let names = review["new_columns"] as? [String] else { return }
            command = "approve_reconstruction"
            approved = names
        }
        var payload: [String: Any] = [
            "review_id": token,
            "approved_results": approved,
            "approved_sheets": Array(approvedSheets).sorted()
        ]
        if let changes = review["changes"] as? [String: [String: Int]] {
            payload["approved_changes"] = changes.mapValues { Array($0.keys).sorted() }
        }
        send(command, payload) { _ in
            self.restorationReview = nil
            self.alert = "A new locally reidentified workbook was created. Keep it private."
            self.page = .home
        }
    }

    func chooseDocumentSource(_ url: URL) {
        documentSource = url.path
        documentInspection = nil
        documentProtectionReview = nil
        send("inspect_document", ["source": documentSource]) {
            self.documentInspection = $0
        }
    }

    func prepareDocumentProtection(terms: [String], removeComments: Bool = true) {
        guard !documentSource.isEmpty else {
            alert = "Choose an original DOCX document."
            return
        }
        let output = documentProtectedOutput.isEmpty
            ? (documentSource as NSString).deletingPathExtension + "-protected.docx"
            : documentProtectedOutput
        let payloadTerms: [[String: String]] = terms
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .map { ["value": $0, "kind": "person"] }
        send("prepare_document_protection", [
            "source": documentSource,
            "output": output,
            "bundle": documentBundleOutput.isEmpty ? NSNull() : documentBundleOutput,
            "terms": payloadTerms,
            "remove_comments": removeComments
        ]) { self.documentProtectionReview = $0 }
    }

    func approveDocumentProtection(passphrase: String) {
        guard let review = documentProtectionReview,
              let token = review["review_id"] as? String else { return }
        send("approve_document_protection", [
            "review_id": token, "passphrase": passphrase
        ]) { _ in
            self.documentRestoreBundle = review["bundle"] as? String ?? ""
            self.documentProtectionReview = nil
            self.alert = "Protected document and private restoration bundle created."
            self.page = .home
        }
    }

    func prepareDocumentRestoration(passphrase: String) {
        guard !documentReturned.isEmpty, !documentRestoreBundle.isEmpty else {
            alert = "Choose the modified protected DOCX and its private bundle."
            return
        }
        let output = documentRestoredOutput.isEmpty
            ? (documentReturned as NSString).deletingPathExtension + "-restored.docx"
            : documentRestoredOutput
        send("prepare_document_restoration", [
            "returned": documentReturned,
            "bundle": documentRestoreBundle,
            "output": output,
            "passphrase": passphrase
        ]) { self.documentRestorationReview = $0 }
    }

    func approveDocumentRestoration() {
        guard let token = documentRestorationReview?["review_id"] as? String else { return }
        send("approve_document_restoration", ["review_id": token]) { _ in
            self.documentRestorationReview = nil
            self.alert = "A new locally reidentified document was created. Keep it private."
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
