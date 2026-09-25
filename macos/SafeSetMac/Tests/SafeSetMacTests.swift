import XCTest
@testable import SafeSetMac

final class SafeSetMacTests: XCTestCase {
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
            "drop", "pseudonymise", "code", "keep", "bin", "keep_numeric"
        ])
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
