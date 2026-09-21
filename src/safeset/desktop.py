"""Offline Tk desktop interface for SafeSet's existing domain workflow."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .desktop_flow import (
    ExportReview,
    approve_export,
    inspect_source,
    prepare_export,
    restore_results,
)
from .errors import SafetyError

BACKGROUND = "#f5f7f5"
INK = "#17342d"
MUTED = "#52645d"
ACCENT = "#126b52"


def _path_row(parent: ttk.Frame, label: str, variable: tk.StringVar, *, save: bool = False) -> None:
    row = ttk.Frame(parent)
    row.pack(fill="x", pady=5)
    ttk.Label(row, text=label, width=19).pack(side="left")
    ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=(0, 8))

    def choose() -> None:
        selected = (
            filedialog.asksaveasfilename(parent=parent, title=label)
            if save
            else filedialog.askopenfilename(parent=parent, title=label)
        )
        if selected:
            variable.set(selected)

    ttk.Button(row, text="Choose…", command=choose).pack(side="right")


def _passphrase(parent: tk.Tk, *, confirm: bool) -> str | None:
    dialog = tk.Toplevel(parent)
    dialog.title("Mapping passphrase")
    dialog.transient(parent)
    dialog.resizable(False, False)
    dialog.grab_set()
    body = ttk.Frame(dialog, padding=22)
    body.pack(fill="both")
    ttk.Label(body, text="Mapping passphrase", style="Heading.TLabel").pack(anchor="w")
    ttk.Label(body, text="Entered locally. It is not saved by SafeSet.").pack(
        anchor="w", pady=(3, 14)
    )
    first = tk.StringVar()
    second = tk.StringVar()
    ttk.Entry(body, textvariable=first, show="•", width=38).pack(fill="x")
    if confirm:
        ttk.Label(body, text="Confirm passphrase").pack(anchor="w", pady=(12, 4))
        ttk.Entry(body, textvariable=second, show="•").pack(fill="x")
    error = ttk.Label(body, text="", foreground="#a62b27")
    error.pack(anchor="w", pady=(8, 0))
    result: list[str] = []

    def accept() -> None:
        if len(first.get()) < 16:
            error.configure(text="Use at least 16 characters.")
        elif confirm and first.get() != second.get():
            error.configure(text="Passphrases do not match.")
        else:
            result.append(first.get())
            first.set("")
            second.set("")
            dialog.destroy()

    controls = ttk.Frame(body)
    controls.pack(fill="x", pady=(16, 0))
    ttk.Button(controls, text="Cancel", command=dialog.destroy).pack(side="right")
    ttk.Button(controls, text="Continue", command=accept).pack(side="right", padx=(0, 8))
    dialog.bind("<Return>", lambda _event: accept())
    dialog.bind("<Escape>", lambda _event: dialog.destroy())
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.after_idle(lambda: dialog.focus_force())
    dialog.wait_window()
    return result[0] if result else None


class Desktop:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.review: ExportReview | None = None
        root.title("SafeSet · local data review")
        root.geometry("840x700")
        root.minsize(700, 620)
        root.configure(background=BACKGROUND)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background=BACKGROUND)
        style.configure("TLabel", background=BACKGROUND, foreground=INK, font=("Helvetica", 12))
        style.configure("Heading.TLabel", font=("Helvetica", 19, "bold"), foreground=INK)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("TButton", padding=(12, 8), font=("Helvetica", 11))
        style.configure("Accent.TButton", foreground="white", background=ACCENT)
        style.map("Accent.TButton", background=[("active", "#0b543e")])
        style.configure("TNotebook", background=BACKGROUND, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 10), font=("Helvetica", 11))

        shell = ttk.Frame(root, padding=(30, 24))
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="SafeSet", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(
            shell,
            text="Review locally  ·  minimise deliberately  ·  approve each export",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 15))
        notebook = ttk.Notebook(shell)
        notebook.pack(fill="both", expand=True)
        self.inspect_tab = ttk.Frame(notebook, padding=20)
        self.export_tab = ttk.Frame(notebook, padding=20)
        self.restore_tab = ttk.Frame(notebook, padding=20)
        notebook.add(self.inspect_tab, text="1  Inspect")
        notebook.add(self.export_tab, text="2  Export")
        notebook.add(self.restore_tab, text="3  Restore")
        self._build_inspect()
        self._build_export()
        self._build_restore()
        ttk.Label(
            shell,
            text=(
                "Passing checks reduces some disclosure risks; it does not establish anonymity. "
                "No runtime network access."
            ),
            style="Muted.TLabel",
            wraplength=750,
        ).pack(anchor="w", pady=(16, 0))

    def _error(self, error: Exception) -> None:
        message = (
            str(error)
            if isinstance(error, SafetyError)
            else "Local file operation failed. No details shown."
        )
        messagebox.showerror("SafeSet", message, parent=self.root)

    def _build_inspect(self) -> None:
        tab = self.inspect_tab
        ttk.Label(tab, text="Inspect a source CSV", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(
            tab,
            text="Only aggregate characteristics appear here. No source values are previewed.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(5, 16))
        self.inspect_source = tk.StringVar()
        _path_row(tab, "Source CSV", self.inspect_source)
        ttk.Button(tab, text="Inspect locally", style="Accent.TButton", command=self._inspect).pack(
            anchor="w", pady=(12, 16)
        )
        self.inspect_result = ttk.Label(tab, text="Choose a file to begin.", justify="left")
        self.inspect_result.pack(anchor="w")
        grid_area = ttk.Frame(tab)
        grid_area.pack(fill="both", expand=True, pady=(16, 0))
        columns = ("column", "classification", "type", "distinct", "blank", "flags")
        self.inspect_grid = ttk.Treeview(grid_area, columns=columns, show="headings", height=11)
        headings = {
            "column": "Column",
            "classification": "Likely class",
            "type": "Type",
            "distinct": "Distinct",
            "blank": "Blank",
            "flags": "Flags",
        }
        for column in columns:
            self.inspect_grid.heading(column, text=headings[column])
            self.inspect_grid.column(
                column,
                width=160 if column in {"column", "classification"} else 85,
                minwidth=70,
                stretch=column in {"column", "classification"},
            )
        grid_scroll = ttk.Scrollbar(grid_area, orient="vertical", command=self.inspect_grid.yview)
        self.inspect_grid.configure(yscrollcommand=grid_scroll.set)
        grid_scroll.pack(side="right", fill="y")
        self.inspect_grid.pack(side="left", fill="both", expand=True)

    def _inspect(self) -> None:
        try:
            summary = inspect_source(Path(self.inspect_source.get()))
            counts: dict[str, int] = {}
            flags = 0
            for column in summary["columns"]:
                kind = column["inferred_classification"]
                counts[kind] = counts.get(kind, 0) + 1
                flags += len(column["flags"])
            lines = [
                f"{summary['rows']:,} rows  ·  {len(summary['columns'])} columns",
                f"{counts.get('direct_identifier', 0)} likely direct identifier columns",
                f"{counts.get('free_text', 0)} likely free-text columns",
                f"{counts.get('unknown', 0)} unclassified columns",
                f"{flags} advisory flags across columns",
                "",
                "Classify every field in a policy. These heuristics are incomplete.",
            ]
            self.inspect_result.configure(text="\n".join(lines))
            self.inspect_grid.delete(*self.inspect_grid.get_children())
            for column in summary["columns"]:
                self.inspect_grid.insert(
                    "",
                    "end",
                    values=(
                        column["column"],
                        column["inferred_classification"],
                        column["type"],
                        column["cardinality"],
                        column["blank_count"],
                        ", ".join(column["flags"]) or "—",
                    ),
                )
        except (SafetyError, OSError, UnicodeError) as error:
            self._error(error)

    def _build_export(self) -> None:
        canvas = tk.Canvas(self.export_tab, background=BACKGROUND, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.export_tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        tab = ttk.Frame(canvas, padding=(0, 0, 15, 16))
        window = canvas.create_window((0, 0), window=tab, anchor="nw")
        tab.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        ttk.Label(tab, text="Prepare a minimised export", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(
            tab,
            text="The candidate stays in memory until validation and approval are complete.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(5, 15))
        self.source = tk.StringVar()
        self.policy = tk.StringVar()
        self.output = tk.StringVar()
        self.map_path = tk.StringVar()
        for label, variable, save in (
            ("Source CSV", self.source, False),
            ("Policy YAML", self.policy, False),
            ("Export CSV", self.output, True),
            ("Encrypted map", self.map_path, True),
        ):
            _path_row(tab, label, variable, save=save)
            variable.trace_add("write", self._invalidate_review)
        ttk.Label(
            tab,
            text=(
                "Leave map blank for a random name in the private SafeSet map directory. "
                "Store it separately from exports."
            ),
            style="Muted.TLabel",
            wraplength=700,
        ).pack(anchor="w", pady=(3, 14))
        ttk.Button(tab, text="Prepare and validate", command=self._prepare).pack(anchor="w")
        self.review_text = ttk.Label(
            tab, text="No candidate prepared.", justify="left", wraplength=730
        )
        self.review_text.pack(anchor="w", pady=(18, 12))
        self.approve_button = ttk.Button(
            tab, text="Approve export and create map", style="Accent.TButton", command=self._approve
        )
        self.approve_button.pack(anchor="w")
        self.approve_button.state(["disabled"])

    def _invalidate_review(self, *_args: object) -> None:
        self.review = None
        self.review_text.configure(text="Inputs changed. Prepare and validate again.")
        self.approve_button.state(["disabled"])

    def _prepare(self) -> None:
        self.review = None
        self.approve_button.state(["disabled"])
        try:
            review = prepare_export(
                Path(self.source.get()),
                Path(self.policy.get()),
                Path(self.output.get()),
                Path(self.map_path.get()) if self.map_path.get().strip() else None,
            )
            self.review = review
            report = review.validation
            verdict = (
                "PASS — ready for your review" if report.passed else "BLOCKED — export prohibited"
            )
            details = [
                verdict,
                f"Source: {review.source_rows:,} rows, {review.source_columns} columns",
                f"Dropped columns: {review.dropped_columns}",
                f"Export columns: {len(review.policy.output_columns)}",
                f"Minimum joint group: {report.minimum_class_size}",
                f"Records in small joint groups: {report.small_class_records}",
                f"Unique records: {report.unique_records}",
                f"Small categorical cells: {report.small_cells}",
                f"Export destination: {review.output}",
                f"Encrypted map destination: {review.map_path}",
            ]
            details += [f"Error: {error}" for error in report.errors]
            details += [f"Warning: {warning}" for warning in report.warnings]
            details.append("Policy decisions:")
            details += [
                f"  {name}: {rule.action} ({rule.classification})"
                for name, rule in review.policy.columns.items()
            ]
            details.append(
                "Check the intended recipient and whether each retained attribute is necessary."
            )
            self.review_text.configure(text="\n".join(details))
            if report.passed:
                self.approve_button.state(["!disabled"])
        except (SafetyError, OSError, UnicodeError) as error:
            self.review_text.configure(text="Preparation failed. No artefacts created.")
            self._error(error)

    def _approve(self) -> None:
        review = self.review
        if review is None or not review.validation.passed:
            return
        if not messagebox.askyesno(
            "Approve export",
            "Create the minimised CSV and a separate encrypted identity map?\n\n"
            "Confirm the intended recipient is suitable. "
            "Passing checks does not establish anonymity.",
            parent=self.root,
            default="no",
        ):
            return
        passphrase = _passphrase(self.root, confirm=True)
        if passphrase is None:
            return
        try:
            approve_export(review, passphrase, approved=True)
            self.review = None
            self.approve_button.state(["disabled"])
            self.review_text.configure(
                text="Export and encrypted map created. Keep the map private and separate."
            )
            messagebox.showinfo(
                "SafeSet", "Export complete. Keep the encrypted map local and separate."
            )
        except (SafetyError, OSError, UnicodeError) as error:
            self.review = None
            self.approve_button.state(["disabled"])
            self._error(error)

    def _build_restore(self) -> None:
        tab = self.restore_tab
        ttk.Label(tab, text="Restore authorised results", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(
            tab,
            text=(
                "This creates sensitive plaintext locally. "
                "Select only the result columns you intend to retain."
            ),
            style="Muted.TLabel",
            wraplength=700,
        ).pack(anchor="w", pady=(5, 15))
        self.result_source = tk.StringVar()
        self.result_map = tk.StringVar()
        self.result_output = tk.StringVar()
        for label, variable, save in (
            ("Analysed CSV", self.result_source, False),
            ("Encrypted map", self.result_map, False),
            ("Restored CSV", self.result_output, True),
        ):
            _path_row(tab, label, variable, save=save)
        ttk.Label(
            tab, text="Result columns (comma separated; record_id is included automatically)"
        ).pack(anchor="w", pady=(14, 5))
        self.result_columns = tk.StringVar()
        ttk.Entry(tab, textvariable=self.result_columns).pack(fill="x")
        ttk.Button(
            tab, text="Authorise local restoration", style="Accent.TButton", command=self._restore
        ).pack(anchor="w", pady=(18, 0))

    def _restore(self) -> None:
        columns = tuple(
            part.strip() for part in self.result_columns.get().split(",") if part.strip()
        )
        if not messagebox.askyesno(
            "Authorise restoration",
            "Restore exact source keys into a sensitive plaintext CSV at the selected destination?",
            parent=self.root,
            default="no",
        ):
            return
        passphrase = _passphrase(self.root, confirm=False)
        if passphrase is None:
            return
        try:
            rows = restore_results(
                Path(self.result_source.get()),
                Path(self.result_map.get()),
                Path(self.result_output.get()),
                columns,
                passphrase,
                authorised=True,
            )
            messagebox.showinfo(
                "SafeSet",
                f"Restored {rows:,} rows locally. Keep this plaintext file private.",
                parent=self.root,
            )
        except (SafetyError, OSError, UnicodeError) as error:
            self._error(error)


def main() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        raise SystemExit(
            "SafeSet desktop requires a working local display and Tk installation."
        ) from None
    Desktop(root)
    root.mainloop()


if __name__ == "__main__":
    main()
