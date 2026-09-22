"""Guided offline Tk interface for protected workbook round trips."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .desktop_flow import (
    approve_protection,
    approve_reconstruction,
    inspect_source,
    prepare_protection,
    prepare_reconstruction,
)
from .errors import SafetyError
from .ingestion import list_excel_sheets
from .policy_authoring import RuleDraft, local_categories, parse_number, parse_pairs

ACTIONS = {
    "Remove": "drop",
    "Replace with anonymous ID": "pseudonymise",
    "Obfuscate values": "code",
    "Keep": "keep",
    "Group into ranges": "bin",
    "Keep exact number": "keep_numeric",
}
CLASSES = {
    "Direct identifier": "direct_identifier",
    "Quasi-identifier": "quasi_identifier",
    "Analytical attribute": "analytical_attribute",
    "Free text": "free_text",
    "Unknown": "unknown",
    "Existing pseudonym": "pseudonymous_identifier",
}


class Desktop:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("SafeSet")
        root.geometry("900x720")
        self.frame = ttk.Frame(root, padding=24)
        self.frame.pack(fill="both", expand=True)
        self.protection_review = None
        self.reconstruction_review = None
        self.home()

    def _clear(self, title: str) -> None:
        for child in self.frame.winfo_children():
            child.destroy()
        ttk.Button(self.frame, text="← Home", command=self.home).pack(anchor="w")
        ttk.Label(self.frame, text=title, font=("Helvetica", 22, "bold")).pack(
            anchor="w", pady=(16, 14)
        )

    def _error(self, error: Exception) -> None:
        message = str(error) if isinstance(error, SafetyError) else "Local file operation failed."
        messagebox.showerror("SafeSet", message, parent=self.root)

    def _path(
        self, label: str, variable: tk.StringVar, *, save: bool = False, extension: str = ".xlsx"
    ) -> None:
        row = ttk.Frame(self.frame)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=25).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)

        def choose() -> None:
            selected = (
                filedialog.asksaveasfilename(parent=self.root, defaultextension=extension)
                if save
                else filedialog.askopenfilename(parent=self.root)
            )
            if selected:
                variable.set(selected)

        ttk.Button(row, text="Choose…", command=choose).pack(side="left", padx=6)

    def _sheets(self, path: Path) -> str | None:
        names = list_excel_sheets(path)
        if len(names) == 1:
            return names[0]
        answer = simpledialog.askstring(
            "Choose worksheet",
            "Enter one visible worksheet name exactly:\n" + "\n".join(names),
            parent=self.root,
        )
        if answer not in names:
            raise SafetyError("Select one visible worksheet.")
        return answer

    def home(self) -> None:
        self._clear("SafeSet")
        ttk.Label(
            self.frame,
            text="Protect a workbook, work with the protected copy, then restore locally.\n"
            "Passing checks reduces some disclosure risks; it does not establish anonymity.",
            wraplength=760,
        ).pack(anchor="w", pady=12)
        ttk.Button(self.frame, text="Protect a workbook", command=self.protect).pack(
            anchor="w", pady=10
        )
        ttk.Button(self.frame, text="Restore a workbook", command=self.restore).pack(
            anchor="w", pady=10
        )
        ttk.Separator(self.frame).pack(fill="x", pady=24)
        ttk.Button(self.frame, text="Advanced tools", command=self._advanced).pack(anchor="w")

    def _advanced(self) -> None:
        from .desktop_advanced import Desktop as AdvancedDesktop

        window = tk.Toplevel(self.root)
        AdvancedDesktop(window)

    def protect(self) -> None:
        self._clear("Protect a workbook")
        self.source = tk.StringVar()
        self.output = tk.StringVar()
        self.bundle = tk.StringVar()
        self.threshold = tk.StringVar(value="2")
        self._path("Original Excel workbook", self.source)
        ttk.Button(self.frame, text="Inspect and review fields", command=self._inspect).pack(
            anchor="w", pady=8
        )
        self._path("Protected workbook", self.output, save=True)
        self.field_host = ttk.Frame(self.frame)
        self.field_host.pack(fill="both", expand=True)

    def _inspect(self) -> None:
        try:
            self.source_path = Path(self.source.get())
            self.source_sheet = self._sheets(self.source_path)
            report = inspect_source(self.source_path, self.source_sheet)
            for child in self.field_host.winfo_children():
                child.destroy()
            ttk.Label(
                self.field_host,
                text=(
                    f"{report['rows']:,} records. Choose an action and classification "
                    "for every field."
                ),
            ).pack(anchor="w", pady=6)
            self.drafts = {}
            self.field_vars = {}
            canvas = tk.Canvas(self.field_host, height=290)
            scrollbar = ttk.Scrollbar(self.field_host, orient="vertical", command=canvas.yview)
            inner = ttk.Frame(canvas)
            inner.bind(
                "<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all"))
            )
            canvas.create_window((0, 0), window=inner, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="left", fill="y")
            for item in report["columns"]:
                name = item["column"]
                row = ttk.Frame(inner)
                row.pack(fill="x", pady=3)
                ttk.Label(row, text=name, width=24).pack(side="left")
                action = tk.StringVar()
                classification = tk.StringVar()
                ttk.Combobox(
                    row, textvariable=action, values=list(ACTIONS), state="readonly", width=27
                ).pack(side="left", padx=4)
                ttk.Combobox(
                    row,
                    textvariable=classification,
                    values=list(CLASSES),
                    state="readonly",
                    width=22,
                ).pack(side="left", padx=4)
                ttk.Button(row, text="Settings", command=lambda n=name: self._settings(n)).pack(
                    side="left", padx=4
                )
                hint = (
                    f"{item['type']}, {item['cardinality']} values; "
                    f"hint: {item['inferred_classification']}"
                )
                ttk.Label(row, text=hint).pack(side="left")
                self.field_vars[name] = (action, classification)
                self.drafts[name] = RuleDraft()
            controls = ttk.Frame(self.field_host)
            controls.pack(fill="x", pady=8)
            ttk.Label(controls, text="Minimum group size").pack(side="left")
            ttk.Entry(controls, textvariable=self.threshold, width=7).pack(side="left", padx=8)
            details = ttk.LabelFrame(self.field_host, text="Advanced")
            self._path_in(details, "Private bundle location (optional)", self.bundle)
            ttk.Button(
                self.field_host,
                text="Advanced settings…",
                command=lambda: (
                    details.pack(fill="x", pady=5)
                    if not details.winfo_manager()
                    else details.pack_forget()
                ),
            ).pack(anchor="w")
            ttk.Button(
                self.field_host, text="Review protection", command=self._review_protect
            ).pack(anchor="w", pady=8)
        except (SafetyError, OSError, UnicodeError) as error:
            self._error(error)

    def _path_in(self, parent: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(
            row,
            text="Choose…",
            command=lambda: variable.set(filedialog.asksaveasfilename(parent=self.root)),
        ).pack(side="left")

    def _settings(self, name: str) -> None:
        try:
            action = ACTIONS.get(self.field_vars[name][0].get())
            draft = self.drafts[name]
            if action in {"keep", "code"}:
                values = local_categories(self.source_path, name, self.source_sheet)
                if messagebox.askyesno(
                    "Review categories",
                    f"Approve {len(values)} local category values for this field?\n"
                    + "\n".join(values[:20]),
                    parent=self.root,
                ):
                    draft.allowed_values = values
            elif action == "bin":
                answer = simpledialog.askstring(
                    "Numeric ranges", "Enter one lower,upper pair per line.", parent=self.root
                )
                if answer is not None:
                    draft.bins = parse_pairs(answer)
            elif action == "keep_numeric":
                lower = simpledialog.askstring("Lower bound", "Minimum", parent=self.root)
                upper = simpledialog.askstring("Upper bound", "Maximum", parent=self.root)
                places = simpledialog.askinteger(
                    "Decimal places",
                    "Maximum decimal places",
                    parent=self.root,
                    minvalue=0,
                    maxvalue=6,
                )
                if lower is not None and upper is not None and places is not None:
                    draft.bounds = (parse_number(lower), parse_number(upper))
                    draft.max_decimal_places = places
            else:
                messagebox.showinfo("SafeSet", "This action needs no settings.", parent=self.root)
        except (SafetyError, OSError, UnicodeError) as error:
            self._error(error)

    def _review_protect(self) -> None:
        try:
            for name, (action, classification) in self.field_vars.items():
                self.drafts[name].action = ACTIONS.get(action.get(), "")
                self.drafts[name].classification = CLASSES.get(classification.get(), "")
            destination = Path(
                self.output.get()
                or self.source_path.with_name(self.source_path.stem + "-protected.xlsx")
            )
            bundle = Path(self.bundle.get()) if self.bundle.get() else None
            review = prepare_protection(
                self.source_path,
                self.drafts,
                self.threshold.get(),
                destination,
                bundle,
                self.source_sheet,
            )
            self.protection_review = review
            warnings = "\n".join(review.validation.warnings)
            errors = "\n".join(review.validation.errors)
            message = (
                f"{review.source_rows:,} records\n"
                f"{review.removed_fields} fields removed; 1 identifier replaced; "
                f"{review.obfuscated_fields} fields obfuscated; "
                f"{review.retained_fields} retained\n"
                f"Mandatory validation: {'passed' if review.validation.passed else 'blocked'}\n"
                f"Minimum joint group: {review.validation.minimum_class_size}\n"
                f"Warnings: {warnings or 'none'}\n"
                f"Blocking findings: {errors or 'none'}\n"
                f"Protected workbook: {review.output}\nPrivate bundle: {review.bundle_path}\n"
                "Passing validation does not establish anonymity or recipient suitability."
            )
            if not review.validation.passed:
                messagebox.showwarning("Protection blocked", message, parent=self.root)
                return
            if not messagebox.askyesno(
                "Review protection", message + "\n\nApprove creation?", parent=self.root
            ):
                return
            passphrase = self._secret(confirm=True)
            if passphrase:
                approve_protection(review, passphrase, approved=True)
                self.last_protection = (review.source, review.bundle_path)
                messagebox.showinfo(
                    "SafeSet", "Protected workbook and private bundle created.", parent=self.root
                )
                self.home()
        except (SafetyError, OSError, UnicodeError) as error:
            self._error(error)

    def _secret(self, *, confirm: bool = False) -> str | None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Restoration passphrase")
        dialog.transient(self.root)
        dialog.grab_set()
        first = tk.StringVar()
        second = tk.StringVar()
        ttk.Label(dialog, text="Restoration passphrase (16 characters minimum)").pack(
            padx=20, pady=8
        )
        ttk.Entry(dialog, textvariable=first, show="*", width=36).pack(padx=20)
        if confirm:
            ttk.Label(dialog, text="Confirm passphrase").pack(pady=8)
            ttk.Entry(dialog, textvariable=second, show="*", width=36).pack(padx=20)
        result = []

        def accept() -> None:
            if len(first.get()) < 16 or (confirm and first.get() != second.get()):
                messagebox.showerror(
                    "SafeSet", "Passphrase is too short or does not match.", parent=dialog
                )
                return
            result.append(first.get())
            dialog.destroy()

        ttk.Button(dialog, text="Continue", command=accept).pack(pady=16)
        self.root.wait_window(dialog)
        return result[0] if result else None

    def restore(self) -> None:
        self._clear("Restore a workbook")
        self.returned = tk.StringVar()
        self.original = tk.StringVar()
        self.restore_bundle = tk.StringVar()
        self.restored = tk.StringVar()
        if hasattr(self, "last_protection"):
            self.original.set(str(self.last_protection[0]))
            self.restore_bundle.set(str(self.last_protection[1]))
        self._path("Modified protected workbook", self.returned)
        self._path("Original source workbook", self.original)
        self._path("Private restoration bundle", self.restore_bundle, extension=".enc")
        self._path("New restored workbook", self.restored, save=True)
        ttk.Label(
            self.frame,
            text=(
                "The bundle must be unlocked locally before SafeSet can verify "
                "exact record coverage."
            ),
        ).pack(anchor="w", pady=10)
        ttk.Button(
            self.frame, text="Validate and review changes", command=self._review_restore
        ).pack(anchor="w")
        self.restore_host = ttk.Frame(self.frame)
        self.restore_host.pack(fill="both", expand=True, pady=16)

    def _review_restore(self) -> None:
        try:
            returned_path = Path(self.returned.get())
            source_path = Path(self.original.get())
            returned_sheet = self._sheets(returned_path)
            source_sheet = self._sheets(source_path)
            secret = self._secret()
            if secret is None:
                return
            destination = Path(
                self.restored.get()
                or returned_path.with_name(returned_path.stem + "-restored.xlsx")
            )
            review = prepare_reconstruction(
                returned_path,
                source_path,
                Path(self.restore_bundle.get()),
                destination,
                secret,
                returned_sheet=returned_sheet,
                source_sheet=source_sheet,
            )
            self.reconstruction_review = review
            for child in self.restore_host.winfo_children():
                child.destroy()
            ttk.Label(
                self.restore_host,
                text=f"Exact coverage: {len(review.returned_table.rows):,} records. "
                "All source-derived fields are unchanged.\n"
                "Original identity and removed fields will be restored from the source. "
                "Coded fields will use their original source labels.",
                wraplength=760,
            ).pack(anchor="w", pady=8)
            self.result_approvals = {}
            if review.new_columns:
                ttk.Label(self.restore_host, text="Approve each new result field to import:").pack(
                    anchor="w"
                )
            for name in review.new_columns:
                variable = tk.BooleanVar(value=False)
                ttk.Checkbutton(self.restore_host, text=name, variable=variable).pack(anchor="w")
                self.result_approvals[name] = variable
            ttk.Label(self.restore_host, text=f"New sensitive workbook: {review.output}").pack(
                anchor="w", pady=8
            )
            ttk.Button(
                self.restore_host, text="Authorise local restoration", command=self._approve_restore
            ).pack(anchor="w", pady=10)
        except (SafetyError, OSError, UnicodeError) as error:
            self._error(error)

    def _approve_restore(self) -> None:
        try:
            review = self.reconstruction_review
            approved = tuple(name for name, value in self.result_approvals.items() if value.get())
            if len(approved) != len(review.new_columns):
                raise SafetyError(
                    "Approve every new field or remove it from the returned workbook."
                )
            if not messagebox.askyesno(
                "Authorise restoration",
                "Create a new locally reidentified workbook?",
                parent=self.root,
            ):
                return
            count = approve_reconstruction(review, approved, authorised=True)
            messagebox.showinfo(
                "SafeSet",
                f"Restored {count:,} records locally. Keep this workbook private.",
                parent=self.root,
            )
            self.home()
        except (SafetyError, OSError, UnicodeError) as error:
            self._error(error)


def main() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        raise SystemExit("SafeSet desktop requires a local display and Tk installation.") from None
    Desktop(root)
    root.mainloop()


if __name__ == "__main__":
    main()
