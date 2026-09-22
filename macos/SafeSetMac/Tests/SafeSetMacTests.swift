import XCTest
@testable import SafeSetMac

final class SafeSetMacTests: XCTestCase {
    func testFieldDraftDefaultsRequireExplicitDecisions() {
        let draft = FieldDraft(id: "Invented Field")
        XCTAssertEqual(draft.action, "")
        XCTAssertEqual(draft.classification, "")
        XCTAssertEqual(draft.payload()["allowed_values"] as? [String], [])
    }

    func testActionNamesMapToStrictPolicyActions() {
        XCTAssertEqual(actionOptions.map(\.1), [
            "drop", "pseudonymise", "code", "keep", "bin", "keep_numeric"
        ])
    }

    @MainActor func testWizardDecisionAndReviewGates() {
        let model = AppModel()
        var field = FieldDraft(id: "Synthetic ID")
        model.fields = [field]
        XCTAssertFalse(model.canPrepareProtection)
        field.action = "drop"
        model.fields = [field]
        XCTAssertTrue(model.canPrepareProtection)
        field.action = "pseudonymise"
        field.classification = "direct_identifier"
        model.fields = [field]
        XCTAssertTrue(model.canPrepareProtection)

        model.restorationReview = ["review_id": "synthetic-token", "new_columns": ["Team"]]
        XCTAssertFalse(model.canApproveRestoration)
        model.approvedResults.insert("Team")
        XCTAssertTrue(model.canApproveRestoration)
        model.invalidate()
        XCTAssertFalse(model.canApproveRestoration)
        XCTAssertNil(model.protectionReview)
    }
}
