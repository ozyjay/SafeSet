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

    func testRestorationGuidancePreservesProtectedLinkageAndUsesPopulatedResults() {
        XCTAssertTrue(restorationAnalysisGuidance.contains("record_id"))
        XCTAssertTrue(restorationAnalysisGuidance.contains("entity_id"))
        XCTAssertTrue(restorationAnalysisGuidance.contains("instead of changing"))
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
        field.classification = "direct_identifier"
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
}
