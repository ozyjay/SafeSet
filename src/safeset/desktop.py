"""Offline Tk desktop interface for SafeSet's existing domain workflow."""

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .desktop_flow import (
    ExportReview,
    ReturnedReview,
    approve_export,
    inspect_returned,
    inspect_source,
    prepare_export,
    restore_results,
)
from .diagnostics import record, record_reason
from .errors import SafetyError
from .ingestion import list_excel_sheets
from .policy import NAME
from .policy_authoring import (
    RuleDraft,
    load_drafts,
    local_categories,
    parse_number,
    parse_pairs,
    save_policy,
)
from .storage import check_map_read, output_destination

BACKGROUND = "#f5f7f5"
INK = "#17342d"
MUTED = "#52645d"
ACCENT = "#126b52"
ACTION_LABELS = {
    "drop": "Remove",
    "pseudonymise": "Replace with random record ID",
    "keep": "Keep approved categories",
    "code": "Replace categories with random codes",
    "bin": "Keep numeric bands",
    "keep_numeric": "Keep exact numeric value",
}
PICKER_TYPES = {
    "xlsx": (("Excel workbooks", "*.xlsx"), ("All files", "*")),
    "yaml": (("YAML policies", "*.yaml *.yml"), ("All files", "*")),
    "enc": (("Encrypted maps", "*.enc"), ("All files", "*")),
}
CLASS_LABELS = {
    "Direct identifier": "direct_identifier",
    "Quasi-identifier": "quasi_identifier",
    "Analytical attribute": "analytical_attribute",
    "Free text": "free_text",
    "Unknown": "unknown",
    "Existing pseudonym": "pseudonymous_identifier",
}
ACTION_FROM_LABEL = {label: action for action, label in ACTION_LABELS.items()}


def _path_row(
    parent: ttk.Frame,
    label: str,
    variable: tk.StringVar,
    *,
    save: bool = False,
    kind: str = "xlsx",
) -> None:
    row = ttk.Frame(parent)
    row.pack(fill="x", pady=5)
    ttk.Label(row, text=label, width=19).pack(side="left")
    ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=(0, 8))

    def choose() -> None:
        selected = (
            filedialog.asksaveasfilename(
                parent=parent,
                title=label,
                filetypes=PICKER_TYPES[kind],
                defaultextension=f".{kind}" if kind != "yaml" else ".yaml",
            )
            if save
            else filedialog.askopenfilename(
                parent=parent, title=label, filetypes=PICKER_TYPES[kind]
            )
        )
        if selected:
            variable.set(selected)

    ttk.Button(row, text="Choose…", command=choose).pack(side="right")


def _selected_sheets(variable: tk.StringVar) -> tuple[str, ...] | None:
    try:
        names = json.loads(variable.get())
    except ValueError:
        return None
    return tuple(names) if isinstance(names, list) and names else None


def _sheet_row(parent: ttk.Frame, path: tk.StringVar, selected: tk.StringVar) -> None:
    row = ttk.Frame(parent)
    row.pack(fill="x", pady=5)
    ttk.Label(row, text="Worksheets", width=19).pack(side="left")
    picker = tk.Listbox(row, selectmode="multiple", exportselection=False, height=4)
    picker.pack(side="left", fill="x", expand=True, padx=(0, 8))
    scrollbar = ttk.Scrollbar(row, orient="vertical", command=picker.yview)
    scrollbar.pack(side="right", fill="y")
    picker.configure(yscrollcommand=scrollbar.set)
    ttk.Label(parent, text="Click each worksheet to include it.", style="Muted.TLabel").pack(
        anchor="w", pady=(0, 4)
    )
    names: tuple[str, ...] = ()
    syncing = False

    def reflect(*_args: object) -> None:
        nonlocal syncing
        if syncing:
            return
        syncing = True
        picker.selection_clear(0, "end")
        chosen = set(_selected_sheets(selected) or ())
        for index, name in enumerate(names):
            if name in chosen:
                picker.selection_set(index)
        syncing = False

    def record_selection(_event: object) -> None:
        if not syncing:
            selected.set(json.dumps([names[index] for index in picker.curselection()]))

    def refresh(*_args: object) -> None:
        nonlocal names
        try:
            names = list_excel_sheets(Path(path.get()))
        except (SafetyError, OSError, UnicodeError):
            names = ()
        picker.delete(0, "end")
        for name in names:
            picker.insert("end", name)
        if len(names) == 1:
            selected.set(json.dumps(names))
        else:
            selected.set("[]")

    picker.bind("<<ListboxSelect>>", record_selection)
    selected.trace_add("write", reflect)
    path.trace_add("write", refresh)


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
    first_entry = ttk.Entry(body, textvariable=first, show="•", width=38)
    first_entry.pack(fill="x")
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
    dialog.after_idle(first_entry.focus_set)
    dialog.wait_window()
    return result[0] if result else None


class Desktop:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.review: ExportReview | None = None
        self.returned_review: ReturnedReview | None = None
        self.inspected_path: Path | None = None
        self.policy_drafts: dict[str, RuleDraft] = {}
        self.policy_controls: dict[str, tuple[tk.StringVar, tk.StringVar]] = {}
        self.policy_details_buttons: dict[str, ttk.Button] = {}
        root.title("SafeSet · local data review")
        width, height = 840, 700
        x = max(0, (root.winfo_screenwidth() - width) // 2)
        y = max(0, (root.winfo_screenheight() - height) // 2)
        root.geometry(f"{width}x{height}+{x}+{y}")
        root.minsize(700, 620)
        root.configure(background=BACKGROUND)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background=BACKGROUND)
        style.configure("TLabel", background=BACKGROUND, foreground=INK, font=("Helvetica", 12))
        style.configure("Heading.TLabel", font=("Helvetica", 19, "bold"), foreground=INK)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Success.TLabel", foreground=ACCENT, font=("Helvetica", 12, "bold"))
        style.configure("Blocked.TLabel", foreground="#a62b27", font=("Helvetica", 12, "bold"))
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
        self.notebook = ttk.Notebook(shell)
        self.notebook.pack(fill="both", expand=True)
        self.inspect_tab = ttk.Frame(self.notebook, padding=20)
        self.policy_tab = ttk.Frame(self.notebook, padding=20)
        self.export_tab = ttk.Frame(self.notebook, padding=20)
        self.restore_tab = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(self.inspect_tab, text="1  Inspect")
        self.notebook.add(self.policy_tab, text="2  Policy")
        self.notebook.add(self.export_tab, text="3  Export")
        self.notebook.add(self.restore_tab, text="4  Restore")
        self._build_inspect()
        self._build_policy()
        self._build_export()
        self._build_restore()
        ttk.Label(
            shell,
            text=(
                "Passing checks reduces some disclosure risks; it does not establish anonymity. "
                "No runtime network access."
            ),
            style="Muted.TLabel",
            wraplength=620,
        ).pack(anchor="w", pady=(16, 0))

    def _error(self, error: Exception, stage: str) -> None:
        record(stage, "rejected" if isinstance(error, SafetyError) else "io_error")
        if isinstance(error, SafetyError):
            record_reason(stage, error)
        message = (
            str(error)
            if isinstance(error, SafetyError)
            else "Local file operation failed. No details shown."
        )
        messagebox.showerror("SafeSet", message, parent=self.root)

    def _build_inspect(self) -> None:
        tab = self.inspect_tab
        ttk.Label(tab, text="Inspect a source Excel workbook", style="Heading.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            tab,
            text="Only aggregate characteristics appear here. No source values are previewed.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(5, 16))
        self.inspect_source = tk.StringVar()
        self.inspect_source.trace_add("write", self._invalidate_inspection)
        _path_row(tab, "Source Excel workbook", self.inspect_source)
        self.inspect_sheet = tk.StringVar()
        self.inspect_sheet.trace_add("write", self._invalidate_inspection)
        _sheet_row(tab, self.inspect_source, self.inspect_sheet)
        controls = ttk.Frame(tab)
        controls.pack(anchor="w", pady=(12, 16))
        ttk.Button(
            controls, text="Inspect locally", style="Accent.TButton", command=self._inspect
        ).pack(side="left")
        self.use_source_button = ttk.Button(
            controls, text="Use existing policy →", command=self._use_inspected_source
        )
        self.use_source_button.pack(side="left", padx=(10, 0))
        self.use_source_button.state(["disabled"])
        self.make_policy_button = ttk.Button(
            controls, text="Create policy →", command=self._use_inspected_for_policy
        )
        self.make_policy_button.pack(side="left", padx=(10, 0))
        self.make_policy_button.state(["disabled"])
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
        record("desktop.inspect", "start")
        self._invalidate_inspection()
        try:
            source = Path(self.inspect_source.get())
            summary = inspect_source(source, _selected_sheets(self.inspect_sheet))
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
            if summary["formula_cells"]:
                lines.extend(
                    (
                        f"{summary['formula_cells']} saved formula results used",
                        "Formula results may be stale. Recalculate and save locally.",
                    )
                )
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
            self.inspected_path = source
            self.inspected_sheet = _selected_sheets(self.inspect_sheet)
            self.use_source_button.state(["!disabled"])
            self.make_policy_button.state(["!disabled"])
            record("desktop.inspect", "success")
        except (SafetyError, OSError, UnicodeError) as error:
            self._error(error, "desktop.inspect")

    def _invalidate_inspection(self, *_args: object) -> None:
        self.inspected_path = None
        self.inspected_sheet = None
        if hasattr(self, "use_source_button"):
            self.use_source_button.state(["disabled"])
            self.make_policy_button.state(["disabled"])
            self.inspect_result.configure(text="Source changed. Inspect again to continue.")
            self.inspect_grid.delete(*self.inspect_grid.get_children())

    def _use_inspected_source(self) -> None:
        if self.inspected_path is not None:
            self.source.set(str(self.inspected_path))
            self.source_sheet.set(json.dumps(self.inspected_sheet or ()))
            self.notebook.select(self.export_tab)

    def _use_inspected_for_policy(self) -> None:
        if self.inspected_path is not None:
            self.policy_source.set(str(self.inspected_path))
            self.policy_sheet.set(json.dumps(self.inspected_sheet or ()))
            self.notebook.select(self.policy_tab)
            self._load_policy_columns()

    def _build_policy(self) -> None:
        footer = ttk.Frame(self.policy_tab)
        footer.pack(side="bottom", fill="x", pady=(12, 0))
        canvas = tk.Canvas(self.policy_tab, background=BACKGROUND, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.policy_tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = ttk.Frame(canvas, padding=(0, 0, 15, 16))
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        ttk.Label(body, text="Build a policy", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text=(
                "Choose an action and classification for every source column. "
                "Replace exactly one source key with a random record ID; remove other "
                "direct identifiers and free text. Hints are advisory."
            ),
            style="Muted.TLabel",
            wraplength=540,
        ).pack(anchor="w", pady=(5, 15))
        self.policy_source = tk.StringVar()
        self.policy_source.trace_add("write", self._invalidate_policy_source)
        _path_row(body, "Source Excel workbook", self.policy_source)
        self.policy_sheet = tk.StringVar()
        self.policy_sheet.trace_add("write", self._invalidate_policy_source)
        _sheet_row(body, self.policy_source, self.policy_sheet)
        ttk.Button(body, text="Load source columns", command=self._load_policy_columns).pack(
            anchor="w", pady=(9, 8)
        )
        self.existing_policy = tk.StringVar()
        _path_row(body, "Existing policy", self.existing_policy, kind="yaml")
        ttk.Button(body, text="Load existing choices", command=self._load_existing_policy).pack(
            anchor="w", pady=(8, 10)
        )
        self.policy_status = ttk.Label(body, text="No source columns loaded.", style="Muted.TLabel")
        self.policy_status.pack(anchor="w", pady=(0, 12))
        ttk.Label(body, text="Minimum group size").pack(anchor="w")
        self.policy_threshold = tk.StringVar()
        ttk.Entry(body, textvariable=self.policy_threshold, width=8).pack(anchor="w", pady=(4, 4))
        ttk.Label(
            body,
            text="Choose a threshold of at least 2. Retained values and joint groups must meet it.",
            style="Muted.TLabel",
            wraplength=540,
        ).pack(anchor="w", pady=(0, 12))
        self.policy_rows = ttk.Frame(body)
        self.policy_rows.pack(fill="x")
        ttk.Separator(body).pack(fill="x", pady=(15, 12))
        self.policy_output = tk.StringVar()
        _path_row(body, "New policy YAML", self.policy_output, save=True, kind="yaml")
        ttk.Label(
            body,
            text=(
                "Save to a new file outside repositories. Category labels in this policy "
                "may still be sensitive. Export is validated separately."
            ),
            style="Muted.TLabel",
            wraplength=540,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Button(
            footer,
            text="Save policy and continue →",
            style="Accent.TButton",
            command=self._save_policy,
        ).pack(side="left")

    def _invalidate_policy_source(self, *_args: object) -> None:
        self.policy_drafts.clear()
        self.policy_controls.clear()
        self.policy_details_buttons.clear()
        if hasattr(self, "policy_rows"):
            for child in self.policy_rows.winfo_children():
                child.destroy()
            self.policy_status.configure(text="Source changed. Load its columns again.")

    def _load_policy_columns(self) -> None:
        record("desktop.policy.columns", "start")
        self._invalidate_policy_source()
        try:
            summary = inspect_source(
                Path(self.policy_source.get()), _selected_sheets(self.policy_sheet)
            )
            if any(not NAME.fullmatch(column["column"]) for column in summary["columns"]):
                raise SafetyError("Policy source headings must use lowercase snake_case.")
            self.policy_status.configure(
                text=(
                    f"{summary['rows']:,} rows · {len(summary['columns'])} columns. "
                    "Set each row explicitly."
                )
            )
            friendly_classes = {value: key for key, value in CLASS_LABELS.items()}
            for column in summary["columns"]:
                name = column["column"]
                self.policy_drafts[name] = RuleDraft()
                row = ttk.Frame(self.policy_rows, padding=(0, 8))
                row.pack(fill="x")
                top = ttk.Frame(row)
                top.pack(fill="x")
                ttk.Label(top, text=name, width=23).pack(side="left")
                hint = friendly_classes.get(column["inferred_classification"], "Unknown")
                ttk.Label(top, text=f"Hint: {hint}", style="Muted.TLabel").pack(side="left")
                details = ttk.Button(
                    top,
                    text="Settings…",
                    command=lambda field=name: self._edit_policy_settings(field),
                )
                details.pack(side="right")
                self.policy_details_buttons[name] = details
                lower = ttk.Frame(row)
                lower.pack(fill="x", pady=(6, 0))
                action = tk.StringVar()
                classification = tk.StringVar()
                ttk.Label(lower, text="Action").pack(side="left", padx=(0, 5))
                ttk.Combobox(
                    lower,
                    textvariable=action,
                    values=tuple(ACTION_FROM_LABEL),
                    state="readonly",
                    width=31,
                ).pack(side="left", padx=(0, 10))
                ttk.Label(lower, text="Class").pack(side="left", padx=(0, 5))
                ttk.Combobox(
                    lower,
                    textvariable=classification,
                    values=tuple(CLASS_LABELS),
                    state="readonly",
                    width=22,
                ).pack(side="left")
                self.policy_controls[name] = (action, classification)
                action.trace_add(
                    "write", lambda *_args, button=details: button.configure(text="Settings…")
                )
                ttk.Separator(self.policy_rows).pack(fill="x")
            record("desktop.policy.columns", "success")
        except (SafetyError, OSError, UnicodeError) as error:
            self._error(error, "desktop.policy.columns")

    def _load_existing_policy(self) -> None:
        record("desktop.policy.choices", "start")
        if not self.existing_policy.get().strip():
            messagebox.showerror(
                "SafeSet", "Choose an existing policy YAML file.", parent=self.root
            )
            return
        if not self.policy_drafts:
            self._load_policy_columns()
        if not self.policy_drafts:
            return
        try:
            drafts, threshold = load_drafts(
                Path(self.policy_source.get()),
                Path(self.existing_policy.get()),
                _selected_sheets(self.policy_sheet),
            )
            action_labels = {action: label for label, action in ACTION_FROM_LABEL.items()}
            class_labels = {value: key for key, value in CLASS_LABELS.items()}
            for name, draft in drafts.items():
                self.policy_drafts[name] = draft
                action, classification = self.policy_controls[name]
                action.set(action_labels[draft.action])
                classification.set(class_labels[draft.classification])
                if draft.action in {"keep", "code", "bin", "keep_numeric"}:
                    self.policy_details_buttons[name].configure(text="Settings ✓")
            self.policy_threshold.set(str(threshold))
            self.policy_status.configure(
                text="Existing choices loaded. Review each field and save to a new policy file."
            )
            record("desktop.policy.choices", "success")
        except (SafetyError, OSError, UnicodeError) as error:
            self._error(error, "desktop.policy.choices")

    def _edit_policy_settings(self, name: str) -> None:
        action_label = self.policy_controls[name][0].get()
        action = ACTION_FROM_LABEL.get(action_label)
        if action is None:
            messagebox.showinfo("SafeSet", "Choose an action first.", parent=self.root)
            return
        if action in {"drop", "pseudonymise"}:
            messagebox.showinfo("SafeSet", "This action needs no settings.", parent=self.root)
            return
        draft = self.policy_drafts[name]
        dialog = tk.Toplevel(self.root)
        dialog.title("Field settings")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill="both")
        ttk.Label(body, text=name, style="Heading.TLabel").pack(anchor="w")
        text_widget = None
        lower = upper = places = None
        if action in {"keep", "code"}:
            ttk.Label(body, text="One approved category per line. Enter every allowed value.").pack(
                anchor="w", pady=(12, 6)
            )
            text_widget = tk.Text(body, width=46, height=8, wrap="none")
            text_widget.pack()
            text_widget.insert("1.0", "\n".join(draft.allowed_values))

            def load_values() -> None:
                classification = CLASS_LABELS.get(self.policy_controls[name][1].get())
                if classification not in {"quasi_identifier", "analytical_attribute"}:
                    messagebox.showerror(
                        "SafeSet", "Choose an eligible classification first.", parent=dialog
                    )
                    return
                if not messagebox.askyesno(
                    "Show local categories",
                    "Display distinct source values in this window for review? "
                    "Do not allowlist personal identifiers or free text.",
                    parent=dialog,
                    default="no",
                ):
                    return
                try:
                    values = local_categories(
                        Path(self.policy_source.get()), name, _selected_sheets(self.policy_sheet)
                    )
                    text_widget.delete("1.0", "end")
                    text_widget.insert("1.0", "\n".join(values))
                except (SafetyError, OSError, UnicodeError) as error:
                    messagebox.showerror(
                        "SafeSet",
                        str(error)
                        if isinstance(error, SafetyError)
                        else "Local file operation failed. No details shown.",
                        parent=dialog,
                    )

            ttk.Button(body, text="Load distinct values locally", command=load_values).pack(
                anchor="w", pady=(8, 0)
            )
        elif action == "bin":
            ttk.Label(
                body,
                text="One lower,upper pair per line, such as 0,4 then 4,7. Bins must join.",
            ).pack(anchor="w", pady=(12, 6))
            text_widget = tk.Text(body, width=46, height=8, wrap="none")
            text_widget.pack()
            text_widget.insert("1.0", "\n".join(f"{lo},{hi}" for lo, hi in draft.bins))
        else:
            lower = tk.StringVar(value="" if draft.bounds is None else str(draft.bounds[0]))
            upper = tk.StringVar(value="" if draft.bounds is None else str(draft.bounds[1]))
            places = tk.StringVar(
                value="" if draft.max_decimal_places is None else str(draft.max_decimal_places)
            )
            for label, variable in (
                ("Minimum value (inclusive)", lower),
                ("Maximum value (inclusive)", upper),
                ("Maximum decimal places (0–6)", places),
            ):
                ttk.Label(body, text=label).pack(anchor="w", pady=(10, 3))
                ttk.Entry(body, textvariable=variable, width=20).pack(anchor="w")

        def accept() -> None:
            try:
                if action in {"keep", "code"}:
                    draft.allowed_values = tuple(text_widget.get("1.0", "end-1c").splitlines())
                elif action == "bin":
                    draft.bins = parse_pairs(text_widget.get("1.0", "end-1c"))
                else:
                    if not places.get().isascii() or not places.get().isdecimal():
                        raise SafetyError("Enter a whole number of decimal places from 0 to 6.")
                    draft.bounds = (parse_number(lower.get()), parse_number(upper.get()))
                    draft.max_decimal_places = int(places.get())
                self.policy_details_buttons[name].configure(text="Settings ✓")
                dialog.destroy()
            except SafetyError as error:
                messagebox.showerror("SafeSet", str(error), parent=dialog)

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(16, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="Save settings", command=accept).pack(side="right", padx=(0, 8))
        dialog.wait_window()

    def _save_policy(self) -> None:
        record("desktop.policy.save", "start")
        if not self.policy_drafts:
            messagebox.showerror("SafeSet", "Load source columns first.", parent=self.root)
            return
        for name, draft in self.policy_drafts.items():
            action, classification = self.policy_controls[name]
            draft.action = ACTION_FROM_LABEL.get(action.get(), "")
            draft.classification = CLASS_LABELS.get(classification.get(), "")
        if any(
            not draft.action or not draft.classification for draft in self.policy_drafts.values()
        ):
            messagebox.showerror(
                "SafeSet", "Choose an action and classification for every column.", parent=self.root
            )
            return
        if any(
            draft.action in {"keep", "code"} and not draft.allowed_values
            for draft in self.policy_drafts.values()
        ):
            messagebox.showerror(
                "SafeSet",
                "Set approved categories for every kept or coded column.",
                parent=self.root,
            )
            return
        if any(
            draft.action == "bin" and len(draft.bins) < 2 for draft in self.policy_drafts.values()
        ):
            messagebox.showerror(
                "SafeSet", "Set at least two bins for each binned column.", parent=self.root
            )
            return
        if any(
            draft.action == "keep_numeric"
            and (draft.bounds is None or draft.max_decimal_places is None)
            for draft in self.policy_drafts.values()
        ):
            messagebox.showerror(
                "SafeSet",
                "Set bounds and decimal places for exact numeric columns.",
                parent=self.root,
            )
            return
        if not self.policy_output.get().strip():
            messagebox.showerror("SafeSet", "Choose a new policy YAML filename.", parent=self.root)
            return
        try:
            source = Path(self.policy_source.get())
            path = save_policy(
                source,
                Path(self.policy_output.get()),
                self.policy_drafts,
                self.policy_threshold.get(),
                _selected_sheets(self.policy_sheet),
            )
            self.source.set(str(source))
            self.source_sheet.set(self.policy_sheet.get())
            self.policy.set(str(path))
            self.notebook.select(self.export_tab)
            messagebox.showinfo(
                "SafeSet",
                "Policy saved. Prepare the export to run the data checks.",
                parent=self.root,
            )
            record("desktop.policy.save", "success")
        except (SafetyError, OSError, UnicodeError) as error:
            self._error(error, "desktop.policy.save")

    def _build_export(self) -> None:
        actions = ttk.Frame(self.export_tab)
        actions.pack(side="bottom", fill="x", pady=(12, 0))
        canvas = tk.Canvas(self.export_tab, background=BACKGROUND, highlightthickness=0)
        self.export_canvas = canvas
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
        self.source_sheet = tk.StringVar()
        self.policy = tk.StringVar()
        self.output = tk.StringVar()
        self.map_path = tk.StringVar()
        for label, variable, save, kind in (
            ("Source Excel workbook", self.source, False, "xlsx"),
            ("Policy YAML", self.policy, False, "yaml"),
            ("New export Excel workbook", self.output, True, "xlsx"),
            ("Encrypted map", self.map_path, True, "enc"),
        ):
            _path_row(tab, label, variable, save=save, kind=kind)
            variable.trace_add("write", self._invalidate_review)
            if variable is self.source:
                self.source_sheet.trace_add("write", self._invalidate_review)
                _sheet_row(tab, self.source, self.source_sheet)
        ttk.Label(
            tab,
            text=(
                "Leave map blank for a random name in the private SafeSet map directory. "
                "Store it separately from exports."
            ),
            style="Muted.TLabel",
            wraplength=540,
        ).pack(anchor="w", pady=(3, 14))
        ttk.Label(
            tab,
            text=(
                "The export filename must be new. Its parent directory must already "
                "exist outside a repository."
            ),
            style="Muted.TLabel",
            wraplength=540,
        ).pack(anchor="w", pady=(0, 12))
        self.export_status = ttk.Label(tab, text="No review yet.", style="Muted.TLabel")
        self.export_status.pack(anchor="w", pady=(8, 0))
        self.review_text = ttk.Label(
            tab, text="Choose the files, then prepare a review.", justify="left", wraplength=540
        )
        self.review_text.pack(anchor="w", pady=(8, 12))
        ttk.Button(actions, text="Prepare review", command=self._prepare).pack(side="left")
        self.approve_button = ttk.Button(
            actions,
            text="Approve export and create map",
            style="Accent.TButton",
            command=self._approve,
        )
        self.approve_button.pack(side="left", padx=(10, 0))
        self.approve_button.state(["disabled"])

    def _invalidate_review(self, *_args: object) -> None:
        self.review = None
        self.export_status.configure(text="Review needed", style="Muted.TLabel")
        self.review_text.configure(text="Inputs changed. Prepare and validate again.")
        self.approve_button.state(["disabled"])

    def _prepare(self) -> None:
        record("desktop.export.prepare", "start")
        self.review = None
        self.approve_button.state(["disabled"])
        try:
            review = prepare_export(
                Path(self.source.get()),
                Path(self.policy.get()),
                Path(self.output.get()),
                Path(self.map_path.get()) if self.map_path.get().strip() else None,
                _selected_sheets(self.source_sheet),
            )
            self.review = review
            report = review.validation
            record("desktop.export.prepare", "candidate_ready")
            if report.passed:
                record("desktop.export.prepare", "validation_passed")
            else:
                record("desktop.export.prepare", "rejected")
            verdict = (
                "Validation passed · Review before approving"
                if report.passed
                else "Validation blocked this export"
            )
            self.export_status.configure(
                text=verdict, style="Success.TLabel" if report.passed else "Blocked.TLabel"
            )
            details = [
                f"Source: {review.source_rows:,} rows, {review.source_columns} columns",
                f"Worksheets: {len(review.sheet or ()) or 1} selected",
                f"Dropped columns: {review.dropped_columns}",
                f"Export columns: {len(review.policy.output_columns)}",
                f"Minimum joint group: {report.minimum_class_size}",
                f"Records in small joint groups: {report.small_class_records}",
                f"Unique records: {report.unique_records}",
                f"Small retained-value groups: {report.small_cells}",
                f"Export destination: {review.output}",
                f"Encrypted map destination: {review.map_path}",
            ]
            if review.formula_cells:
                details.append(f"Saved formula results used: {review.formula_cells}")
            details += [f"Error: {error}" for error in report.errors]
            details += [f"Warning: {warning}" for warning in report.warnings]
            if review.formula_cells:
                details.append(
                    "Warning: Formula results may be stale. Recalculate and save the "
                    "source workbook locally before approving this export."
                )
            details.append("Policy decisions:")
            details += [
                f"  {name}: {ACTION_LABELS[rule.action]} ({rule.classification})"
                for name, rule in review.policy.columns.items()
            ]
            details.append(
                "Check the intended recipient and whether each retained attribute is necessary."
            )
            self.review_text.configure(text="\n".join(details))
            self.root.update_idletasks()
            bounds = self.export_canvas.bbox("all")
            if bounds:
                self.export_canvas.yview_moveto(self.review_text.winfo_y() / max(1, bounds[3]))
            if report.passed:
                self.approve_button.state(["!disabled"])
        except (SafetyError, OSError, UnicodeError) as error:
            self.export_status.configure(text="Preparation failed", style="Blocked.TLabel")
            self.review_text.configure(text="Preparation failed. No artefacts created.")
            self._error(error, "desktop.export.prepare")

    def _approve(self) -> None:
        review = self.review
        if review is None or not review.validation.passed:
            return
        record("desktop.export.approve", "start")
        if not messagebox.askyesno(
            "Approve export",
            "Create the minimised Excel workbook and a separate encrypted identity map?\n\n"
            "Confirm the intended recipient is suitable. "
            "Passing checks does not establish anonymity.",
            parent=self.root,
            default="no",
        ):
            record("desktop.export.approve", "declined")
            return
        passphrase = _passphrase(self.root, confirm=True)
        if passphrase is None:
            record("desktop.export.approve", "declined")
            return
        record("desktop.export.approve", "approval_received")
        try:
            approve_export(review, passphrase, approved=True)
            self.review = None
            self.approve_button.state(["disabled"])
            self.export_status.configure(text="Export complete", style="Success.TLabel")
            self.result_map.set(str(review.map_path))
            self.review_text.configure(
                text=(
                    f"Export Excel workbook: {review.output}\n"
                    f"Encrypted map: {review.map_path}\n\n"
                    "The map path is ready in Restore. Keep the map private and separate."
                )
            )
            messagebox.showinfo(
                "SafeSet",
                "Export complete. The map path is ready in Restore. "
                "Keep the encrypted map local and separate.",
                parent=self.root,
            )
            record("desktop.export.approve", "published")
        except (SafetyError, OSError, UnicodeError) as error:
            self.review = None
            self.approve_button.state(["disabled"])
            self.export_status.configure(text="Export failed", style="Blocked.TLabel")
            self.review_text.configure(
                text=(
                    f"Planned export: {review.output}\n"
                    f"Map destination: {review.map_path}\n\n"
                    "Check these destinations before preparing a new review."
                )
            )
            self._error(error, "desktop.export.approve")

    def _build_restore(self) -> None:
        canvas = tk.Canvas(self.restore_tab, background=BACKGROUND, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.restore_tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        tab = ttk.Frame(canvas, padding=(0, 0, 15, 16))
        window = canvas.create_window((0, 0), window=tab, anchor="nw")
        tab.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        ttk.Label(tab, text="Restore authorised results", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(
            tab,
            text="Choose the returned workbook, then select results to join to source keys.",
            style="Muted.TLabel",
            wraplength=540,
        ).pack(anchor="w", pady=(5, 15))
        self.result_source = tk.StringVar()
        self.result_source.trace_add("write", self._invalidate_returned_review)
        self.result_sheet = tk.StringVar()
        self.result_sheet.trace_add("write", self._invalidate_returned_review)
        self.result_map = tk.StringVar()
        self.result_output = tk.StringVar()
        _path_row(tab, "Analysed Excel workbook", self.result_source)
        _sheet_row(tab, self.result_source, self.result_sheet)
        ttk.Button(tab, text="Read result columns", command=self._inspect_returned).pack(
            anchor="w", pady=(10, 8)
        )
        self.returned_status = ttk.Label(
            tab, text="No returned Excel workbook reviewed yet.", style="Muted.TLabel"
        )
        self.returned_status.pack(anchor="w")
        ttk.Label(tab, text="Approve returned columns").pack(anchor="w", pady=(14, 4))
        ttk.Label(
            tab,
            text=(
                "Tick every result column in this Excel workbook. To omit one, remove it from the "
                "analysed workbook and read it again. record_id is matched automatically."
            ),
            style="Muted.TLabel",
            wraplength=540,
        ).pack(anchor="w")
        choices_box = ttk.Frame(tab)
        choices_box.pack(fill="x", pady=(7, 14))
        self.returned_canvas = tk.Canvas(
            choices_box, height=100, background=BACKGROUND, highlightthickness=1
        )
        choices_scroll = ttk.Scrollbar(
            choices_box, orient="vertical", command=self.returned_canvas.yview
        )
        self.returned_canvas.configure(yscrollcommand=choices_scroll.set)
        choices_scroll.pack(side="right", fill="y")
        self.returned_canvas.pack(side="left", fill="x", expand=True)
        self.returned_choices_frame = ttk.Frame(self.returned_canvas)
        window = self.returned_canvas.create_window(
            (0, 0), window=self.returned_choices_frame, anchor="nw"
        )
        self.returned_choices_frame.bind(
            "<Configure>",
            lambda _event: self.returned_canvas.configure(
                scrollregion=self.returned_canvas.bbox("all")
            ),
        )
        self.returned_canvas.bind(
            "<Configure>",
            lambda event: self.returned_canvas.itemconfigure(window, width=event.width),
        )
        self.returned_choices: dict[str, tk.BooleanVar] = {}
        _path_row(tab, "Encrypted map", self.result_map, kind="enc")
        _path_row(tab, "New restored Excel workbook", self.result_output, save=True)
        ttk.Label(
            tab,
            text=("Choose a new filename in an existing private directory outside a repository."),
            style="Muted.TLabel",
            wraplength=540,
        ).pack(anchor="w", pady=(4, 2))
        ttk.Button(
            tab, text="Authorise local restoration", style="Accent.TButton", command=self._restore
        ).pack(anchor="w", pady=(16, 0))

    def _invalidate_returned_review(self, *_args: object) -> None:
        self.returned_review = None
        if hasattr(self, "returned_status"):
            self.returned_status.configure(
                text="Analysed Excel workbook changed. Read its columns again."
            )
            for child in self.returned_choices_frame.winfo_children():
                child.destroy()
            self.returned_choices.clear()

    def _inspect_returned(self) -> None:
        record("desktop.restore.review", "start")
        self._invalidate_returned_review()
        try:
            review = inspect_returned(
                Path(self.result_source.get()), _selected_sheets(self.result_sheet)
            )
            self.returned_review = review
            self.returned_status.configure(
                text=(
                    f"{review.rows:,} rows · {len(review.result_columns)} result columns "
                    f"across {len(review.sheet or ()) or 1} worksheet(s) to review."
                )
            )
            for column in review.result_columns:
                selected = tk.BooleanVar(value=False)
                self.returned_choices[column] = selected
                ttk.Checkbutton(self.returned_choices_frame, text=column, variable=selected).pack(
                    anchor="w", pady=2
                )
            record("desktop.restore.review", "success")
        except (SafetyError, OSError, UnicodeError) as error:
            self._error(error, "desktop.restore.review")

    def _restore(self) -> None:
        record("desktop.restore.publish", "start")
        review = self.returned_review
        if review is None:
            messagebox.showerror(
                "SafeSet", "Read the returned Excel workbook before restoring.", parent=self.root
            )
            return
        columns = tuple(name for name, selected in self.returned_choices.items() if selected.get())
        if not columns:
            messagebox.showerror("SafeSet", "Select at least one result column.", parent=self.root)
            return
        if len(columns) != len(review.result_columns):
            messagebox.showerror(
                "SafeSet",
                "Approve every returned result column, or remove unwanted columns "
                "from the analysed Excel workbook and read it again.",
                parent=self.root,
            )
            return
        analysed = Path(self.result_source.get())
        mapping = Path(self.result_map.get())
        output = Path(self.result_output.get())
        try:
            output_destination(output, analysed, mapping)
            check_map_read(mapping, analysed, output)
        except (SafetyError, OSError, UnicodeError) as error:
            self._error(error, "desktop.restore.publish")
            return
        if not messagebox.askyesno(
            "Authorise restoration",
            f"Restore {review.rows:,} rows with {len(columns)} approved result columns?\n\n"
            "This creates sensitive plaintext at the new destination you chose.",
            parent=self.root,
            default="no",
        ):
            record("desktop.restore.publish", "declined")
            return
        passphrase = _passphrase(self.root, confirm=False)
        if passphrase is None:
            record("desktop.restore.publish", "declined")
            return
        record("desktop.restore.publish", "approval_received")
        try:
            rows = restore_results(
                analysed,
                mapping,
                output,
                columns,
                passphrase,
                authorised=True,
                sheet=_selected_sheets(self.result_sheet),
            )
            messagebox.showinfo(
                "SafeSet",
                f"Restored {rows:,} rows locally. Keep this plaintext file private.",
                parent=self.root,
            )
            record("desktop.restore.publish", "published")
        except (SafetyError, OSError, UnicodeError) as error:
            self._error(error, "desktop.restore.publish")


def main() -> None:
    record("desktop.app", "start")
    try:
        root = tk.Tk()
    except tk.TclError:
        record("desktop.app", "io_error")
        raise SystemExit(
            "SafeSet desktop requires a working local display and Tk installation."
        ) from None
    Desktop(root)
    root.mainloop()
    record("desktop.app", "closed")


if __name__ == "__main__":
    main()
