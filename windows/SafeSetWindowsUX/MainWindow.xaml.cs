using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System;
using System.Collections.Generic;
using System.Linq;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using Windows.Storage.Pickers;

namespace SafeSetWindows
{
    public sealed partial class MainWindow : Window
    {
        private readonly BackendBridge backend = new();

        public MainWindow()
        {
            InitializeComponent();
            Closed += (_, _) => backend.Dispose();
#if !DEBUG
            StatusBar.Title = "Windows release verification incomplete";
            StatusBar.Message = "Publication remains disabled until native interactions have been verified on Windows. Use the Debug build with synthetic fixtures for local verification.";
#endif
        }

        private void NavView_Loaded(object sender, RoutedEventArgs e)
        {
            NavigateTo("home");
        }

        private void NavView_SelectionChanged(
            NavigationView sender,
            NavigationViewSelectionChangedEventArgs args)
        {
            if (args.SelectedItemContainer?.Tag is string tag)
            {
                ShowPage(tag);
            }
        }

        private void NavigateTo(string tag)
        {
            foreach (var item in NavView.MenuItems.OfType<NavigationViewItem>())
            {
                if (string.Equals(item.Tag as string, tag, StringComparison.Ordinal))
                {
                    NavView.SelectedItem = item;
                    ShowPage(tag);
                    return;
                }
            }
        }

        private void ShowPage(string tag)
        {
            HomePage.Visibility = tag == "home" ? Visibility.Visible : Visibility.Collapsed;
            ProtectWorkbookPage.Visibility =
                tag == "protectWorkbook" ? Visibility.Visible : Visibility.Collapsed;
            ProtectDocumentPage.Visibility =
                tag == "protectDocument" ? Visibility.Visible : Visibility.Collapsed;
            RestoreWorkbookPage.Visibility =
                tag == "restoreWorkbook" ? Visibility.Visible : Visibility.Collapsed;
            RestoreDocumentPage.Visibility =
                tag == "restoreDocument" ? Visibility.Visible : Visibility.Collapsed;
            AdvancedPage.Visibility =
                tag == "advanced" ? Visibility.Visible : Visibility.Collapsed;
            HelpPage.Visibility =
                tag == "help" ? Visibility.Visible : Visibility.Collapsed;
        }

        private void HomeProtectWorkbook_Click(object sender, RoutedEventArgs e) =>
            NavigateTo("protectWorkbook");

        private void HomeProtectDocument_Click(object sender, RoutedEventArgs e) =>
            NavigateTo("protectDocument");

        private void HomeRestoreWorkbook_Click(object sender, RoutedEventArgs e) =>
            NavigateTo("restoreWorkbook");

        private void HomeRestoreDocument_Click(object sender, RoutedEventArgs e) =>
            NavigateTo("restoreDocument");

        private async Task<string?> PickOpenAsync(params string[] extensions)
        {
            var picker = new FileOpenPicker();
            foreach (var extension in extensions)
            {
                picker.FileTypeFilter.Add(extension);
            }

            var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(this);
            WinRT.Interop.InitializeWithWindow.Initialize(picker, hwnd);

            var file = await picker.PickSingleFileAsync();
            return file?.Path;
        }

        private async Task<string?> PickSaveAsync(
            string description,
            string extension,
            string suggestedName)
        {
            // A save-file picker may create a placeholder, violating no-clobber.
            // Choose an existing parent and a new name without touching the file.
            var picker = new FolderPicker();
            picker.FileTypeFilter.Add("*");
            var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(this);
            WinRT.Interop.InitializeWithWindow.Initialize(picker, hwnd);
            var folder = await picker.PickSingleFolderAsync();
            if (folder == null) return null;
            var name = new TextBox { Header = description, Text = suggestedName + extension };
            var subdirectory = new TextBox { Header = "New private subdirectory", Text = "SafeSetPrivate" };
            var content = new StackPanel { Spacing = 12 };
            content.Children.Add(name);
            if (extension == ".enc") content.Children.Add(subdirectory);
            var dialog = NewDialog("Choose a new destination", content, "Use destination");
            if (await dialog.ShowAsync() != ContentDialogResult.Primary) return null;
            static bool ValidName(string value) => !string.IsNullOrWhiteSpace(value) &&
                value != "." && value != ".." && value == Path.GetFileName(value) &&
                value.IndexOfAny(Path.GetInvalidFileNameChars()) < 0;
            if (!ValidName(name.Text) || !name.Text.EndsWith(extension, StringComparison.OrdinalIgnoreCase) ||
                (extension == ".enc" && !ValidName(subdirectory.Text)))
            {
                StatusBar.Title = "Destination needs a new name";
                StatusBar.Message = "Use a filename with the required extension and a simple private subdirectory name.";
                StatusBar.Severity = InfoBarSeverity.Warning;
                return null;
            }
            return extension == ".enc" ? Path.Combine(folder.Path, subdirectory.Text, name.Text) :
                Path.Combine(folder.Path, name.Text);
        }

        private async void BrowseWorkbookSource_Click(object sender, RoutedEventArgs e)
        {
            WorkbookSourcePath.Text = await PickOpenAsync(".xlsx") ?? WorkbookSourcePath.Text;
            await LoadWorkbookSheets();
        }

        private async void LoadWorkbookSheets_Click(object sender, RoutedEventArgs e) => await LoadWorkbookSheets();

        private async Task LoadWorkbookSheets()
        {
            await RunWorkflow(async () =>
            {
                var result = await backend.RequestAsync("list_sheets", new { path = WorkbookSourcePath.Text });
                WorkbookSheet.ItemsSource = result.GetProperty("sheets").EnumerateArray().Select(x => x.GetString()).ToArray();
                WorkbookSheet.SelectedIndex = 0;
            });
        }

        private async void BrowseWorkbookReturned_Click(object sender, RoutedEventArgs e)
        {
            WorkbookReturnedPath.Text = await PickOpenAsync(".xlsx") ?? WorkbookReturnedPath.Text;
        }

        private async void BrowseDocumentSource_Click(object sender, RoutedEventArgs e)
        {
            DocumentSourcePath.Text = await PickOpenAsync(".docx") ?? DocumentSourcePath.Text;

            if (!string.IsNullOrWhiteSpace(DocumentSourcePath.Text) &&
                string.IsNullOrWhiteSpace(DocumentProtectedPath.Text))
            {
                var source = DocumentSourcePath.Text;
                var separator = Math.Max(source.LastIndexOf('\\'), source.LastIndexOf('/'));
                var directory = separator >= 0 ? source[..(separator + 1)] : string.Empty;
                var file = separator >= 0 ? source[(separator + 1)..] : source;
                var stem = file.EndsWith(".docx", StringComparison.OrdinalIgnoreCase)
                    ? file[..^5]
                    : file;
                DocumentProtectedPath.Text = directory + stem + "-protected.docx";
            }
        }

        private async void ChooseProtectedDocument_Click(object sender, RoutedEventArgs e)
        {
            DocumentProtectedPath.Text =
                await PickSaveAsync("Word document", ".docx", "manuscript-protected")
                ?? DocumentProtectedPath.Text;
        }

        private async void ChooseDocumentBundle_Click(object sender, RoutedEventArgs e)
        {
            DocumentBundlePath.Text =
                await PickSaveAsync("SafeSet private bundle", ".enc", "document-restoration")
                ?? DocumentBundlePath.Text;
        }

        private async void BrowseDocumentReturned_Click(object sender, RoutedEventArgs e)
        {
            DocumentReturnedPath.Text =
                await PickOpenAsync(".docx") ?? DocumentReturnedPath.Text;
        }

        private async void BrowseDocumentRestoreBundle_Click(object sender, RoutedEventArgs e)
        {
            DocumentRestoreBundlePath.Text =
                await PickOpenAsync(".enc") ?? DocumentRestoreBundlePath.Text;
        }

        private async void ChooseRestoredDocument_Click(object sender, RoutedEventArgs e)
        {
            DocumentRestoredPath.Text =
                await PickSaveAsync("Word document", ".docx", "manuscript-restored")
                ?? DocumentRestoredPath.Text;
        }

        private ContentDialog NewDialog(string title, object content, string action) => new()
        {
            XamlRoot = NavView.XamlRoot,
            Title = title,
            Content = content,
            PrimaryButtonText = action,
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Close
        };

        private static TextBlock Text(string text) => new() { Text = text, TextWrapping = TextWrapping.Wrap };

        private async Task RunWorkflow(Func<Task> operation)
        {
#if !DEBUG
            StatusBar.Title = "Windows release verification incomplete";
            StatusBar.Message = "This Release build cannot handle operational workflows until native interactions are verified. Use the Debug build with synthetic fixtures.";
            await Task.CompletedTask;
            return;
#else
            NavView.IsEnabled = false;
            try
            {
                StatusBar.Title = "Checking locally";
                StatusBar.Message = "SafeSet is checking the selected inputs. Publication requires review and approval.";
                StatusBar.Severity = InfoBarSeverity.Informational;
                await operation();
            }
            catch (Exception)
            {
                StatusBar.Title = "Request blocked";
                StatusBar.Message = "Check the selected files, policy, passphrase and storage locations, then review again. Mandatory checks cannot be overridden. A failed publication may retain a private encrypted bundle.";
                StatusBar.Severity = InfoBarSeverity.Error;
            }
            finally { NavView.IsEnabled = true; }
#endif
        }

        private async Task CancelReview()
        {
            await backend.RequestAsync("cancel", new { });
            StatusBar.Title = "Cancelled";
            StatusBar.Message = "The review was cancelled. No publication was approved.";
            StatusBar.Severity = InfoBarSeverity.Informational;
        }

        private async Task<string?> Secret(bool confirm)
        {
            var first = new PasswordBox { Header = "Private bundle passphrase", PasswordRevealMode = PasswordRevealMode.Hidden };
            var second = new PasswordBox { Header = "Confirm passphrase", PasswordRevealMode = PasswordRevealMode.Hidden };
            var panel = new StackPanel { Spacing = 12 };
            panel.Children.Add(Text("Enter the passphrase locally. Keep it separately from the private bundle."));
            panel.Children.Add(first);
            if (confirm) panel.Children.Add(second);
            var dialog = NewDialog("Private bundle", panel, "Continue");
            dialog.IsPrimaryButtonEnabled = false;
            void Changed(object sender, RoutedEventArgs args) => dialog.IsPrimaryButtonEnabled =
                first.Password.Length >= 12 && (!confirm || first.Password == second.Password);
            first.PasswordChanged += Changed;
            second.PasswordChanged += Changed;
            try { return await dialog.ShowAsync() == ContentDialogResult.Primary ? first.Password : null; }
            finally { first.Password = ""; second.Password = ""; }
        }

        private void Complete(string message)
        {
            StatusBar.Title = "Completed locally";
            StatusBar.Message = message;
            StatusBar.Severity = InfoBarSeverity.Success;
        }

        private async void ProtectDocument_Click(object sender, RoutedEventArgs e) => await RunWorkflow(async () =>
        {
            var source = DocumentSourcePath.Text;
            var content = await backend.RequestAsync("review_document_content", new { source });
            var panel = new StackPanel { Spacing = 10, MaxWidth = 540 };
            panel.Children.Add(Text("Review the original document locally, including every figure. These suggestions are incomplete and image pixels are not analysed. Tick only paragraphs you want removed."));
            var figures = new List<(string Id, CheckBox Check)>();
            foreach (var item in content.GetProperty("figures").EnumerateArray())
            {
                var check = new CheckBox { Content = $"I reviewed figure {item.GetProperty("image")} in {item.GetProperty("part").GetString()}, paragraph {item.GetProperty("paragraph")}." };
                figures.Add((item.GetProperty("id").GetString()!, check));
                panel.Children.Add(check);
            }
            var paragraphs = new List<(string Id, CheckBox Check)>();
            foreach (var item in content.GetProperty("suggestions").EnumerateArray())
            {
                panel.Children.Add(Text(item.GetProperty("excerpt").GetString()!));
                var check = new CheckBox { Content = $"Remove paragraph {item.GetProperty("paragraph")} in {item.GetProperty("part").GetString()}" };
                paragraphs.Add((item.GetProperty("id").GetString()!, check));
                panel.Children.Add(check);
            }
            var contentDialog = NewDialog("Review document content", new ScrollViewer { Content = panel, MaxHeight = 450 }, "Prepare protection");
            contentDialog.IsPrimaryButtonEnabled = figures.Count == 0;
            foreach (var figure in figures)
            {
                figure.Check.Checked += (_, _) => contentDialog.IsPrimaryButtonEnabled = figures.All(x => x.Check.IsChecked == true);
                figure.Check.Unchecked += (_, _) => contentDialog.IsPrimaryButtonEnabled = false;
            }
            if (await contentDialog.ShowAsync() != ContentDialogResult.Primary) { await CancelReview(); return; }
            var terms = DocumentIdentityTerms.Text.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries)
                .Select(value => new { value = value.Trim(), kind = "other" }).ToArray();
            var review = await backend.RequestAsync("prepare_document_protection", new
            {
                source, output = DocumentProtectedPath.Text, bundle = DocumentBundlePath.Text, terms,
                remove_comments = RemoveDocumentComments.IsChecked == true,
                reviewed_figures = figures.Select(x => x.Id).ToArray(),
                remove_paragraphs = paragraphs.Where(x => x.Check.IsChecked == true).Select(x => x.Id).ToArray(),
                review_digest = content.GetProperty("source_digest").GetString()
            });
            var summary = Text($"Validation passed. Protect {review.GetProperty("replacement_count")} distinct identifiers in {review.GetProperty("replacement_occurrences")} occurrences.\nComments removed: {review.GetProperty("comments_removed")}\nProtected document: {review.GetProperty("output").GetString()}\nPrivate bundle: {review.GetProperty("bundle").GetString()}\n\nKeep the bundle outside export folders and cloud synchronisation. Passing checks does not establish anonymity or recipient suitability.");
            if (await NewDialog("Approve document protection", summary, "Approve creation").ShowAsync() != ContentDialogResult.Primary)
            { await CancelReview(); return; }
            var passphrase = await Secret(true);
            if (passphrase == null) { await CancelReview(); return; }
            await backend.RequestAsync("approve_document_protection", new { review_id = review.GetProperty("review_id").GetString(), passphrase });
            Complete("Created the protected document and separate encrypted private bundle. Review the protected document before sharing it.");
        });

        private async void RestoreDocument_Click(object sender, RoutedEventArgs e) => await RunWorkflow(async () =>
        {
            var passphrase = await Secret(false);
            if (passphrase == null) { await CancelReview(); return; }
            var review = await backend.RequestAsync("prepare_document_restoration", new
            {
                returned = DocumentReturnedPath.Text, bundle = DocumentRestoreBundlePath.Text,
                output = DocumentRestoredPath.Text, passphrase
            });
            var summary = Text($"Token integrity passed. Restore {review.GetProperty("replacement_count")} identifiers in {review.GetProperty("replacement_occurrences")} occurrences.\nNew identifiable document: {review.GetProperty("output").GetString()}\n\nKeep this document privately and review the returned content locally.");
            if (await NewDialog("Approve document restoration", summary, "Approve restoration").ShowAsync() != ContentDialogResult.Primary)
            { await CancelReview(); return; }
            await backend.RequestAsync("approve_document_restoration", new { review_id = review.GetProperty("review_id").GetString() });
            Complete("Created a new locally restored document. The returned document was not modified.");
        });

        private async void BrowseWorkbookPolicy_Click(object sender, RoutedEventArgs e) =>
            WorkbookPolicyPath.Text = await PickOpenAsync(".yaml", ".yml") ?? WorkbookPolicyPath.Text;

        private async void ChooseProtectedWorkbook_Click(object sender, RoutedEventArgs e) =>
            WorkbookProtectedPath.Text = await PickSaveAsync("Protected workbook", ".xlsx", "workbook-protected") ?? WorkbookProtectedPath.Text;

        private async void ChooseWorkbookBundle_Click(object sender, RoutedEventArgs e) =>
            WorkbookBundlePath.Text = await PickSaveAsync("Private bundle", ".enc", "workbook-restoration") ?? WorkbookBundlePath.Text;

        private async void BrowseWorkbookOriginal_Click(object sender, RoutedEventArgs e) =>
            WorkbookOriginalPath.Text = await PickOpenAsync(".xlsx") ?? WorkbookOriginalPath.Text;

        private async void BrowseWorkbookRestoreBundle_Click(object sender, RoutedEventArgs e) =>
            WorkbookRestoreBundlePath.Text = await PickOpenAsync(".enc") ?? WorkbookRestoreBundlePath.Text;

        private async void ChooseRestoredWorkbook_Click(object sender, RoutedEventArgs e) =>
            WorkbookRestoredPath.Text = await PickSaveAsync("Restored workbook", ".xlsx", "workbook-restored") ?? WorkbookRestoredPath.Text;

        private async void ProtectWorkbook_Click(object sender, RoutedEventArgs e) => await RunWorkflow(async () =>
        {
            var source = WorkbookSourcePath.Text;
            var sheet = WorkbookSheet.SelectedItem as string;
            if (string.IsNullOrWhiteSpace(sheet)) throw new BackendException();
            var policy = await backend.RequestAsync("load_policy", new { source, sheet, policy = WorkbookPolicyPath.Text });
            var review = await backend.RequestAsync("prepare_protection", new
            {
                source, sheet, output = WorkbookProtectedPath.Text, bundle = WorkbookBundlePath.Text,
                drafts = policy.GetProperty("drafts"), threshold = policy.GetProperty("threshold").GetInt32().ToString(System.Globalization.CultureInfo.InvariantCulture),
                validation_profile = "strict"
            });
            var validation = review.GetProperty("validation");
            var summary = new StackPanel { Spacing = 10, MaxWidth = 540 };
            summary.Children.Add(Text($"Rows: {review.GetProperty("rows")}\nRemoved fields: {review.GetProperty("removed")}\nObfuscated fields: {review.GetProperty("obfuscated")}\nRetained fields: {review.GetProperty("retained")}\nValidation: {validation}\nProtected workbook: {review.GetProperty("output").GetString()}\nPrivate bundle: {review.GetProperty("bundle").GetString()}"));
            foreach (var field in policy.GetProperty("drafts").EnumerateObject())
                summary.Children.Add(Text($"{field.Name}: {field.Value.GetProperty("classification").GetString()} / {field.Value.GetProperty("action").GetString()}"));
            summary.Children.Add(Text("All protected source fields remain immutable. Approve new result columns during restoration. Passing checks does not establish anonymity or recipient suitability."));
            var dialog = NewDialog("Review workbook protection", new ScrollViewer { Content = summary, MaxHeight = 450 }, "Approve creation");
            dialog.IsPrimaryButtonEnabled = validation.GetProperty("passed").GetBoolean();
            if (await dialog.ShowAsync() != ContentDialogResult.Primary) { await CancelReview(); return; }
            var passphrase = await Secret(true);
            if (passphrase == null) { await CancelReview(); return; }
            await backend.RequestAsync("approve_protection", new { review_id = review.GetProperty("review_id").GetString(), passphrase });
            Complete("Created the protected workbook and separate private bundle. Source fields are immutable; add results as new columns.");
        });

        private async void RestoreWorkbook_Click(object sender, RoutedEventArgs e) => await RunWorkflow(async () =>
        {
            var passphrase = await Secret(false);
            if (passphrase == null) { await CancelReview(); return; }
            var relational = WorkbookRelationalRestore.IsChecked == true;
            var request = new Dictionary<string, object?>
            {
                ["returned"] = WorkbookReturnedPath.Text, ["source"] = WorkbookOriginalPath.Text,
                ["bundle"] = WorkbookRestoreBundlePath.Text, ["output"] = WorkbookRestoredPath.Text,
                ["passphrase"] = passphrase
            };
            if (!relational)
            {
                request["returned_sheet"] = null;
                request["source_sheet"] = string.IsNullOrWhiteSpace(WorkbookOriginalSheet.Text) ? null : WorkbookOriginalSheet.Text;
            }
            var review = await backend.RequestAsync(relational ? "prepare_relational_reconstruction" : "prepare_reconstruction", request);
            var panel = new StackPanel { Spacing = 10, MaxWidth = 540 };
            panel.Children.Add(Text($"Integrity checks passed. Rows: {review.GetProperty("rows")}\nNew identifiable workbook: {review.GetProperty("output").GetString()}\nSelect every result field, analysis sheet and changed field you explicitly approve."));
            var results = new Dictionary<string, List<(string Name, CheckBox Check)>>();
            void AddFields(string sheet, JsonElement fields)
            {
                results[sheet] = new();
                foreach (var field in fields.EnumerateArray())
                {
                    var name = field.GetString()!;
                    var check = new CheckBox { Content = $"Approve new result field: {sheet} / {name}" };
                    results[sheet].Add((name, check)); panel.Children.Add(check);
                }
            }
            if (relational)
                foreach (var sheet in review.GetProperty("new_columns").EnumerateObject()) AddFields(sheet.Name, sheet.Value);
            else AddFields("", review.GetProperty("new_columns"));
            var sheets = new List<(string Name, CheckBox Check)>();
            foreach (var item in review.GetProperty("new_sheets").EnumerateArray())
            {
                var name = item.GetString()!;
                var check = new CheckBox { Content = $"Approve added analysis worksheet: {name}" };
                sheets.Add((name, check)); panel.Children.Add(check);
            }
            var changes = new Dictionary<string, List<(string Name, CheckBox Check)>>();
            if (relational && review.GetProperty("changes").ValueKind == JsonValueKind.Object)
                foreach (var sheet in review.GetProperty("changes").EnumerateObject())
                {
                    changes[sheet.Name] = new();
                    foreach (var field in sheet.Value.EnumerateObject())
                    {
                        var check = new CheckBox { Content = $"Approve {field.Value} changed cells: {sheet.Name} / {field.Name}" };
                        changes[sheet.Name].Add((field.Name, check)); panel.Children.Add(check);
                    }
                }
            var dialog = NewDialog("Approve workbook restoration", new ScrollViewer { Content = panel, MaxHeight = 450 }, "Approve restoration");
            var all = results.Values.SelectMany(x => x).Select(x => x.Check).Concat(sheets.Select(x => x.Check)).Concat(changes.Values.SelectMany(x => x).Select(x => x.Check)).ToArray();
            dialog.IsPrimaryButtonEnabled = all.Length == 0;
            foreach (var check in all)
            {
                check.Checked += (_, _) => dialog.IsPrimaryButtonEnabled = all.All(x => x.IsChecked == true);
                check.Unchecked += (_, _) => dialog.IsPrimaryButtonEnabled = false;
            }
            if (await dialog.ShowAsync() != ContentDialogResult.Primary) { await CancelReview(); return; }
            var approval = new Dictionary<string, object?>
            {
                ["review_id"] = review.GetProperty("review_id").GetString(),
                ["approved_results"] = relational ? results.ToDictionary(x => x.Key, x => x.Value.Select(y => y.Name).ToArray()) : results[""].Select(x => x.Name).ToArray(),
                ["approved_sheets"] = sheets.Select(x => x.Name).ToArray()
            };
            if (relational && review.GetProperty("changes").ValueKind == JsonValueKind.Object)
                approval["approved_changes"] = changes.ToDictionary(x => x.Key, x => x.Value.Select(y => y.Name).ToArray());
            await backend.RequestAsync(relational ? "approve_relational_reconstruction" : "approve_reconstruction", approval);
            Complete("Created a new locally restored workbook. Review the results in Excel and recalculate any formulas.");
        });
    }
}
