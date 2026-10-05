# Platform branches

The local `windows` branch contains the native WinUI frontend and Windows build scripts. The local `mac` branch contains the native SwiftUI frontend and macOS build scripts. Both retain the shared Python safety engine, bounded desktop protocol, CLI, tests, fixtures and security documentation. `main` preserves the original combined codebase and history.

Do not fork validation, approval, private-storage or restoration rules into either native frontend. Merge shared engine fixes across both platform branches. Platform-specific native files are maintained on their corresponding branch. Publishing either branch requires an explicit instruction.

## Windows history reconstruction — 5 October 2026

Baseline: `d1f9539`, immediately before the Windows foundation commits. The following commits were cherry-picked in topological order. For mixed commits, macOS frontend/build files, the macOS packaging guide and macOS VS Code task/launch files were excluded. Each replayed commit records its original full commit ID in its message. The inherited macOS frontend/build files were then removed in a separate layout commit.

Before layout removal, comparisons against `main` at `03b7fb8` confirmed exact equality for `src`, `tests`, `pyproject.toml`, `examples`, `.github`, `windows` and every Windows script. This checks the final files as well as the selected history. The Windows storage module and its tests remain shared engine code on the Mac branch.

| Original commit | Change |
| --- | --- |
| `c8986dd` | docs: make SafeSet cross-platform and artefact-oriented |
| `e8b11a9` | docs: define native Windows desktop target |
| `5120904` | build: add WinUI 3 bootstrap script |
| `ad53f5a` | docs: document DOCX and cross-platform desktop architecture |
| `7bdb227` | docs: document DOCX and cross-platform desktop architecture |
| `a4be5bd` | docs: document DOCX and cross-platform desktop architecture |
| `66ea612` | docs: document DOCX and cross-platform desktop architecture |
| `64750e3` | docs: define DOCX safety model |
| `0504fdd` | fix: report distinct DOCX identifiers in inspection |
| `fa74eab` | feat: add native WinUI SafeSet shell |
| `dc160f3` | feat: add Windows navigation and file-picker UX |
| `39fbacf` | build: add repeatable Windows UX overlay |
| `47e70f2` | fix: make WinUI shell XAML self-contained |
| `c0daef6` | build: apply SafeSet UX during Windows bootstrap |
| `431f3e3` | chore: ignore generated local WinUI project |
| `b86777b` | docs: explain runnable Windows UX overlay |
| `0672ad4` | build: add Windows UX smoke check |
| `829fe5d` | refactor: reorganize Windows UX project structure and update scripts |
| `e509658` | Implement Windows private storage with NTFS ACL validation |
| `5c0423d` | refactor: enhance restoration guidance and validation messages for protected worksheets |
| `7238e90` | refactor: update restoration guidance and validation for protected worksheets and schemas |
| `ff94eb2` | refactor: enhance analysis prompt and user guidance for protected workbook handling |
| `5f5e34f` | refactor: enhance guidance for analysis worksheets and restoration result examples |
| `d2bdcbe` | feat: Enhance editable workbook functionality and validation |
| `9940ed6` | Enhance editable workbook handling and validation |
| `627a178` | refactor: update documentation and error messages for clarity and consistency across the application |
| `dc860cc` | Implement participant reconciliation and approval process |
| `c266d4e` | feat: enhance participant mapping and validation with source sheet support |
| `cbb2961` | feat: update terminology from 'reference sheet' to 'membership sheet' for clarity in participant comparison |
| `bcf5a40` | feat: add support for bundle permissions inspection and development passphrase handling in macOS app |
| `4251719` | feat: enhance analysis task instructions and prompt handling in macOS app |
| `a9f8a04` | feat: add result workbook restoration design documentation |
| `76f074c` | feat: Implement result workbook restoration and approval process |
| `160b58e` | feat: Enhance result workbook handling for new rows with blank record IDs and improve validation checks |
| `9a2eea4` | feat: Enhance error handling and validation for review expiration in desktop bridge and related components |
| `192f9a2` | feat: Refactor result workbook restoration process and update UI prompts for improved clarity |
| `3ad92e3` | feat: Enhance document protection with figure and paragraph review |
| `03b7fb8` | feat: Add VS Code workspace settings to exclude build directories from file discovery and search |

Excluded macOS-only commits: `7eb0285`, `f13adda`, `48de1d6`, `a8a35cb`, `8dcf5ef`, `6e336dc`, `186ca62`.

The current uncommitted Windows setup/backend work was preserved in the named Git stash `SafeSet Windows setup and backend work before platform branch reconstruction` before replay. It is reapplied only after the branch split is verified. No branch was pushed as part of this operation.
