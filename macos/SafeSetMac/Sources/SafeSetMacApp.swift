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
let retainedInformationOptions: [(String, String)] = [
    ("Information useful for the analysis", "analytical_attribute"),
    ("Information about the person or group that could distinguish them", "quasi_identifier"),
    ("I'm not sure", "")
]

func plainLanguageSuggestion(_ classification: String) -> String {
    switch classification {
    case "direct_identifier":
        return "This field may directly identify a person and would normally be removed or used as the one linking identifier."
    case "quasi_identifier":
        return "This field may distinguish a person or small group when combined with other information."
    case "analytical_attribute":
        return "This field may be useful for the analysis, but keeping it still contributes to disclosure risk."
    case "free_text":
        return "This looks like free text and would normally be removed because SafeSet does not redact it."
    case "pseudonymous_identifier":
        return "This looks like an existing identifier and should not be treated as automatically safe."
    default:
        return "SafeSet is not confident about this field. Choose based on its meaning and the intended analysis."
    }
}

let restorationAnalysisGuidance = "Please analyse the protected Excel workbook and return a modified .xlsx file that SafeSet can restore. Use the protected workbook as the base. Preserve every original worksheet, row, heading, record_id, entity_id and protected value exactly, including heading spelling and case. Keep each original record_id exactly once on its original worksheet. You may reorder columns and add new result columns anywhere, or add separate analysis worksheets. Give new result columns unique headings and do not change protected values. Do not request the original source, private bundle or passphrase."
let restorationResultExample = "For each new result column on a protected worksheet, give every row a short value such as Campus mismatch or No change; blank result cells are not supported. Do not put formulas in protected worksheets. Added analysis worksheets may contain blank cells; use static values where possible. If they contain formulas, the workbook must include saved scalar results. Before returning the file, compare each protected worksheet's row count and exact record_id values with the input workbook; every original ID must appear once on the same worksheet, with no new IDs in protected worksheets. SafeSet copies approved results into static tables, so formulas, formatting and drawings are not preserved. If you cannot keep the original workbook intact, explain the limitation instead of returning a changed file."
let restorationCopyText = "\(restorationAnalysisGuidance)\n\n\(restorationResultExample)"

func copyRestorationPrompt() {
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(restorationCopyText, forType: .string)
}

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
                if field.action == "drop" {
                    Text("Removed").foregroundStyle(.secondary)
                } else {
                    Text(metadata ?? "\(field.type) · \(field.cardinality) values")
                        .foregroundStyle(.secondary)
                }
                Button {
                    if field.action == "drop" {
                        field.action = ""
                    } else {
                        field.action = "drop"
                        field.classification = ""
                    }
                } label: {
                    Image(systemName: field.action == "drop" ? "arrow.uturn.backward" : "xmark")
                        .font(.system(size: 11, weight: .semibold))
                        .frame(width: 28, height: 28)
                        .background(.quaternary, in: Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(field.action == "drop" ? "Undo remove" : "Remove field")
                .help(field.action == "drop" ? "Undo removal of this field" : "Remove this field")
            }
            if let scope {
                Text(scope).appFont(12).foregroundStyle(.secondary)
            }
            if field.action != "drop" {
                if field.blankCount > 0 {
                    Label(
                        "\(field.blankCount) blank or whitespace-only cells",
                        systemImage: "exclamationmark.triangle.fill"
                    )
                    .appFont(13)
                    .foregroundStyle(.red)
                }
                HStack {
                    Picker("Appearance", selection: Binding(
                        get: { field.action },
                        set: { action in
                            field.action = action
                            if action == "pseudonymise" {
                                field.classification = "direct_identifier"
                            } else if action == "drop" {
                                field.classification = ""
                            } else if !["quasi_identifier", "analytical_attribute"]
                                .contains(field.classification) {
                                field.classification = ""
                            }
                        }
                    )) {
                        Text("Choose…").tag("")
                        ForEach(actionOptions, id: \.1) { item in Text(item.0).tag(item.1) }
                    }
                    .appFont(13)
                    if ["keep", "code", "bin", "keep_numeric"].contains(field.action) {
                        Picker("Why keep this field?", selection: $field.classification) {
                            ForEach(retainedInformationOptions, id: \.1) { item in
                                Text(item.0).tag(item.1)
                            }
                        }
                        .appFont(13)
                    }
                }
                if field.action == "pseudonymise" {
                    Text("SafeSet will use this as the source identifier that links records. It is treated internally as a direct identifier and replaced with fresh random IDs.")
                        .appFont(12)
                        .foregroundStyle(.secondary)
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
                    Text("Local suggestion: \(plainLanguageSuggestion(field.hint))")
                    Text("This suggestion is advisory only and never permits a field to be released.")
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
        }
        .padding(14)
        .opacity(field.action == "drop" ? 0.55 : 1)
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
                Label("Protect workbook", systemImage: "tablecells")
                    .appFont(13).tag(AppModel.Page.protect)
                Label("Protect document", systemImage: "doc.text")
                    .appFont(13).tag(AppModel.Page.protectDocument)
                Label("Restore workbook", systemImage: "arrow.uturn.backward.square")
                    .appFont(13).tag(AppModel.Page.restore)
                Label("Restore document", systemImage: "arrow.uturn.backward.doc")
                    .appFont(13).tag(AppModel.Page.restoreDocument)
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
                case .protectDocument: ProtectDocumentView()
                case .restore: RestoreView()
                case .restoreDocument: RestoreDocumentView()
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
        .sheet(isPresented: $model.showAnalysisPrompt) {
            AnalysisPromptSheet()
                .environmentObject(model)
        }
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
            Text("Create protected working copies for analysis or review, then restore approved identifiers locally.")
                .appFont(16).foregroundStyle(.secondary)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 240))], spacing: 16) {
                Button { model.page = .protect } label: {
                    Label("Protect a workbook", systemImage: "tablecells")
                        .appFont(13)
                        .frame(maxWidth: .infinity, minHeight: 92)
                }.buttonStyle(.borderedProminent)
                Button { model.page = .protectDocument } label: {
                    Label("Protect a document", systemImage: "doc.text")
                        .appFont(13)
                        .frame(maxWidth: .infinity, minHeight: 92)
                }.buttonStyle(.borderedProminent)
                Button { model.page = .restore } label: {
                    Label("Restore a workbook", systemImage: "arrow.uturn.backward.square")
                        .appFont(13)
                        .frame(maxWidth: .infinity, minHeight: 92)
                }.buttonStyle(.bordered)
                Button { model.page = .restoreDocument } label: {
                    Label("Restore a document", systemImage: "arrow.uturn.backward.doc")
                        .appFont(13)
                        .frame(maxWidth: .infinity, minHeight: 92)
                }.buttonStyle(.bordered)
            }
            if model.hasRecentProtectedWorkbook {
                GroupBox("Before using ChatGPT") {
                    HStack(alignment: .center, spacing: 16) {
                        Text("Send the protected workbook with the preservation prompt. Keep the original source, private bundle and passphrase local.")
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Button("View and copy prompt") { model.showAnalysisPrompt = true }
                            .buttonStyle(.bordered)
                    }
                    .padding(.vertical, 6)
                }
            }
            Text("Passing checks reduces some disclosure risks. It does not establish anonymity or recipient suitability.")
                .foregroundStyle(.secondary)
            Spacer()
        }
        .padding(28)
    }
}

struct AnalysisPromptSheet: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Protected workbook created").appFont(20, weight: .bold)
            Text("Before sending it to ChatGPT, copy this prompt and include it with the exact protected workbook. Keep the original source, private bundle and passphrase local.")
            ScrollView {
                Text(restorationCopyText)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12)
            }
            .background(.quaternary.opacity(0.35), in: RoundedRectangle(cornerRadius: 8))
            HStack {
                Spacer()
                Button("Done") { model.showAnalysisPrompt = false }
                Button("Copy prompt") { copyRestorationPrompt() }
                    .buttonStyle(.borderedProminent)
            }
        }
        .padding(24)
        .frame(width: 650, height: 470)
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

struct ProtectDocumentView: View {
    @EnvironmentObject var model: AppModel
    @State private var identities = ""
    @State private var passphrase = ""
    @State private var confirmation = ""
    @State private var showApproval = false
    @State private var removeComments = true

    private var terms: [String] {
        identities.components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Protect a document").appFont(26, weight: .bold)
                Text("Prepare a DOCX manuscript for external review or AI-assisted work. SafeSet automatically protects email addresses and ORCID identifiers; add known names or other identities below.")
                    .foregroundStyle(.secondary)
                PathRow(title: "Original document", path: $model.documentSource,
                        save: false, fileExtension: "docx") { model.chooseDocumentSource($0) }

                if let inspection = model.documentInspection {
                    GroupBox("Local document inspection") {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Emails found: \(inspection["email_count"] as? Int ?? 0)")
                            Text("ORCID identifiers found: \(inspection["orcid_count"] as? Int ?? 0)")
                            Text("Comments: \(inspection["comments"] as? Int ?? 0)")
                            Text("Tracked changes: \(inspection["tracked_changes"] as? Int ?? 0)")
                            Text("Hidden text markers: \(inspection["hidden_text"] as? Int ?? 0)")
                            Text("Embedded/active objects: \(inspection["embedded_objects"] as? Int ?? 0)")
                            Text("Authoring metadata fields: \(inspection["metadata_fields"] as? Int ?? 0)")
                            if let blockers = inspection["blockers"] as? [String], !blockers.isEmpty {
                                Text("Resolve before protection: \(blockers.joined(separator: ", "))")
                                    .foregroundStyle(.red)
                            }
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }
                }

                Text("Known names or identifiers to protect").appFont(18, weight: .bold)
                TextEditor(text: $identities)
                    .font(.system(size: 13))
                    .frame(minHeight: 120)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(.quaternary))
                Text("One value per line. SafeSet performs exact local matching; this list is never returned through the desktop bridge.")
                    .appFont(12).foregroundStyle(.secondary)
                Toggle("Remove Word comments from the protected copy", isOn: $removeComments)
                    .toggleStyle(.checkbox)

                PathRow(title: "Protected document", path: $model.documentProtectedOutput,
                        save: true, fileExtension: "docx")
                DisclosureGroup("Advanced settings") {
                    PathRow(title: "Private bundle location", path: $model.documentBundleOutput,
                            save: true, fileExtension: "enc")
                }
                Button("Review document protection") {
                    model.prepareDocumentProtection(terms: terms, removeComments: removeComments)
                }
                .buttonStyle(.borderedProminent)

                if let review = model.documentProtectionReview {
                    Divider()
                    Text("Final review").appFont(18, weight: .bold)
                    Text("Protected identities: \(review["replacement_count"] as? Int ?? 0)")
                    Text("Protected occurrences: \(review["replacement_occurrences"] as? Int ?? 0)")
                    Text("Comments removed: \((review["comments_removed"] as? Bool) == true ? "yes" : "no")")
                    Text("Protected copy: \(review["output"] as? String ?? "")")
                    Text("Private restoration bundle: \(review["bundle"] as? String ?? "")")
                    Text("This review reduces some disclosure risks; it does not certify anonymity or recipient suitability.")
                        .foregroundStyle(.secondary)
                    Button("Approve and create") { showApproval = true }
                        .buttonStyle(.borderedProminent)
                    Button("Cancel review") { model.cancelReview() }
                }
            }
            .padding(28)
            .frame(maxWidth: 850, alignment: .leading)
        }
        .sheet(isPresented: $showApproval) {
            VStack(alignment: .leading, spacing: 14) {
                Text("Approve document protection").appFont(18, weight: .bold)
                SecureField("Restoration passphrase", text: $passphrase)
                SecureField("Confirm passphrase", text: $confirmation)
                HStack {
                    Button("Cancel") {
                        showApproval = false; passphrase = ""; confirmation = ""
                    }
                    Button("Create") {
                        guard passphrase.count >= 16, passphrase == confirmation else {
                            model.alert = "Passphrases must match and contain at least 16 characters."
                            return
                        }
                        let secret = passphrase
                        passphrase = ""; confirmation = ""; showApproval = false
                        model.approveDocumentProtection(passphrase: secret)
                    }.buttonStyle(.borderedProminent)
                }
            }.padding(24).frame(width: 430)
        }
    }
}


struct RestoreDocumentView: View {
    @EnvironmentObject var model: AppModel
    @State private var passphrase = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Restore a document").appFont(26, weight: .bold)
                Text("Restore SafeSet protection tokens in a returned DOCX. The returned document must preserve every token exactly; SafeSet never guesses missing identities.")
                    .foregroundStyle(.secondary)
                PathRow(title: "Modified protected document", path: $model.documentReturned,
                        save: false, fileExtension: "docx")
                PathRow(title: "Private restoration bundle", path: $model.documentRestoreBundle,
                        save: false, fileExtension: "enc")
                PathRow(title: "Restored document", path: $model.documentRestoredOutput,
                        save: true, fileExtension: "docx")
                SecureField("Bundle passphrase", text: $passphrase)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 420)
                Button("Review restoration") {
                    let secret = passphrase
                    passphrase = ""
                    model.prepareDocumentRestoration(passphrase: secret)
                }.buttonStyle(.borderedProminent)

                if let review = model.documentRestorationReview {
                    Divider()
                    Text("Restoration review").appFont(18, weight: .bold)
                    Text("Identifiers to restore: \(review["replacement_count"] as? Int ?? 0)")
                    Text("Protected occurrences: \(review["replacement_occurrences"] as? Int ?? 0)")
                    Text("New local document: \(review["output"] as? String ?? "")")
                    Button("Authorise restoration") { model.approveDocumentRestoration() }
                        .buttonStyle(.borderedProminent)
                    Button("Cancel review") { model.cancelReview() }
                }
            }
            .padding(28)
            .frame(maxWidth: 850, alignment: .leading)
        }
    }
}


struct ProtectView: View {
    @EnvironmentObject var model: AppModel
    @State private var passphrase = ""
    @State private var confirmation = ""
    @State private var showApproval = false
    @State private var showOnlyFieldsNeedingAttention = true

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Protect a workbook").appFont(26, weight: .bold)
                PathRow(title: "Original workbook", path: $model.source, save: false,
                        fileExtension: "xlsx") { model.chooseSource($0) }
                if model.sourceSheets.count > 1 {
                    GroupBox("Worksheets in the protected release") {
                        VStack(alignment: .leading) {
                            Text("Selected worksheets are protected and included in the release. Unselected worksheets are excluded, not copied through.")
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
                    Text("A repeated heading appears once and its decision applies to every listed worksheet. Sheet-specific headings remain separate. For fields you retain or transform, choose why the information is needed. Removed fields need no classification, and the linking identifier is handled automatically.")
                        .foregroundStyle(.secondary)
                    let attentionCount = model.consolidatedFields.filter {
                        model.fieldNeedsAttention($0.id)
                    }.count
                    HStack {
                        Text("\(attentionCount) of \(model.consolidatedFields.count) fields need attention")
                            .appFont(13, weight: .semibold)
                        Spacer()
                        Toggle("Show only fields needing attention",
                               isOn: $showOnlyFieldsNeedingAttention)
                            .appFont(13)
                            .toggleStyle(.checkbox)
                    }
                    if model.undecidedFieldCount > 0 {
                        Button("Remove \(model.undecidedFieldCount) undecided fields") {
                            model.removeUndecidedFields()
                        }
                        .appFont(13)
                        .disabled(!model.hasSourceKeySelections)
                        .help("Applies Remove only to fields with no action on any selected worksheet. You can show all fields to change a decision.")
                        if !model.hasSourceKeySelections {
                            Text("Choose one source identifier per worksheet before removing the undecided fields.")
                                .appFont(12)
                                .foregroundStyle(.secondary)
                        }
                    }
                    if showOnlyFieldsNeedingAttention && attentionCount == 0 {
                        Text("No fields need further input here. Show all fields to review or change them.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(model.consolidatedFields.filter {
                        !showOnlyFieldsNeedingAttention || model.fieldNeedsAttention($0.id)
                    }) { item in
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
                Toggle("Multi-sheet relational bundle", isOn: Binding(
                    get: { model.relationalRestore },
                    set: { model.relationalRestore = $0; model.invalidate() }
                ))
                    .appFont(13)
                Text(model.relationalRestore
                     ? "The private bundle defines every required worksheet. SafeSet includes those automatically and presents added analysis worksheets separately for approval."
                     : "Restore one or more same-schema worksheets from a version 2 bundle.")
                    .foregroundStyle(.secondary)
                GroupBox("Returning analysis findings") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(restorationAnalysisGuidance)
                        Text(restorationResultExample)
                        Button("Copy prompt") {
                            copyRestorationPrompt()
                        }
                        .buttonStyle(.bordered)
                        .foregroundStyle(.primary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .foregroundStyle(.secondary)
                }
                PathRow(title: "Modified protected copy", path: $model.returned,
                        save: false, fileExtension: "xlsx") {
                    model.chooseRestoreFile($0, sourceFile: false)
                }
                if model.relationalRestore, !model.returned.isEmpty {
                    Text("No worksheet selection is needed. Required worksheets are verified against the private bundle after it is unlocked; unexpected hidden worksheets are rejected.")
                        .appFont(12)
                        .foregroundStyle(.secondary)
                }
                if !model.relationalRestore && model.returnedSheets.count > 1 {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Protected worksheets")
                            .appFont(13, weight: .semibold)
                        ForEach(model.returnedSheets, id: \.self) { sheet in
                            Toggle(sheet, isOn: Binding(
                                get: { model.selectedReturnedSheets.contains(sheet) },
                                set: { selected in
                                    if selected { model.selectedReturnedSheets.insert(sheet) }
                                    else { model.selectedReturnedSheets.remove(sheet) }
                                    model.invalidate()
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
                                    model.invalidate()
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
                HStack {
                    Button("Validate and review") {
                        let secret = passphrase; passphrase = ""
                        model.prepareRestoration(passphrase: secret)
                    }.appFont(13).buttonStyle(.borderedProminent)
                    Button("Locate unsafe source cells") {
                        let secret = passphrase; passphrase = ""
                        model.locateUnsafeSourceCells(passphrase: secret)
                    }.appFont(13).buttonStyle(.bordered)
                }
                if let count = model.unsafeSourceCount {
                    Text("Unsafe source cells: \(count)").appFont(13, weight: .semibold)
                    ForEach(model.unsafeSourceLocations) { location in
                        Text("\(location.sheet) — \(location.cell)").appFont(13)
                    }
                    if count > model.unsafeSourceLocations.count {
                        Text("Showing the first 20 locations.")
                            .appFont(12).foregroundStyle(.secondary)
                    }
                    Text("Only worksheet names and cell coordinates are shown; no cell values are copied or logged.")
                        .appFont(12).foregroundStyle(.secondary)
                }
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
