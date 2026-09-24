using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Windows.Storage.Pickers;

namespace SafeSetWindows
{
    public sealed partial class MainWindow : Window
    {
        public MainWindow()
        {
            InitializeComponent();
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
            var picker = new FileSavePicker
            {
                SuggestedFileName = suggestedName
            };
            picker.FileTypeChoices.Add(description, new List<string> { extension });

            var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(this);
            WinRT.Interop.InitializeWithWindow.Initialize(picker, hwnd);

            var file = await picker.PickSaveFileAsync();
            return file?.Path;
        }

        private async void BrowseWorkbookSource_Click(object sender, RoutedEventArgs e)
        {
            WorkbookSourcePath.Text = await PickOpenAsync(".xlsx") ?? WorkbookSourcePath.Text;
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

        private void PreviewOnly_Click(object sender, RoutedEventArgs e)
        {
            StatusBar.Severity = InfoBarSeverity.Warning;
            StatusBar.Title = "Windows UX preview";
            StatusBar.Message =
                "This screen is interactive, but SafeSet is not publishing protected or restored files on Windows yet. The Windows ACL private-storage gate must be completed first.";
            StatusBar.IsOpen = true;
        }
    }
}
