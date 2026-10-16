import XCTest
import AppKit
@testable import SafeSetMac

final class SafeSetMacTests: XCTestCase {
    @MainActor func testNewResultPromptAndApprovalGates() {
        let model = AppModel()
        model.resultWorkbookPrompt = true
        model.analysisTaskInstructions = "Assign Team using Subject Campus."
        XCTAssertTrue(model.copyableAnalysisPrompt.contains("new result .xlsx workbook"))
        XCTAssertTrue(model.copyableAnalysisPrompt.contains("new team labels are allowed"))
        XCTAssertTrue(model.copyableAnalysisPrompt.contains("Assign Team using Subject Campus."))
        model.acceptRestorationReview([
            "review_id": "synthetic-result-review", "result_workbook": true, "ready": true,
            "sheets": [
                "New Allocations": ["rows": 3, "linked": true,
                                    "result_fields": ["Team", "Role"],
                                    "new_categories": ["Team": 1]],
                "Team Summary": ["rows": 2, "linked": false,
                                 "result_fields": ["Team", "Count"],
                                 "new_categories": [String: Int]()]
            ]
        ])
        XCTAssertTrue(model.canApproveRestoration)
        model.restorationReview?["ready"] = false
        XCTAssertFalse(model.canApproveRestoration)
        model.restorationReview?["ready"] = true
        model.resultConfigurationChanged()
        XCTAssertFalse(model.canApproveRestoration)
        model.resultConfigChanged = false
        model.restorationReview?.removeValue(forKey: "review_id")
        XCTAssertFalse(model.canApproveRestoration)
    }

    @MainActor func testResultJoinsIncludeOnlySelectedSourceFields() {
        let model = AppModel()
        model.resultJoinSources = ["New Allocations": "Updated Classlist"]
        model.resultJoinFields = ["New Allocations": ["Student key", "Course"]]
        let join = model.resultJoins["New Allocations"] as? [String: Any]
        XCTAssertEqual(join?["source_sheet"] as? String, "Updated Classlist")
        XCTAssertEqual(join?["source_fields"] as? [String], ["Course", "Student key"])
        XCTAssertEqual(join?["join_by"] as? String, "entity_id")
        XCTAssertEqual(join?["unique_entities"] as? Bool, true)
    }

    @MainActor func testTaskInstructionsDoNotReplaceWorkbookPermissions() {
        let model = AppModel()
        model.latestAnalysisPrompt = "Synthetic protected-workbook permissions."
        model.analysisTaskInstructions = "  Fill existing teams first, then request a new team.  "
        let prompt = model.copyableAnalysisPrompt
        XCTAssertTrue(prompt.hasPrefix("Synthetic protected-workbook permissions."))
        XCTAssertTrue(prompt.contains("Fill existing teams first, then request a new team."))
        XCTAssertTrue(prompt.contains("Do not invent a code"))
        model.analysisTaskInstructions = "  \n  "
        XCTAssertEqual(model.copyableAnalysisPrompt, model.latestAnalysisPrompt)
    }

    #if DEBUG
    func testDevelopmentPassphraseAcceptsOnlyExactSyntheticFixture() throws {
        let repository = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let fixture = repository.appendingPathComponent("examples/synthetic_participants.xlsx")
        XCTAssertNotNil(DevelopmentPassphrase.forWorkbook(fixture.path))
        let changed = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString + ".xlsx")
        defer { try? FileManager.default.removeItem(at: changed) }
        var bytes = try Data(contentsOf: fixture)
        bytes.append(0)
        try bytes.write(to: changed)
        XCTAssertNil(DevelopmentPassphrase.forWorkbook(changed.path))
    }
    #endif

    @MainActor func testParticipantChangesNeedReadyReviewAndSeparateApprovals() {
        let model = AppModel()
        model.relationalRestore = true
        model.acceptRestorationReview([
            "review_id": "synthetic-participant-review", "reconciliation": true,
            "ready": false, "additions": 22, "removals": 1,
            "new_columns": ["Allocations": [String](), "Participants": [String]()],
            "changes": ["Allocations": ["Team": 1], "Participants": [String: Int]()]
        ])
        model.approvedChanges = ["Allocations": ["Team"]]
        model.approvedParticipantAdditions = true
        model.approvedParticipantRemovals = true
        XCTAssertFalse(model.canApproveRestoration)
        model.restorationReview?["ready"] = true
        XCTAssertTrue(model.canApproveRestoration)
        model.approvedParticipantRemovals = false
        XCTAssertFalse(model.canApproveRestoration)
        model.approvedParticipantRemovals = true
        model.participantConfigurationChanged()
        XCTAssertFalse(model.canApproveRestoration)
        XCTAssertFalse(model.approvedParticipantAdditions)
        XCTAssertFalse(model.approvedParticipantRemovals)
        XCTAssertTrue(model.approvedChanges.isEmpty)
    }

    @MainActor func testParticipantMappingsDistinguishMissingBlankAndReferenceFields() {
        let model = AppModel()
        model.participantMappings = [
            "Synthetic name": "column:Name", "Role": "source:Synthetic Roles\u{1F}Role", "Note": "blank", "Other": ""
        ]
        let mappings = model.participantConfig["column_sources"] as? [String: Any]
        XCTAssertEqual(mappings?["Synthetic name"] as? String, "Name")
        let role = mappings?["Role"] as? [String: String]
        XCTAssertEqual(role?["sheet"], "Synthetic Roles")
        XCTAssertEqual(role?["column"], "Role")
        XCTAssertTrue(mappings?["Note"] is NSNull)
        XCTAssertNil(mappings?["Other"])
    }

    @MainActor func testEditableFieldsAreScopedToSheetsAndReversibleActions() {
        let model = AppModel()
        model.sourceSheet = "Allocations"
        model.selectedSourceSheets = ["Allocations", "Participants"]
        var team = FieldDraft(id: "Synthetic team")
        team.action = "code"
        var identifier = FieldDraft(id: "Synthetic key")
        identifier.action = "pseudonymise"
        var grouped = FieldDraft(id: "Synthetic band")
        grouped.action = "bin"
        model.fields = [team, identifier, grouped]
        model.fieldsBySheet["Participants"] = [team, identifier]
        model.editableFields["Allocations"] = [team.id, identifier.id, grouped.id]
        XCTAssertEqual(model.editingPermissions["Allocations"], [team.id])
        XCTAssertEqual(model.editingPermissions["Participants"], [])
        team.action = "drop"
        model.fields = [team, identifier, grouped]
        XCTAssertEqual(model.editingPermissions["Allocations"], [])
    }

    @MainActor func testChangedFieldsRequireSeparateExplicitApproval() {
        let model = AppModel()
        model.relationalRestore = true
        model.restorationReview = [
            "review_id": "synthetic-token",
            "new_columns": ["Allocations": [String](), "Participants": [String]()],
            "changes": ["Allocations": ["Team": 2], "Participants": [String: Int]()]
        ]
        XCTAssertFalse(model.canApproveRestoration)
        model.approvedChanges = ["Allocations": ["Team"]]
        XCTAssertTrue(model.canApproveRestoration)
        model.approvedChanges["Allocations"]?.insert("Unexpected")
        XCTAssertFalse(model.canApproveRestoration)
        model.approvedChanges = ["Allocations": ["Team"], "Participants": ["Team"]]
        XCTAssertFalse(model.canApproveRestoration)
    }

    func testHelpIsAnExplicitNavigationDestination() {
        XCTAssertEqual(AppModel.Page.help.rawValue, "help")
    }

    func testHelpMarkdownPreservesBlockStructure() {
        let blocks = parseHelpMarkdown("""
        # Guide

        A **safe** paragraph.

        1. First step
        2. Second step

        | Field | Action |
        | --- | --- |
        | Name | Remove |

        ```pwsh
        Get-Help SafeSet
        ```
        """)
        XCTAssertEqual(blocks.count, 5)
        if case .heading(1, "Guide") = blocks[0].kind {} else {
            XCTFail("Expected a level-one heading")
        }
        if case .list(true, let items) = blocks[2].kind {
            XCTAssertEqual(items, ["First step", "Second step"])
        } else { XCTFail("Expected an ordered list") }
        if case .table(let headers, let rows) = blocks[3].kind {
            XCTAssertEqual(headers, ["Field", "Action"])
            XCTAssertEqual(rows, [["Name", "Remove"]])
        } else { XCTFail("Expected a table") }
        if case .code("Get-Help SafeSet") = blocks[4].kind {} else {
            XCTFail("Expected a code block")
        }
    }

    func testFieldDraftDefaultsRequireExplicitDecisions() {
        let draft = FieldDraft(id: "Invented Field")
        XCTAssertEqual(draft.action, "")
        XCTAssertEqual(draft.classification, "")
        XCTAssertEqual(draft.payload()["allowed_values"] as? [String], [])
        XCTAssertNil(draft.payload()["max_decimal_places"])
    }

    func testActionNamesMapToStrictPolicyActions() {
        XCTAssertEqual(actionOptions.map(\.1), [
            "drop", "pseudonymise", "code", "keep", "review_text", "bin", "keep_numeric"
        ])
        XCTAssertEqual(actionOptions.first { $0.1 == "keep" }?.0, "Keep short categories unchanged")
        XCTAssertEqual(actionOptions.first { $0.1 == "review_text" }?.0, "Review and redact text")
    }

    @MainActor func testLongTextNeedsIndividualReviewAndStaysReferenceOnly() {
        let model = AppModel()
        model.source = "/synthetic/local-workbook.xlsx"
        model.sourceSheet = "Synthetic"
        model.selectedSourceSheets = ["Synthetic"]
        var key = FieldDraft(id: "Synthetic key")
        key.action = "pseudonymise"
        var text = FieldDraft(id: "Journal response")
        text.action = "review_text"
        XCTAssertTrue(text.needsAttention)
        XCTAssertEqual(text.payload()["classification"] as? String, "free_text")
        model.fields = [key, text]
        model.fieldsBySheet = ["Synthetic": model.fields]
        XCTAssertFalse(model.canPrepareProtection)
        XCTAssertTrue(model.editableCandidates("Synthetic").isEmpty)
        var entry = TextReviewEntry(
            sheet: "Synthetic", digest: String(repeating: "a", count: 64),
            original: "A synthetic journal paragraph.", count: 1, text: "Reviewed paragraph."
        )
        let review = TextReviewSheet(source: model.source, field: text.id, entries: [entry])
        model.acceptTextReview(review, entries: [entry])
        XCTAssertTrue(model.fields[1].textReviews.isEmpty)
        entry.reviewed = true
        entry.edit("An edited paragraph.")
        XCTAssertFalse(entry.reviewed)
        entry.reviewed = true
        model.acceptTextReview(review, entries: [entry])
        XCTAssertFalse(model.fields[1].needsAttention)
        XCTAssertTrue(model.canPrepareProtection)
        XCTAssertEqual(model.fields[1].textReviews[entry.digest], "An edited paragraph.")
        XCTAssertTrue(model.editableCandidates("Synthetic").isEmpty)
        model.source = "/synthetic/different-workbook.xlsx"
        entry.text = "Should not replace the old approval."
        model.acceptTextReview(review, entries: [entry])
        XCTAssertEqual(model.fields[1].textReviews[entry.digest], "An edited paragraph.")
        var removed = model.fields[1]
        removed.action = "drop"
        model.updateConsolidatedField(text.id, with: removed)
        XCTAssertTrue(model.fields[1].textReviews.isEmpty)
    }

    @MainActor func testTextRejectionFeedbackIsVisibleWithoutLosingReviewState() {
        let digest = String(repeating: "a", count: 64)
        let feedback = TextReviewFeedback.decode([
            digest: ["email", "known_identifier", "unexpected source text"],
            "": ["source_changed"], "not-a-binding": ["email"]
        ])
        XCTAssertEqual(feedback[digest]?.count, 2)
        XCTAssertNil(feedback["not-a-binding"])
        XCTAssertFalse(feedback.values.flatMap { $0 }.contains("unexpected source text"))
        let model = AppModel()
        let entry = TextReviewEntry(
            sheet: "Synthetic", digest: digest, original: "A synthetic paragraph.",
            count: 1, text: "Edited synthetic paragraph.", reviewed: true
        )
        let review = TextReviewSheet(source: "/synthetic.xlsx", field: "Journal", entries: [entry])
        model.textReviewSheet = review
        model.showTextReviewIssues(feedback, sheet: "Synthetic")
        XCTAssertFalse(model.textReviewMessage.isEmpty)
        XCTAssertEqual(model.textReviewIssues[entry.id]?.count, 2)
        XCTAssertEqual(model.textReviewIssues[""]?.count, 1)
        XCTAssertEqual(model.textReviewSheet?.id, review.id)
        XCTAssertEqual(model.textReviewSheet?.entries[0].text, entry.text)
        XCTAssertEqual(model.textReviewSheet?.entries[0].reviewed, true)
        var edited = entry
        edited.edit(entry.text)
        XCTAssertTrue(edited.reviewed)
        edited.edit("A different synthetic paragraph.")
        XCTAssertFalse(edited.reviewed)
        model.busy = true
        model.approveText(review, entries: [entry])
        XCTAssertFalse(model.textReviewIssues.isEmpty)
    }

    @MainActor func testIssueHighlightsDecorateExactTextAndIgnoreStaleOrInvalidRanges() {
        let text = "🧪 Synthetic Ada wrote a fictional response."
        let range = (text as NSString).range(of: "Synthetic Ada")
        let mark = TextReviewHighlight(reason: "known_identifier", start: range.location,
                                       end: NSMaxRange(range))
        XCTAssertTrue(mark.valid(in: text))
        XCTAssertFalse(TextReviewHighlight(reason: "email", start: 0, end: 1).valid(in: text))
        let editor = NSTextView()
        editor.string = text
        ReviewedTextEditor.applyHighlights([mark], to: editor)
        XCTAssertNotNil(editor.layoutManager?.temporaryAttribute(
            .backgroundColor, atCharacterIndex: range.location, effectiveRange: nil
        ))
        XCTAssertNil(editor.layoutManager?.temporaryAttribute(
            .backgroundColor, atCharacterIndex: 0, effectiveRange: nil
        ))
        XCTAssertEqual(editor.string, text)
        ReviewedTextEditor.applyHighlights([], to: editor)
        XCTAssertNil(editor.layoutManager?.temporaryAttribute(
            .backgroundColor, atCharacterIndex: range.location, effectiveRange: nil
        ))
        let digest = String(repeating: "a", count: 64)
        let model = AppModel()
        var entry = TextReviewEntry(sheet: "Synthetic", digest: digest, original: text,
                                    count: 1, text: text)
        model.showTextReviewIssues([digest: ["A fixed warning."]], sheet: "Synthetic",
                                  highlights: [digest: [mark]], checkedText: [digest: text])
        XCTAssertEqual(model.highlights(for: entry), [mark])
        entry.edit("A changed synthetic paragraph.")
        XCTAssertTrue(model.highlights(for: entry).isEmpty)
        XCTAssertTrue(model.issueMessages(for: entry).isEmpty)
        let decoded = TextReviewFeedback.decodeHighlights([digest: [
            ["reason": "email", "start": 3, "end": 5],
            ["reason": "email", "start": -1, "end": 5],
            ["reason": "untrusted text", "start": 0, "end": 2]
        ]])
        XCTAssertEqual(decoded[digest]?.count, 1)
        let decomposed = "e\u{301} Synthetic Ada"
        let composed = "é Synthetic Ada"
        var unicodeEntry = TextReviewEntry(sheet: "Synthetic", digest: digest,
                                           original: decomposed, count: 1,
                                           text: decomposed, reviewed: true)
        model.showTextReviewIssues([digest: ["A fixed warning."]], sheet: "Synthetic",
                                  highlights: [digest: [mark]], checkedText: [digest: decomposed])
        unicodeEntry.edit(composed)
        XCTAssertFalse(unicodeEntry.reviewed)
        XCTAssertTrue(model.highlights(for: unicodeEntry).isEmpty)
        model.closeTextReview()
        XCTAssertTrue(model.textReviewCheckedText.isEmpty)
        XCTAssertTrue(model.textReviewHighlights.isEmpty)
    }

    func testFieldActionsHideTechnicalClassificationAndBuildSafePayloads() {
        var identifier = FieldDraft(id: "Invented source key")
        identifier.action = "pseudonymise"
        XCTAssertFalse(identifier.needsAttention)
        XCTAssertEqual(identifier.payload()["classification"] as? String, "direct_identifier")

        var removed = FieldDraft(id: "Invented removed field")
        removed.action = "drop"
        XCTAssertFalse(removed.needsAttention)
        XCTAssertEqual(removed.payload()["classification"] as? String, "unknown")

        var uncertain = FieldDraft(id: "Invented retained field")
        uncertain.action = "keep"
        uncertain.classification = ""
        uncertain.allowedValues = ["Synthetic A", "Synthetic B"]
        XCTAssertTrue(uncertain.needsAttention)
        XCTAssertEqual(retainedInformationOptions.last?.0, "I'm not sure")
        XCTAssertEqual(retainedInformationOptions.last?.1, "")
    }

    func testRestorationGuidancePreservesProtectedLinkageAndUsesPopulatedResults() {
        XCTAssertTrue(restorationAnalysisGuidance.contains("record_id"))
        XCTAssertTrue(restorationAnalysisGuidance.contains("entity_id"))
        XCTAssertTrue(restorationAnalysisGuidance.contains("reorder columns"))
        XCTAssertTrue(restorationAnalysisGuidance.contains("new result columns anywhere"))
        XCTAssertTrue(restorationAnalysisGuidance.contains("unique headings"))
        XCTAssertTrue(restorationAnalysisGuidance.contains("change protected values"))
        XCTAssertTrue(restorationResultExample.contains("No change"))
        XCTAssertTrue(restorationResultExample.contains("blank result cells are not supported"))
        XCTAssertTrue(restorationResultExample.contains("exact record_id values"))
        XCTAssertTrue(restorationResultExample.contains("no new IDs"))
        XCTAssertTrue(restorationResultExample.contains("Do not merge cells"))
        XCTAssertTrue(restorationResultExample.contains("at most four words and 64 characters"))
    }

    @MainActor func testWizardDecisionAndReviewGates() {
        let model = AppModel()
        var field = FieldDraft(id: "Synthetic ID")
        model.fields = [field]
        XCTAssertFalse(model.canPrepareProtection)
        field.action = "drop"
        model.fields = [field]
        XCTAssertFalse(model.canPrepareProtection)
        field.action = "pseudonymise"
        model.fields = [field]
        XCTAssertTrue(model.canPrepareProtection)

        model.restorationReview = ["review_id": "synthetic-token", "new_columns": ["Team"]]
        XCTAssertFalse(model.canApproveRestoration)
        model.approvedResults.insert("Team")
        XCTAssertTrue(model.canApproveRestoration)
        model.restorationReview?["new_sheets"] = ["Changes"]
        XCTAssertFalse(model.canApproveRestoration)
        model.approvedSheets.insert("Changes")
        XCTAssertTrue(model.canApproveRestoration)
        model.invalidate()
        XCTAssertFalse(model.canApproveRestoration)
        XCTAssertNil(model.protectionReview)
    }

    @MainActor func testSharedCodeCandidatesRequireMatchingCodedHeadings() {
        let model = AppModel()
        model.selectedSourceSheets = ["Synthetic A", "Synthetic B"]
        model.sourceSheet = "Synthetic A"
        var first = FieldDraft(id: "Cohort")
        first.action = "code"
        var second = FieldDraft(id: "Cohort")
        second.action = "code"
        var unrelated = FieldDraft(id: "Campus")
        unrelated.action = "code"
        model.fields = [first, unrelated]
        model.fieldsBySheet["Synthetic B"] = [second]

        XCTAssertEqual(model.sharedCodeCandidates, ["Cohort"])
    }

    @MainActor func testConsolidatedFieldsShowRepeatedHeadingsOnceAndPropagateDecisions() {
        let model = AppModel()
        model.sourceSheets = ["Synthetic A", "Synthetic B"]
        model.selectedSourceSheets = ["Synthetic A", "Synthetic B"]
        model.sourceSheet = "Synthetic A"
        var sharedA = FieldDraft(id: "Cohort")
        sharedA.type = "categorical"
        sharedA.cardinality = 3
        let onlyA = FieldDraft(id: "Tutorial")
        var sharedB = FieldDraft(id: "Cohort")
        sharedB.type = "categorical"
        sharedB.cardinality = 4
        let onlyB = FieldDraft(id: "Placement")
        model.fieldsBySheet = [
            "Synthetic A": [sharedA, onlyA],
            "Synthetic B": [sharedB, onlyB]
        ]
        model.fields = [sharedA, onlyA]

        XCTAssertEqual(model.consolidatedFields.map(\.id), ["Cohort", "Tutorial", "Placement"])
        XCTAssertEqual(model.consolidatedFields[0].sheets, ["Synthetic A", "Synthetic B"])
        XCTAssertEqual(model.consolidatedFields[1].sheets, ["Synthetic A"])
        XCTAssertEqual(model.consolidatedFields[2].sheets, ["Synthetic B"])

        var decision = model.consolidatedFields[0].draft
        decision.action = "code"
        decision.classification = "quasi_identifier"
        model.updateConsolidatedField("Cohort", with: decision)
        XCTAssertEqual(model.fieldsBySheet["Synthetic A"]?[0].action, "code")
        XCTAssertEqual(model.fieldsBySheet["Synthetic B"]?[0].action, "code")
        XCTAssertEqual(model.fieldsBySheet["Synthetic A"]?[0].classification, "quasi_identifier")
        XCTAssertEqual(model.fieldsBySheet["Synthetic B"]?[0].classification, "quasi_identifier")
    }

    @MainActor func testConsolidatedCategoryApprovalPreservesPerSheetAllowlists() {
        let model = AppModel()
        model.sourceSheet = "Synthetic A"
        model.sourceSheets = ["Synthetic A", "Synthetic B"]
        model.selectedSourceSheets = ["Synthetic A", "Synthetic B"]
        var shared = FieldDraft(id: "Cohort")
        shared.action = "code"
        shared.classification = "quasi_identifier"
        model.fieldsBySheet = ["Synthetic A": [shared], "Synthetic B": [shared]]
        model.fields = [shared]
        let category = CategorySheet(
            field: "Cohort",
            sheets: ["Synthetic A", "Synthetic B"],
            action: "code",
            values: ["Alpha", "Beta"],
            valuesBySheet: ["Synthetic A": ["Alpha"], "Synthetic B": ["Beta"]],
            blankCount: 0
        )

        model.approveCategories(category)

        XCTAssertEqual(model.fieldsBySheet["Synthetic A"]?[0].allowedValues, ["Alpha"])
        XCTAssertEqual(model.fieldsBySheet["Synthetic B"]?[0].allowedValues, ["Beta"])

        var decision = model.consolidatedFields[0].draft
        decision.classification = "analytical_attribute"
        model.updateConsolidatedField("Cohort", with: decision)
        XCTAssertEqual(model.fieldsBySheet["Synthetic A"]?[0].allowedValues, ["Alpha"])
        XCTAssertEqual(model.fieldsBySheet["Synthetic B"]?[0].allowedValues, ["Beta"])

        decision.action = "keep"
        model.updateConsolidatedField("Cohort", with: decision)
        XCTAssertEqual(model.fieldsBySheet["Synthetic A"]?[0].allowedValues, [])
        XCTAssertEqual(model.fieldsBySheet["Synthetic B"]?[0].allowedValues, [])
    }

    @MainActor func testRemoveUndecidedFieldsPreservesConfiguredDecisions() {
        let model = AppModel()
        model.sourceSheets = ["Synthetic A", "Synthetic B"]
        model.selectedSourceSheets = ["Synthetic A", "Synthetic B"]
        model.sourceSheet = "Synthetic A"
        var identifier = FieldDraft(id: "Invented ID")
        identifier.action = "pseudonymise"
        identifier.classification = "direct_identifier"
        var partlyConfigured = FieldDraft(id: "Cohort")
        partlyConfigured.action = "code"
        partlyConfigured.classification = "quasi_identifier"
        model.fieldsBySheet = [
            "Synthetic A": [identifier, FieldDraft(id: "Unused"), partlyConfigured],
            "Synthetic B": [identifier, FieldDraft(id: "Unused"), FieldDraft(id: "Cohort")]
        ]
        model.fields = model.fieldsBySheet["Synthetic A"]!

        XCTAssertEqual(model.undecidedFieldCount, 1)
        XCTAssertTrue(model.hasSourceKeySelections)
        model.removeUndecidedFields()

        XCTAssertEqual(model.fieldsBySheet["Synthetic A"]?[1].action, "drop")
        XCTAssertEqual(model.fieldsBySheet["Synthetic B"]?[1].action, "drop")
        XCTAssertEqual(model.fieldsBySheet["Synthetic A"]?[0].action, "pseudonymise")
        XCTAssertEqual(model.fieldsBySheet["Synthetic A"]?[2].action, "code")
        XCTAssertEqual(model.fieldsBySheet["Synthetic B"]?[2].action, "")
        XCTAssertTrue(model.fieldNeedsAttention("Cohort"))
        XCTAssertFalse(model.fieldNeedsAttention("Unused"))
    }

    @MainActor func testBulkRemovalRequiresSourceKeySelections() {
        let model = AppModel()
        model.sourceSheets = ["Synthetic A"]
        model.selectedSourceSheets = ["Synthetic A"]
        model.sourceSheet = "Synthetic A"
        model.fieldsBySheet = ["Synthetic A": [FieldDraft(id: "Invented ID")]]
        XCTAssertFalse(model.hasSourceKeySelections)
        model.removeUndecidedFields()
        XCTAssertEqual(model.fieldsBySheet["Synthetic A"]?[0].action, "")
    }

    func testFieldAttentionIncludesRequiredCategoryReview() {
        var field = FieldDraft(id: "Invented cohort")
        field.action = "keep"
        field.classification = "analytical_attribute"
        XCTAssertTrue(field.needsAttention)
        field.allowedValues = ["Example A", "Example B"]
        XCTAssertFalse(field.needsAttention)
        field.blankCount = 1
        XCTAssertTrue(field.needsAttention)
    }

    @MainActor func testRestoreWorksheetSelectionsPreserveWorkbookOrder() {
        let model = AppModel()
        model.returnedSheets = ["Later", "Earlier", "Analysis"]
        model.selectedReturnedSheets = ["Earlier", "Later"]
        model.originalSheets = ["Source B", "Source A", "Instructions"]
        model.selectedOriginalSheets = ["Source A", "Source B"]

        XCTAssertEqual(model.orderedReturnedRestoreSheets, ["Later", "Earlier"])
        XCTAssertEqual(model.orderedOriginalRestoreSheets, ["Source B", "Source A"])
    }

    @MainActor func testRecentPrivateBundlePathIsRememberedAndCanBeForgotten() throws {
        let suite = "org.ozyjay.SafeSet.tests.\(UUID().uuidString)"
        guard let preferences = UserDefaults(suiteName: suite) else {
            return XCTFail("Could not create isolated preferences")
        }
        defer { preferences.removePersistentDomain(forName: suite) }
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("SafeSet-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let bundle = directory.appendingPathComponent("synthetic-private-bundle.enc")
        try Data().write(to: bundle)

        let first = AppModel(preferences: preferences)
        first.rememberRestoreBundle(bundle.path)
        let relaunched = AppModel(preferences: preferences)
        XCTAssertEqual(relaunched.restoreBundle, bundle.path)

        relaunched.forgetRestoreBundle()
        XCTAssertEqual(relaunched.restoreBundle, "")
        XCTAssertEqual(AppModel(preferences: preferences).restoreBundle, "")
    }

    @MainActor func testMissingRememberedPrivateBundleIsDiscarded() {
        let suite = "org.ozyjay.SafeSet.tests.\(UUID().uuidString)"
        guard let preferences = UserDefaults(suiteName: suite) else {
            return XCTFail("Could not create isolated preferences")
        }
        defer { preferences.removePersistentDomain(forName: suite) }
        preferences.set("/synthetic/missing/private-bundle.enc", forKey: "recentRestoreBundlePath")

        XCTAssertEqual(AppModel(preferences: preferences).restoreBundle, "")
        XCTAssertNil(preferences.string(forKey: "recentRestoreBundlePath"))
    }
}
