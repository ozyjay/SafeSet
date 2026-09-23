import AppKit
import Combine
import Foundation
import SwiftUI

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
    var hint = ""
    var flags: [String] = []
    var action = ""
    var classification = ""
    var allowedValues: [String] = []
    var binsText = ""
    var lower = ""
    var upper = ""
    var places = "0"

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
            "bins": bins, "bounds": bounds, "max_decimal_places": Int(places) as Any? ?? NSNull()
        ]
    }
}

struct CategorySheet: Identifiable {
    let id = UUID()
    let field: String
    let action: String
    let values: [String]
}

@MainActor final class AppModel: ObservableObject {
    enum Page: String { case home, protect, restore, advanced }
    @Published var page: Page = .home
    @Published var busy = false
    @Published var alert = ""
    @Published var source = ""
    @Published var sourceSheets: [String] = []
    @Published var sourceSheet = ""
    @Published var fields: [FieldDraft] = []
    @Published var threshold = "2"
    @Published var protectedOutput = ""
    @Published var bundleOutput = ""
    @Published var protectionReview: [String: Any]?
    @Published var categorySheet: CategorySheet?
    @Published var returned = ""
    @Published var returnedSheets: [String] = []
    @Published var returnedSheet = ""
    @Published var original = ""
    @Published var originalSheets: [String] = []
    @Published var originalSheet = ""
    @Published var restoreBundle = ""
    @Published var restoredOutput = ""
    @Published var restorationReview: [String: Any]?
    @Published var approvedResults: Set<String> = []
    @Published var legacyPolicy = ""
    @Published var legacyMap = ""
    @Published var legacyOutput = ""
    @Published var legacyReturned = ""
    @Published var legacyResultColumns: [String] = []
    @Published var legacyApproved: Set<String> = []
    @Published var legacyReview: [String: Any]?
    private var bridge: BackendBridge?
    private let worker = DispatchQueue(label: "org.ozyjay.SafeSet.bridge", qos: .userInitiated)

    var canPrepareProtection: Bool {
        !fields.isEmpty && fields.allSatisfy {
            !$0.action.isEmpty && ($0.action == "drop" || !$0.classification.isEmpty)
        }
    }

    var canApproveRestoration: Bool {
        guard let review = restorationReview,
              review["review_id"] is String,
              let names = review["new_columns"] as? [String] else { return false }
        return Set(names) == approvedResults
    }

    init() {
        do { bridge = try BackendBridge() }
        catch { alert = "The bundled SafeSet engine could not start." }
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
        source = url.path; fields = []; invalidate()
        send("list_sheets", ["path": source]) { result in
            self.sourceSheets = result["sheets"] as? [String] ?? []
            self.sourceSheet = self.sourceSheets.count == 1 ? self.sourceSheets[0] : ""
            if !self.sourceSheet.isEmpty { self.inspect() }
        }
    }

    func inspect() {
        guard !source.isEmpty, !sourceSheet.isEmpty else { return }
        invalidate()
        send("inspect", ["source": source, "sheet": sourceSheet]) { result in
            let data = result["columns"] as? [[String: Any]] ?? []
            self.fields = data.map { item in
                var field = FieldDraft(id: item["column"] as? String ?? "")
                field.type = item["type"] as? String ?? ""
                field.cardinality = item["cardinality"] as? Int ?? 0
                field.hint = item["inferred_classification"] as? String ?? ""
                field.flags = item["flags"] as? [String] ?? []
                return field
            }
        }
    }

    func categories(for field: String) {
        invalidate()
        send("categories", ["source": source, "sheet": sourceSheet, "column": field]) { result in
            let action = self.fields.first(where: { $0.id == field })?.action ?? ""
            self.categorySheet = CategorySheet(
                field: field, action: action, values: result["values"] as? [String] ?? []
            )
        }
    }

    func approveCategories(_ category: CategorySheet) {
        if let index = fields.firstIndex(where: { $0.id == category.field }) {
            fields[index].allowedValues = category.values
        }
        categorySheet = nil
    }

    func draftPayload() -> [String: Any] {
        Dictionary(uniqueKeysWithValues: fields.map { ($0.id, $0.payload()) })
    }

    func prepareProtection() {
        guard canPrepareProtection else {
            alert = "Choose an action for every field and classify fields you keep or replace."
            return
        }
        let output = protectedOutput.isEmpty
            ? (source as NSString).deletingPathExtension + "-protected.xlsx" : protectedOutput
        var payload: [String: Any] = [
            "source": source, "sheet": sourceSheet, "output": output,
            "drafts": draftPayload(), "threshold": threshold
        ]
        payload["bundle"] = bundleOutput.isEmpty ? NSNull() : bundleOutput
        send("prepare_protection", payload) { self.protectionReview = $0 }
    }

    func approveProtection(passphrase: String) {
        guard let review = protectionReview,
              let token = review["review_id"] as? String else { return }
        send("approve_protection", ["review_id": token, "passphrase": passphrase]) { _ in
            self.original = self.source
            self.originalSheets = self.sourceSheets
            self.originalSheet = self.sourceSheet
            self.restoreBundle = review["bundle"] as? String ?? ""
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
            } else {
                self.returnedSheets = sheets
                self.returnedSheet = sheets.count == 1 ? sheets[0] : ""
            }
        }
    }

    func prepareRestoration(passphrase: String) {
        guard !returned.isEmpty, !original.isEmpty, !restoreBundle.isEmpty,
              !returnedSheet.isEmpty, !originalSheet.isEmpty else {
            alert = "Choose both workbooks, their worksheets and the private bundle."; return
        }
        let output = restoredOutput.isEmpty
            ? (returned as NSString).deletingPathExtension + "-restored.xlsx" : restoredOutput
        send("prepare_reconstruction", [
            "returned": returned, "returned_sheet": returnedSheet,
            "source": original, "source_sheet": originalSheet,
            "bundle": restoreBundle, "output": output, "passphrase": passphrase
        ]) { result in
            self.restorationReview = result
            self.approvedResults = []
        }
    }

    func approveRestoration() {
        guard canApproveRestoration,
              let review = restorationReview,
              let token = review["review_id"] as? String,
              let names = review["new_columns"] as? [String] else {
            alert = "Approve every new result field or remove it from the returned workbook."
            return
        }
        send("approve_reconstruction", [
            "review_id": token, "approved_results": names
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
                if let places = draft["max_decimal_places"] as? Int {
                    self.fields[index].places = String(places)
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

private func chooseOpen() -> URL? {
    let panel = NSOpenPanel()
    panel.allowedContentTypes = [.init(filenameExtension: "xlsx")!]
    panel.canChooseDirectories = false
    return panel.runModal() == .OK ? panel.url : nil
}

private func chooseAnyFile() -> URL? {
    let panel = NSOpenPanel()
    panel.canChooseDirectories = false
    return panel.runModal() == .OK ? panel.url : nil
}

private func chooseSave(extension suffix: String) -> URL? {
    let panel = NSSavePanel()
    panel.allowedContentTypes = [.init(filenameExtension: suffix)!]
    return panel.runModal() == .OK ? panel.url : nil
}

struct PathRow: View {
    let title: String
    @Binding var path: String
    let save: Bool
    let fileExtension: String
    var onChoose: ((URL) -> Void)? = nil

    var body: some View {
        HStack {
            Text(title).frame(width: 180, alignment: .leading)
            TextField("Choose a local file", text: $path)
                .textFieldStyle(.roundedBorder)
                .disabled(!save)
            Button("Choose…") {
                if let url = save ? chooseSave(extension: fileExtension) : chooseAnyFile() {
                    path = url.path
                    onChoose?(url)
                }
            }
        }
    }
}

struct FieldCard: View {
    @Binding var field: FieldDraft
    let categories: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(field.id).font(.headline)
                Spacer()
                Text("\(field.type) · \(field.cardinality) values")
                    .foregroundStyle(.secondary)
            }
            HStack {
                Picker("Appearance", selection: $field.action) {
                    Text("Choose…").tag("")
                    ForEach(actionOptions, id: \.1) { item in Text(item.0).tag(item.1) }
                }
                if field.action != "drop" {
                    Picker("Classification", selection: $field.classification) {
                        Text("Choose…").tag("")
                        ForEach(classOptions, id: \.1) { item in Text(item.0).tag(item.1) }
                    }
                }
            }
            if field.action == "keep" || field.action == "code" {
                VStack(alignment: .leading, spacing: 5) {
                    Text(field.action == "code"
                         ? "Review the distinct source values before SafeSet replaces each one with a fresh random code."
                         : "Review the distinct source values that will remain unchanged in the protected copy.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                    HStack {
                        Button("Review values found in this field…") { categories(field.id) }
                        Text("\(field.allowedValues.count) source values approved")
                        .foregroundStyle(.secondary)
                    }
                }
            }
            if field.action == "bin" {
                TextField("One lower,upper range per line", text: $field.binsText, axis: .vertical)
                    .lineLimit(2...5)
            }
            if field.action == "keep_numeric" {
                HStack {
                    TextField("Lower bound", text: $field.lower)
                    TextField("Upper bound", text: $field.upper)
                    TextField("Decimal places", text: $field.places)
                }
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("Decision details").font(.subheadline.weight(.semibold))
                Text("Suggested classification: \(field.hint.replacingOccurrences(of: "_", with: " "))")
                if field.action != "drop" && !field.flags.isEmpty {
                    Label("Warnings: \(field.flags.joined(separator: ", "))",
                          systemImage: "exclamationmark.triangle")
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

    var body: some View {
        NavigationSplitView {
            List(selection: Binding(
                get: { model.page }, set: { model.page = $0 ?? .home; model.invalidate() }
            )) {
                Label("Home", systemImage: "house").tag(AppModel.Page.home)
                Label("Protect workbook", systemImage: "lock.doc").tag(AppModel.Page.protect)
                Label("Restore workbook", systemImage: "lock.open.doc").tag(AppModel.Page.restore)
                Label("Advanced", systemImage: "slider.horizontal.3").tag(AppModel.Page.advanced)
            }
            .navigationTitle("SafeSet")
            .frame(minWidth: 190)
        } detail: {
            Group {
                switch model.page {
                case .home: HomeView()
                case .protect: ProtectView()
                case .restore: RestoreView()
                case .advanced: AdvancedView()
                }
            }
            .frame(minWidth: 680, minHeight: 540)
            .overlay { if model.busy { ProgressView().padding().background(.regularMaterial) } }
        }
        .alert("SafeSet", isPresented: Binding(
            get: { !model.alert.isEmpty }, set: { if !$0 { model.alert = "" } }
        )) { Button("OK") { model.alert = "" } } message: { Text(model.alert) }
        .onChange(of: model.fields) { model.invalidate() }
        .onChange(of: model.source) { model.invalidate() }
        .onChange(of: model.sourceSheet) { model.fields = []; model.invalidate() }
        .onChange(of: model.protectedOutput) { model.invalidate() }
        .onChange(of: model.bundleOutput) { model.invalidate() }
        .onChange(of: model.threshold) { model.invalidate() }
        .onChange(of: model.returned) { model.invalidate() }
        .onChange(of: model.returnedSheet) { model.invalidate() }
        .onChange(of: model.original) { model.invalidate() }
        .onChange(of: model.originalSheet) { model.invalidate() }
        .onChange(of: model.restoreBundle) { model.invalidate() }
        .onChange(of: model.restoredOutput) { model.invalidate() }
        .onChange(of: model.legacyPolicy) { model.invalidate() }
        .onChange(of: model.legacyMap) { model.invalidate() }
        .onChange(of: model.legacyOutput) { model.invalidate() }
    }
}

struct HomeView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Text("Protect, work, restore").font(.largeTitle.bold())
            Text("Create a protected working copy, analyse it, then reconstruct a new identifiable workbook locally.")
                .font(.title3).foregroundStyle(.secondary)
            HStack(spacing: 16) {
                Button { model.page = .protect } label: {
                    Label("Protect a workbook", systemImage: "lock.doc")
                        .frame(maxWidth: .infinity, minHeight: 100)
                }.buttonStyle(.borderedProminent)
                Button { model.page = .restore } label: {
                    Label("Restore a workbook", systemImage: "lock.open.doc")
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

struct ProtectView: View {
    @EnvironmentObject var model: AppModel
    @State private var passphrase = ""
    @State private var confirmation = ""
    @State private var showApproval = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Protect a workbook").font(.largeTitle.bold())
                PathRow(title: "Original workbook", path: $model.source, save: false,
                        fileExtension: "xlsx") { model.chooseSource($0) }
                if model.sourceSheets.count > 1 {
                    Picker("Worksheet", selection: $model.sourceSheet) {
                        Text("Choose…").tag("")
                        ForEach(model.sourceSheets, id: \.self) { Text($0).tag($0) }
                    }
                    Button("Inspect worksheet") { model.inspect() }
                }
                if !model.fields.isEmpty {
                    Text("Review every field").font(.title2.bold())
                    Text("Choose an action for every field. Classify fields you keep or replace; removed fields need no classification.")
                        .foregroundStyle(.secondary)
                    ForEach($model.fields) { field in
                        FieldCard(field: field) { model.categories(for: $0) }
                    }
                    HStack {
                        Text("Minimum group size")
                        TextField("2", text: $model.threshold).frame(width: 75)
                    }
                    PathRow(title: "Protected workbook", path: $model.protectedOutput,
                            save: true, fileExtension: "xlsx")
                    DisclosureGroup("Advanced settings") {
                        PathRow(title: "Private bundle location", path: $model.bundleOutput,
                                save: true, fileExtension: "enc")
                    }
                    Button("Review protection") { model.prepareProtection() }
                        .buttonStyle(.borderedProminent)
                }
                if let review = model.protectionReview,
                   let validation = review["validation"] as? [String: Any] {
                    Divider()
                    Text("Final review").font(.title2.bold())
                    Text("\(review["rows"] as? Int ?? 0) records · \(review["removed"] as? Int ?? 0) removed · 1 identifier replaced · \(review["obfuscated"] as? Int ?? 0) obfuscated · \(review["retained"] as? Int ?? 0) retained")
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
                        Text("Minimum joint group: \(validation["minimum_class_size"] as? Int ?? 0)")
                        Text("Records in small classes: \(validation["small_class_records"] as? Int ?? 0)")
                    }
                    Text("Passing validation does not establish anonymity or recipient suitability.")
                        .foregroundStyle(.secondary)
                    Button("Approve and create") { showApproval = true }
                        .disabled(validation["passed"] as? Bool != true)
                        .buttonStyle(.borderedProminent)
                    Button("Cancel review") { model.cancelReview() }
                }
            }
            .padding(28)
            .frame(maxWidth: 850, alignment: .leading)
        }
        .sheet(item: $model.categorySheet) { category in
            VStack(alignment: .leading, spacing: 12) {
                Text("Review values found in this field").font(.title2.bold())
                Text(category.field).font(.headline)
                Text("SafeSet found \(category.values.count) distinct source values. Confirm that this is the complete set you expect in this field.")
                    .foregroundStyle(.secondary)
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
                    Button("Cancel") { model.categorySheet = nil }
                    Button("Approve this source-value list") {
                        model.approveCategories(category)
                    }
                        .buttonStyle(.borderedProminent)
                }
            }.padding(24).frame(minWidth: 500, minHeight: 390)
        }
        .sheet(isPresented: $showApproval) {
            VStack(alignment: .leading, spacing: 14) {
                Text("Approve protection").font(.title2.bold())
                Text("Create the reviewed protected workbook and private encrypted bundle?")
                SecureField("Restoration passphrase", text: $passphrase)
                SecureField("Confirm passphrase", text: $confirmation)
                HStack {
                    Button("Cancel") { showApproval = false; passphrase = ""; confirmation = "" }
                    Button("Create") {
                        guard passphrase.count >= 16, passphrase == confirmation else {
                            model.alert = "Passphrases must match and contain at least 16 characters."
                            return
                        }
                        let secret = passphrase
                        passphrase = ""; confirmation = ""; showApproval = false
                        model.approveProtection(passphrase: secret)
                    }.buttonStyle(.borderedProminent)
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
                Text("Restore a workbook").font(.largeTitle.bold())
                PathRow(title: "Modified protected copy", path: $model.returned,
                        save: false, fileExtension: "xlsx") {
                    model.chooseRestoreFile($0, sourceFile: false)
                }
                if model.returnedSheets.count > 1 {
                    Picker("Protected worksheet", selection: $model.returnedSheet) {
                        Text("Choose…").tag("")
                        ForEach(model.returnedSheets, id: \.self) { Text($0).tag($0) }
                    }
                }
                PathRow(title: "Original source", path: $model.original,
                        save: false, fileExtension: "xlsx") {
                    model.chooseRestoreFile($0, sourceFile: true)
                }
                if model.originalSheets.count > 1 {
                    Picker("Source worksheet", selection: $model.originalSheet) {
                        Text("Choose…").tag("")
                        ForEach(model.originalSheets, id: \.self) { Text($0).tag($0) }
                    }
                }
                PathRow(title: "Private bundle", path: $model.restoreBundle,
                        save: false, fileExtension: "enc")
                PathRow(title: "New restored workbook", path: $model.restoredOutput,
                        save: true, fileExtension: "xlsx")
                Text("Unlocking the private bundle is required to validate exact record coverage.")
                    .foregroundStyle(.secondary)
                SecureField("Restoration passphrase", text: $passphrase)
                Button("Validate and review") {
                    let secret = passphrase; passphrase = ""
                    model.prepareRestoration(passphrase: secret)
                }.buttonStyle(.borderedProminent)
                if let review = model.restorationReview {
                    Divider()
                    Text("Restoration review").font(.title2.bold())
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
                        }
                    }
                    Text("New sensitive workbook: \(review["output"] as? String ?? "")")
                    Button("Authorise local restoration") { showAuthorise = true }
                        .buttonStyle(.borderedProminent)
                    Button("Cancel review") { model.cancelReview() }
                }
            }.padding(28).frame(maxWidth: 850, alignment: .leading)
        }
        .confirmationDialog("Create a new locally reidentified workbook?",
                            isPresented: $showAuthorise) {
            Button("Authorise restoration") { model.approveRestoration() }
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
                Text("Advanced tools").font(.largeTitle.bold())
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
                            Button("Inspect") { model.inspect() }
                        }
                        PathRow(title: "Policy", path: $model.legacyPolicy,
                                save: false, fileExtension: "yaml")
                        HStack {
                            Button("Load policy choices") { model.loadPolicy() }
                            Button("Review and edit fields") { model.page = .protect }
                            Button("Save revised policy…") {
                                if let url = chooseSave(extension: "yaml") {
                                    model.savePolicy(url.path)
                                }
                            }
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
                        if let review = model.legacyReview,
                           let validation = review["validation"] as? [String: Any] {
                            Text("\(review["rows"] as? Int ?? 0) records. Validation: \((validation["passed"] as? Bool == true) ? "passed" : "blocked")")
                            Text("Export: \(review["output"] as? String ?? "")")
                            Text("Private map: \(review["map"] as? String ?? "")")
                            if let warnings = validation["warnings"] as? [String] {
                                ForEach(warnings, id: \.self) { Text($0) }
                            }
                            SecureField("New map passphrase", text: $secret)
                            SecureField("Confirm map passphrase", text: $confirmation)
                            Button("Approve export and create map") {
                                guard secret.count >= 16, secret == confirmation else {
                                    model.alert = "Passphrases must match and contain at least 16 characters."
                                    return
                                }
                                let value = secret; secret = ""
                                confirmation = ""
                                model.approveLegacyExport(passphrase: value)
                            }.disabled(validation["passed"] as? Bool != true)
                            Button("Cancel review") { model.cancelReview() }
                        }
                    }.padding(8)
                }
                GroupBox("Legacy selected-result restoration") {
                    VStack(alignment: .leading, spacing: 10) {
                        PathRow(title: "Returned workbook", path: $model.legacyReturned,
                                save: false, fileExtension: "xlsx")
                        Button("Read returned columns") { model.inspectLegacyReturned() }
                        ForEach(model.legacyResultColumns, id: \.self) { name in
                            Toggle(name, isOn: Binding(
                                get: { model.legacyApproved.contains(name) },
                                set: { if $0 { model.legacyApproved.insert(name) }
                                       else { model.legacyApproved.remove(name) } }
                            ))
                        }
                        PathRow(title: "New restored workbook", path: $model.restoredOutput,
                                save: true, fileExtension: "xlsx")
                        SecureField("Map passphrase", text: $secret)
                        Button("Authorise legacy restoration") {
                            let value = secret; secret = ""
                            model.restoreLegacy(passphrase: value)
                        }
                    }.padding(8)
                }
            }.padding(28).frame(maxWidth: 850, alignment: .leading)
        }
    }
}

@main struct SafeSetMacApp: App {
    @StateObject private var model = AppModel()
    var body: some Scene {
        WindowGroup { RootView().environmentObject(model) }
            .windowStyle(.titleBar)
    }
}
