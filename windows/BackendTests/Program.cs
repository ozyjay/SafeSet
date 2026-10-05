using System.Diagnostics;
using System.Text.Json;
using SafeSetWindows;

// Test harness only. Use synthetic inputs; production UI never prints replies.
if (args.Length != 2) return 2;
ProcessStartInfo Helper()
{
    var info = new ProcessStartInfo(args[1]);
    if (args[0] == "python")
    {
        info.ArgumentList.Add("-I");
        info.ArgumentList.Add("-m");
        info.ArgumentList.Add("safeset.desktop_bridge");
    }
    else if (args[0].StartsWith("fake:", StringComparison.Ordinal))
    {
        info.ArgumentList.Add("-I");
        info.ArgumentList.Add(args[0][5..]);
    }
    else if (args[0].StartsWith("fake:", StringComparison.Ordinal))
    {
        info.ArgumentList.Add("-I");
        info.ArgumentList.Add(args[0][5..]);
    }
    info.Environment.Remove("PYTHONHOME");
    info.Environment.Remove("PYTHONPATH");
    return info;
}
using var backend = new BackendBridge(Helper, args[0].StartsWith("fake:") ? TimeSpan.FromSeconds(1) : null);
while (Console.ReadLine() is string line)
{
    try
    {
        using var request = JsonDocument.Parse(line);
        var root = request.RootElement;
        var result = await backend.RequestAsync(root.GetProperty("command").GetString()!, root.GetProperty("payload"));
        Console.WriteLine(JsonSerializer.Serialize(new { ok = true, result }));
    }
    catch (Exception) { Console.WriteLine("{\"ok\":false,\"error\":\"backend_rejected\"}"); }
}
return 0;
