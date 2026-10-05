using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace SafeSetWindows;

// No requests, responses, paths, stderr or exception payloads are logged.
internal sealed class BackendException : Exception
{
    public BackendException() : base("SafeSet could not complete this request. Check the selected files, storage locations and review decisions, then review again.") { }
}

internal sealed class BackendBridge : IDisposable
{
    private const int FrameLimit = 1024 * 1024;
    private readonly SemaphoreSlim serial = new(1, 1);
    private readonly Func<ProcessStartInfo> startInfo;
    private readonly TimeSpan requestTimeout;
    private Process? helper;
    private BufferedStream? responses;

    public BackendBridge() : this(LocateHelper) { }
    internal BackendBridge(Func<ProcessStartInfo> startInfo, TimeSpan? requestTimeout = null)
    {
        this.startInfo = startInfo;
        this.requestTimeout = requestTimeout ?? TimeSpan.FromMinutes(2);
    }

    private static ProcessStartInfo LocateHelper()
    {
        var bundled = Path.Combine(AppContext.BaseDirectory, "engine", "SafeSetHelper", "SafeSetHelper.exe");
        if (File.Exists(bundled)) return new ProcessStartInfo(bundled);
        // Development only: resolve a specific checkout interpreter, never search PATH.
        for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory != null; directory = directory.Parent)
        {
            if (!File.Exists(Path.Combine(directory.FullName, "AGENTS.md")) ||
                !File.Exists(Path.Combine(directory.FullName, "pyproject.toml"))) continue;
            var python = Path.Combine(directory.FullName, ".venv", "Scripts", "python.exe");
            if (!File.Exists(python)) break;
            var info = new ProcessStartInfo(python) { WorkingDirectory = directory.FullName };
            info.ArgumentList.Add("-I");
            info.ArgumentList.Add("-m");
            info.ArgumentList.Add("safeset.desktop_bridge");
            return info;
        }
        throw new BackendException();
    }

    private void Start()
    {
        if (helper != null && !helper.HasExited) return;
        Stop();
        var info = startInfo();
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        info.RedirectStandardInput = true;
        info.RedirectStandardOutput = true;
        info.RedirectStandardError = true;
        helper = Process.Start(info) ?? throw new BackendException();
        responses = new BufferedStream(helper.StandardOutput.BaseStream, 4096);
        _ = DiscardErrors(helper.StandardError.BaseStream);
    }

    private static async Task DiscardErrors(Stream stream)
    {
        var buffer = new byte[4096];
        try { while (await stream.ReadAsync(buffer) > 0) { } }
        catch (Exception) { /* discard diagnostics; never expose payloads */ }
    }

    private byte[] ReadFrame()
    {
        using var frame = new MemoryStream();
        while (frame.Length <= FrameLimit)
        {
            var value = responses!.ReadByte();
            if (value < 0) throw new BackendException();
            if (value == 10) return frame.ToArray();
            frame.WriteByte((byte)value);
        }
        throw new BackendException();
    }

    private static void UniqueProperties(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in value.EnumerateObject())
            {
                if (!names.Add(property.Name)) throw new BackendException();
                UniqueProperties(property.Value);
            }
        }
        else if (value.ValueKind == JsonValueKind.Array)
            foreach (var item in value.EnumerateArray()) UniqueProperties(item);
    }

    public async Task<JsonElement> RequestAsync(string command, object payload)
    {
        await serial.WaitAsync();
        try
        {
            Start();
            var id = Guid.NewGuid().ToString();
            var request = JsonSerializer.SerializeToUtf8Bytes(new { version = 1, id, command, payload });
            if (request.Length + 1 > FrameLimit) throw new BackendException();
            using var timeout = new CancellationTokenSource(requestTimeout);
            await helper!.StandardInput.BaseStream.WriteAsync(request, timeout.Token);
            await helper.StandardInput.BaseStream.WriteAsync(new byte[] { 10 }, timeout.Token);
            await helper.StandardInput.BaseStream.FlushAsync(timeout.Token);
            var response = await Task.Run(ReadFrame).WaitAsync(timeout.Token);
            if (response.Length > FrameLimit) throw new BackendException();
            // Reject invalid UTF-8 rather than replacing bytes silently.
            var decoded = new UTF8Encoding(false, true).GetString(response);
            using var document = JsonDocument.Parse(decoded, new JsonDocumentOptions { MaxDepth = 64 });
            var root = document.RootElement;
            UniqueProperties(root);
            if (root.ValueKind != JsonValueKind.Object || root.GetProperty("version").GetInt32() != 1 ||
                root.GetProperty("id").GetString() != id) throw new BackendException();
            var ok = root.GetProperty("ok").GetBoolean();
            var expected = new HashSet<string>(new[] { "version", "id", "ok", ok ? "result" : "error" });
            if (!expected.SetEquals(root.EnumerateObject().Select(item => item.Name))) throw new BackendException();
            if (!ok) throw new BackendException();
            var result = root.GetProperty("result");
            if (result.ValueKind != JsonValueKind.Object) throw new BackendException();
            return result.Clone();
        }
        catch (Exception)
        {
            Stop(); // Any uncertainty invalidates pending reviews and authentication.
            throw new BackendException();
        }
        finally { serial.Release(); }
    }

    private void Stop()
    {
        try { if (helper != null && !helper.HasExited) helper.Kill(entireProcessTree: true); }
        catch (Exception) { }
        try { responses?.Dispose(); helper?.Dispose(); }
        catch (Exception) { }
        responses = null;
        helper = null;
    }

    public void Dispose() => Stop();
}
