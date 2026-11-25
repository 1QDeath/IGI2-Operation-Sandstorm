// Operation Sandstorm - Setup.exe (installer + uninstaller), C# 5 / .NET Framework 4.5 WinForms, built by work/release/release2.py
// with the Framework's own csc.exe. Reads the payload from the <name>[-N].dat zip parts next to it (setup.json inside part 1).
//   Setup.exe                        wizard: Welcome -> Location -> Options -> Progress -> Finish
//   Setup.exe /S [/D=<dir>] [/display=sharp|low|verylow|none] [/noshortcut]     silent install
//   Setup.exe /uninstall [/S]        (the copy in the game / backup folder: Add/Remove Programs runs this)
//   Setup.exe /shots=<dir>           save a picture of every wizard page (no install)
// mode "full":  extracts the whole game into a new folder.
// mode "addon": adds the mission to an existing GOG IGI 2 folder; every file it changes is first copied to <game>\_Sandstorm_backup.
// Registry: HKCU only (no admin).
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

static class Program
{
    // v1.6: the real path (Application.ExecutablePath turns "%41" in a folder name into "A")
    static string exePath;
    public static string ExePath
    {
        get
        {
            if (exePath == null) { try { exePath = Process.GetCurrentProcess().MainModule.FileName; } catch { exePath = typeof(Program).Assembly.Location; } }
            return exePath;
        }
    }

    // a message a player can act on, for errors that reach the top
    public static string Friendly(Exception e)
    {
        if (e is FileNotFoundException || e is FileLoadException || e is TypeLoadException)
            if ((e.Message ?? "").IndexOf("System.IO.Compression", StringComparison.OrdinalIgnoreCase) >= 0)
                return "This setup needs Microsoft .NET Framework 4.5 or newer (built into Windows 8/10/11; on Windows 7 install it from microsoft.com).";
        if (e is UnauthorizedAccessException)
            return e.Message + "\n\nWindows did not allow the change. If the game is in Program Files: right-click Setup.exe > Run as administrator, or move the game folder (for example to C:\\Games).";
        int hr = 0; try { hr = Marshal.GetHRForException(e) & 0xFFFF; } catch { }
        if (e is IOException && (hr == 112 || hr == 39))
            return "The disk is full. Free some space and run Setup again.";
        return e.Message;
    }

    [STAThread]
    static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        var a = new Args(args);
        try { Log.PathName = Path.Combine(Path.GetTempPath(), "Sandstorm_Setup.log"); Log.Write("---- " + Program.ExePath + " " + string.Join(" ", args)); } catch { }
        // v1.6: nothing reaches the raw .NET "unhandled exception" dialog
        bool quiet = a.Has("/S") || a.Get("/shots=") != null;
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (s, e) =>
        {
            Log.Write("UI ERROR " + e.Exception);
            if (!quiet) try { MessageBox.Show(Friendly(e.Exception) + (Log.PathName != null ? "\n\nDetails: " + Log.PathName : ""), "Operation Sandstorm", MessageBoxButtons.OK, MessageBoxIcon.Error); } catch { }
        };
        AppDomain.CurrentDomain.UnhandledException += (s, e) =>
        {
            Log.Write("FATAL " + e.ExceptionObject);
            if (quiet) { try { Console.Error.WriteLine(e.ExceptionObject); } catch { } Environment.Exit(1); }
            try { MessageBox.Show(Friendly(e.ExceptionObject as Exception ?? new Exception("" + e.ExceptionObject)) + (Log.PathName != null ? "\n\nDetails: " + Log.PathName : ""), "Operation Sandstorm", MessageBoxButtons.OK, MessageBoxIcon.Error); } catch { }
        };
        try
        {
            if (a.Has("/uninstall")) return Uninstaller.Run(a);
            var cfg = Payload.Load();
            if (a.Get("/shots=") != null)
            {
                var wd = new System.Threading.Timer(_ => Environment.Exit(3), null, 90000, Timeout.Infinite);   // never hang a test run
                Wizard.Shots(cfg, a.Get("/shots=")); return 0;
            }
            if (a.Has("/S")) return Installer.Silent(cfg, a);
            Application.Run(new Wizard(cfg));
            return 0;
        }
        catch (Exception e)
        {
            if (a.Has("/S") || a.Get("/shots=") != null)
            {
                Console.Error.WriteLine(e.ToString()); Log.Write("ERROR " + e);
                if (a.Get("/shots=") != null) try { Directory.CreateDirectory(a.Get("/shots=")); File.WriteAllText(Path.Combine(a.Get("/shots="), "error.txt"), e.ToString()); } catch { }
                return 1;
            }
            Log.Write("ERROR " + e);
            MessageBox.Show(Friendly(e), "Operation Sandstorm", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}

class Args
{
    List<string> v;
    public Args(string[] a) { v = a.ToList(); }
    public bool Has(string n) { return v.Any(x => x.Equals(n, StringComparison.OrdinalIgnoreCase)); }
    public string Get(string prefix)
    {
        foreach (var x in v) if (x.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) return x.Substring(prefix.Length).Trim('"');
        return null;
    }
}

static class Log
{
    public static string PathName;
    public static void Write(string s)
    {
        try { if (PathName != null) File.AppendAllText(PathName, DateTime.Now.ToString("HH:mm:ss ") + s + "\r\n"); } catch { }
    }
}

// ------------------------------------------------------------------------------------------------ payload + config
class Payload
{
    public Dictionary<string, object> J;
    public string Dir;
    public List<string> Parts = new List<string>();
    public string S(string k) { object o; return J.TryGetValue(k, out o) && o != null ? o.ToString() : ""; }
    public long L(string k) { object o; return J.TryGetValue(k, out o) && o != null ? Convert.ToInt64(o) : 0; }
    public List<string> List(string k)
    {
        object o; var r = new List<string>();
        if (J.TryGetValue(k, out o) && o is System.Collections.ArrayList) foreach (var x in (System.Collections.ArrayList)o) r.Add(x.ToString());
        return r;
    }
    public Dictionary<string, string> Map(string k)
    {
        object o; var r = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (J.TryGetValue(k, out o) && o is Dictionary<string, object>) foreach (var kv in (Dictionary<string, object>)o) r[kv.Key] = kv.Value == null ? null : kv.Value.ToString();
        return r;
    }
    public bool Full { get { return S("mode") == "full"; } }

    public static Payload Load()
    {
        var p = new Payload();
        p.Dir = Path.GetDirectoryName(Program.ExePath);
        // v1.6: the .dat whose setup.json names ITSELF as part 1 (an old "Sandstorm (1).dat" next to a new download never mixes builds)
        string first = null, any = null;
        foreach (var x in Directory.GetFiles(p.Dir, "*.dat").OrderBy(f => f, StringComparer.OrdinalIgnoreCase))
        {
            try
            {
                using (var z = ZipFile.OpenRead(x))
                {
                    var e = z.GetEntry("_setup/setup.json"); if (e == null) continue;
                    if (any == null) any = x;
                    using (var r = new StreamReader(e.Open(), Encoding.UTF8))
                    {
                        var j = new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Deserialize<Dictionary<string, object>>(r.ReadToEnd());
                        object parts; var l = j.TryGetValue("parts", out parts) ? parts as System.Collections.ArrayList : null;
                        if (l != null && l.Count > 0 && string.Equals("" + l[0], Path.GetFileName(x), StringComparison.OrdinalIgnoreCase)) { first = x; break; }
                    }
                }
            }
            catch { }
        }
        first = first ?? any;
        if (first == null)
        {
            var d = p.Dir ?? "";
            if (d.IndexOf("\\Temp1_", StringComparison.OrdinalIgnoreCase) >= 0 || d.IndexOf(".zip", StringComparison.OrdinalIgnoreCase) >= 0)
                throw new Exception("Setup was started from inside the zip. Extract the zip first (right-click > Extract All), then run Setup.exe from the extracted folder.");
            throw new Exception("The setup data file (Sandstorm*.dat) is missing next to Setup.exe. Keep Setup.exe and Sandstorm.dat together in one folder (extract the whole zip).");
        }
        using (var z = ZipFile.OpenRead(first))
        using (var r = new StreamReader(z.GetEntry("_setup/setup.json").Open(), Encoding.UTF8))
        {
            var js = new JavaScriptSerializer(); js.MaxJsonLength = int.MaxValue;
            p.J = js.Deserialize<Dictionary<string, object>>(r.ReadToEnd());
        }
        foreach (var n in p.List("parts"))
        {
            var f = Path.Combine(p.Dir, n);
            if (!File.Exists(f)) throw new Exception("Setup data file missing: " + n + " (keep every .dat file next to Setup.exe)");
            p.Parts.Add(f);
        }
        return p;
    }

    public static Image Art(string name)
    {
        var s = typeof(Program).Assembly.GetManifestResourceStream(name);
        return s == null ? null : Image.FromStream(s);
    }

    public static Image Avatar()
    {
        var s = typeof(Program).Assembly.GetManifestResourceStream("avatar.png");
        return s == null ? null : Image.FromStream(s);
    }
}

// ------------------------------------------------------------------------------------------------ helpers
static class U
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool CreateHardLink(string lpFileName, string lpExistingFileName, IntPtr sec);

    public static string Md5(string p) { using (var m = MD5.Create()) using (var f = File.OpenRead(p)) return Hex(m.ComputeHash(f)); }
    public static string Md5Of(byte[] b) { using (var m = MD5.Create()) return Hex(m.ComputeHash(b)); }
    public static string Sha1(string p) { using (var m = SHA1.Create()) using (var f = File.OpenRead(p)) return Hex(m.ComputeHash(f)); }
    static string Hex(byte[] b) { var s = new StringBuilder(); foreach (var x in b) s.Append(x.ToString("x2")); return s.ToString(); }
    public static void Link(string src, string dst)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(dst));
        if (!CreateHardLink(dst, src, IntPtr.Zero)) { File.Copy(src, dst, true); ClearRO(dst); }
    }
    // v1.6: read-only flags (a game copied from a CD / some repacks) never block a write or a delete
    public static void ClearRO(string p)
    {
        try { var a = File.GetAttributes(p); if ((a & FileAttributes.ReadOnly) != 0) File.SetAttributes(p, a & ~FileAttributes.ReadOnly); } catch { }
    }
    public static void DeleteFile(string p) { if (File.Exists(p)) { ClearRO(p); File.Delete(p); } }
    public static void DeleteDir(string d)
    {
        if (!Directory.Exists(d)) return;
        foreach (var f in Directory.GetFiles(d, "*", SearchOption.AllDirectories)) ClearRO(f);
        Directory.Delete(d, true);
    }
    // the whole new file is on disk before the old one goes (a full disk never leaves a game file cut short or missing)
    public static void WriteSafe(string p, byte[] data) { Swap(p, tmp => File.WriteAllBytes(tmp, data)); }
    public static void CopySafe(string src, string p) { Swap(p, tmp => File.Copy(src, tmp)); }
    // write <p>.sstmp, then swap it in (the old file goes only once the new one is complete; the temp never stays behind)
    static void Swap(string p, Action<string> make)
    {
        var tmp = p + ".sstmp"; bool removed = false;
        try
        {
            if (File.Exists(tmp)) DeleteFile(tmp);
            make(tmp); ClearRO(tmp);
            if (File.Exists(p))
            {
                ClearRO(p);
                try { File.Replace(tmp, p, null, true); return; }
                catch (Exception e) { Log.Write("replace " + p + ": " + e.Message + " - delete + move"); }
                File.Delete(p); removed = true;
            }
            for (int i = 0; ; i++)                                // an antivirus scan can hold the new file for a moment
            {
                try { File.Move(tmp, p); break; }
                catch (IOException) { if (i >= 9) throw; Thread.Sleep(300); }
                catch (UnauthorizedAccessException) { if (i >= 9) throw; Thread.Sleep(300); }
            }
        }
        // the temp goes only while the real file exists (if the swap died between delete and move, the complete new file stays as .sstmp)
        finally { try { if (File.Exists(tmp) && !(removed && !File.Exists(p))) { ClearRO(tmp); File.Delete(tmp); } } catch { } }
    }
    // a file whose swap died half-way: the complete .sstmp stands in for it
    public static string OrTemp(string p) { return !File.Exists(p) && File.Exists(p + ".sstmp") ? p + ".sstmp" : p; }
    // a free name in dir for file name n (name, name (2), ...)
    public static string FreeName(string dir, string n)
    {
        var p = Path.Combine(dir, n);
        for (int i = 2; File.Exists(p) || Directory.Exists(p); i++) p = Path.Combine(dir, Path.GetFileNameWithoutExtension(n) + " (" + i + ")" + Path.GetExtension(n));
        return p;
    }
    // null = we can write files in dir (creates and deletes a probe file)
    public static string CanWrite(string dir)
    {
        try
        {
            var p = Path.Combine(dir, "_sandstorm_write_test.tmp");
            File.WriteAllBytes(p, new byte[] { 1 }); File.Delete(p); return null;
        }
        catch (Exception e) { return e.Message; }
    }
    public static void Unblock(string p) { try { DeleteFileW(p + ":Zone.Identifier"); } catch { } }
    const string Layers = @"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers";
    // the Windows compatibility flags for an exe (null = none)
    public static string CompatFlag(string exe)
    {
        try { using (var k = Registry.CurrentUser.OpenSubKey(Layers)) return k == null ? null : k.GetValue(exe) as string; } catch { return null; }
    }
    public static void SetCompatFlag(string exe, string v)
    {
        try
        {
            using (var k = Registry.CurrentUser.CreateSubKey(Layers))
            {
                if (v == null) { if (k.GetValue(exe) != null) k.DeleteValue(exe, false); }
                else k.SetValue(exe, v);
            }
        }
        catch { }
    }
    // a game in Program Files run without admin writes its profile to VirtualStore: the game then reads THAT copy (null = none)
    public static string VirtualStoreProfile(string game)
    {
        try
        {
            var full = Path.GetFullPath(game); var root = Path.GetPathRoot(full);
            if (root.Length < 2 || root.StartsWith(@"\\")) return null;
            var p = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "VirtualStore", full.Substring(root.Length), "config.qvm");
            return File.Exists(p) ? p : null;
        }
        catch { return null; }
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool DeleteFileW(string name);
    // an igi2.exe running FROM this game folder (another copy of the game elsewhere does not block); unknown path = blocks
    public static bool GameRunning(string dir)
    {
        foreach (var p in Process.GetProcessesByName("igi2"))
        {
            try
            {
                var f = Path.GetFullPath(p.MainModule.FileName);
                if (dir == null || f.StartsWith(Path.GetFullPath(dir).TrimEnd('\\') + "\\",StringComparison.OrdinalIgnoreCase)) return true;
            }
            catch { return true; }
        }
        return false;
    }
    public static bool IsGame(string d)
    {
        return !string.IsNullOrEmpty(d) && File.Exists(Path.Combine(d, "igi2.exe")) && Directory.Exists(Path.Combine(d, "MISSIONS", "multiplayer"));
    }
    public static string FindGog(string id)
    {
        foreach (var root in new[] { @"SOFTWARE\WOW6432Node\GOG.com\Games\" + id, @"SOFTWARE\GOG.com\Games\" + id })
        {
            foreach (var hive in new[] { Registry.LocalMachine, Registry.CurrentUser })
            {
                try { using (var k = hive.OpenSubKey(root)) if (k != null) { var p = k.GetValue("path") as string; if (IsGame(p)) return p; } } catch { }
            }
        }
        foreach (var d in new[] { @"C:\GOG Games\IGI 2 Covert Strike", @"C:\GOG Games\IGI 2", @"C:\Program Files (x86)\GOG Galaxy\Games\IGI 2 Covert Strike",
                                  @"C:\Program Files (x86)\GOG Galaxy\Games\IGI 2", @"D:\GOG Games\IGI 2 Covert Strike", @"C:\Games\IGI 2" })
            if (IsGame(d)) return d;
        return "";
    }
    public static void Shortcut(string lnk, string target, string dir, string icon)
    {
        Type t = Type.GetTypeFromProgID("WScript.Shell");
        dynamic sh = Activator.CreateInstance(t);
        dynamic s = sh.CreateShortcut(lnk);
        s.TargetPath = target; s.WorkingDirectory = dir; s.IconLocation = icon + ",0"; s.Save();
    }
    public static string DesktopLnk(string product) { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), product + ".lnk"); }
    // null = fine (or nothing to run), else what went wrong (v1.6: reported to the player, a hung script is stopped before we touch its files)
    public static string RunDisplay(string game, string mode)
    {
        var cmd = Path.Combine(game, "IGI2_Display_Setup.cmd");
        if (mode == "none" || !File.Exists(cmd)) return null;
        try
        {
            var psi = new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, "cmd.exe"), "/c \"\"" + cmd + "\" /" + mode + " /nostart\"");
            psi.WorkingDirectory = game; psi.CreateNoWindow = true; psi.UseShellExecute = false; psi.WindowStyle = ProcessWindowStyle.Hidden;
            psi.RedirectStandardInput = true;                       // a "pause" in the script reads end-of-input instead of waiting
            using (var p = Process.Start(psi))
            {
                p.StandardInput.Close();
                if (!p.WaitForExit(120000)) { try { KillTree(p.Id); } catch { } Log.Write("display " + mode + " timeout"); return "it did not finish in 2 minutes"; }
                Log.Write("display " + mode + " exit " + p.ExitCode);
                return p.ExitCode == 0 ? null : "exit code " + p.ExitCode;
            }
        }
        catch (Exception e) { Log.Write("display " + mode + ": " + e); return e.Message; }
    }
    static void KillTree(int pid)
    {
        using (var k = Process.Start(new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, "taskkill.exe"), "/T /F /PID " + pid) { CreateNoWindow = true, UseShellExecute = false }))
            k.WaitForExit(10000);
    }
    // after the display script: Sharp keeps the owner's look (dgVoodoo [DirectX] Antialiasing 4x / Filtering 16); Low-end / Very low keep the script's
    // v1.3 (owner 11-24: plain GOG copy crashed at start in dxcore.dll; GOG + Patch, which has these two, works): on every base
    // [General] EnumerateRefreshRates = true and [GeneralExt] FullscreenAttributes = fake (borderless); everything else stays
    public static void SafeConf(string game)
    {
        var p = Path.Combine(game, "dgVoodoo.conf"); if (!File.Exists(p)) return;
        var enc = Encoding.GetEncoding(28591); var t = enc.GetString(File.ReadAllBytes(p));
        t = SetKey(t, "General", "EnumerateRefreshRates", "true");
        t = SetKey(t, "GeneralExt", "FullscreenAttributes", "fake");
        t = SetKey(t, "GeneralExt", "PresentationModel", "flip_discard");   // (11-24: legacy discard swapchain + OBS Game Capture = crash in dxcore; flip model fixes it, owner-tested)
        t = SetKey(t, "GeneralExt", "FPSLimit", "60");               // (owner 11-24: 60 fps cap by default on every option; change it in dgVoodoo.conf)
        WriteSafe(p, enc.GetBytes(t));
        Log.Write("dgVoodoo.conf: EnumerateRefreshRates = true, FullscreenAttributes = fake, PresentationModel = flip_discard, FPSLimit = 60");
    }

    // set key = value inside [section] (adds the line at the end of the section when it is missing)
    public static string SetKey(string t, string section, string key, string value)
    {
        var m = Regex.Match(t, @"(?ms)^\[" + Regex.Escape(section) + @"\][^\r\n]*\r?\n(.*?)(?=^\[|\z)");
        if (!m.Success) return t;
        var body = m.Groups[1].Value;
        var k = Regex.Match(body, @"(?m)^(" + Regex.Escape(key) + @"[ \t]*=)[ \t]*([^\r\n]*)");
        string nb;
        if (k.Success) nb = body.Substring(0, k.Index) + k.Groups[1].Value + " " + value + body.Substring(k.Index + k.Length);
        else { var nl = t.Contains("\r\n") ? "\r\n" : "\n"; var pad = new string(' ', Math.Max(1, 36 - key.Length)); nb = key + pad + "= " + value + nl + body; }
        return t.Substring(0, m.Groups[1].Index) + nb + t.Substring(m.Groups[1].Index + m.Groups[1].Length);
    }

    public static void SharpLook(Payload c, string game, string mode)
    {
        if (mode != "sharp") return;
        var p = Path.Combine(game, "dgVoodoo.conf"); if (!File.Exists(p)) return;
        var enc = Encoding.GetEncoding(28591); var t = enc.GetString(File.ReadAllBytes(p));
        var m = Regex.Match(t, @"(?ms)^\[DirectX\].*?(?=^\[)"); if (!m.Success) return;
        var sec = m.Value;
        foreach (var kv in c.Map("sharp_conf"))
            sec = Regex.Replace(sec, "(?m)^(" + Regex.Escape(kv.Key) + "[ \t]*=)[^\r\n]*", mm => mm.Groups[1].Value + " " + kv.Value);
        t = t.Substring(0, m.Index) + sec + t.Substring(m.Index + m.Length);
        WriteSafe(p, enc.GetBytes(t));
        Log.Write("sharp look applied");
    }
    public static void Register(Payload c, string game, string uninstallExe, long bytes)
    {
        using (var k = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + c.S("key")))
        {
            k.SetValue("DisplayName", c.S("product"));
            k.SetValue("DisplayVersion", c.S("version"));
            k.SetValue("Publisher", c.S("publisher"));
            k.SetValue("InstallLocation", game);
            k.SetValue("DisplayIcon", uninstallExe + ",0");
            k.SetValue("UninstallString", "\"" + uninstallExe + "\" /uninstall");
            k.SetValue("QuietUninstallString", "\"" + uninstallExe + "\" /uninstall /S");
            k.SetValue("Comments", c.S("made_by") + " - " + c.S("discord"));
            k.SetValue("NoModify", 1, RegistryValueKind.DWord);
            k.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            k.SetValue("EstimatedSize", (int)(bytes / 1024), RegistryValueKind.DWord);
        }
    }
    public static void Unregister(string key) { try { Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + key, false); } catch { } }
}

// ------------------------------------------------------------------------------------------------ ILFF (.res) + QVM (config) helpers
static class Ilff
{
    public class Chunk { public byte[] Tag; public byte[] Data; public uint Al; }
    public static List<Chunk> Read(byte[] d, out uint align, out byte[] form)
    {
        if (d == null || d.Length < 20 || Encoding.ASCII.GetString(d, 0, 4) != "ILFF") throw new Exception("not an ILFF file (" + (d == null ? 0 : d.Length) + " bytes)");
        align = BitConverter.ToUInt32(d, 8); form = new byte[4]; Array.Copy(d, 16, form, 0, 4);
        var r = new List<Chunk>(); int p = 20;
        while (p < d.Length)
        {
            // v1.5: a damaged / modded file (cut short, bad chunk sizes) is a clear error, never an index crash
            if (p + 16 > d.Length) throw new Exception("damaged file: chunk header cut short at byte " + p);
            var tg = new byte[4]; Array.Copy(d, p, tg, 0, 4);
            var c = new Chunk { Tag = tg, Al = BitConverter.ToUInt32(d, p + 8) };
            long sz = BitConverter.ToUInt32(d, p + 4); uint nx = BitConverter.ToUInt32(d, p + 12);
            if (p + 16 + sz > d.Length) throw new Exception("damaged file: chunk at byte " + p + " runs past the end");
            c.Data = new byte[sz]; Array.Copy(d, p + 16, c.Data, 0, (int)sz); r.Add(c);
            if (nx == 0) break;
            if (nx < 16 || p + (long)nx > int.MaxValue) throw new Exception("damaged file: bad chunk link at byte " + p);
            p += (int)nx;
        }
        return r;
    }
    public static byte[] Write(List<Chunk> ch, uint align, byte[] form, bool padLast)
    {
        var ms = new MemoryStream(); var w = new BinaryWriter(ms);
        w.Write(Encoding.ASCII.GetBytes("ILFF")); w.Write(0u); w.Write(align); w.Write(0u); w.Write(form);
        for (int i = 0; i < ch.Count; i++)
        {
            bool last = i == ch.Count - 1; int len = ch[i].Data.Length;
            int pad = (last && !padLast) ? 0 : (4 - len % 4) % 4;
            w.Write(ch[i].Tag); w.Write((uint)len); w.Write(ch[i].Al); w.Write(last ? 0u : (uint)(16 + len + pad)); w.Write(ch[i].Data);
            if (pad > 0) w.Write(new byte[pad]);
        }
        w.Flush(); var o = ms.ToArray(); Array.Copy(BitConverter.GetBytes((uint)o.Length), 0, o, 4, 4); return o;
    }
    public static string Name(Chunk c) { return Encoding.GetEncoding(28591).GetString(c.Data).TrimEnd('\0'); }
}

static class Qvm
{
    // config.qvm = compiled game script (LOOP v8). GOActiveMission(<difficulty>, <index>) holds the campaign position. Changing an index can
    // change the width of its push opcode, so every later CALL argument offset and every BRA that spans the change is shifted (linear sweep).
    static readonly Dictionary<byte, int> Len = new Dictionary<byte, int> {
        {0x00,1},{0x01,1},{0x02,1},{0x08,5},{0x09,2},{0x0a,3},{0x0b,5},{0x0d,5},{0x0e,5},{0x0f,2},{0x10,3},{0x11,5},{0x12,5},{0x13,2},{0x14,3},
        {0x15,1},{0x16,1},{0x18,1},{0x2c,1},{0x03,5} };
    static uint U32(byte[] b, int o) { return BitConverter.ToUInt32(b, o); }

    class Site { public int Diff; public int Val; public int At; public int W; }

    // v1.5: a usable config.qvm = LOOP header + code inside the file (a 0-byte / cut profile from a game crash is not)
    static bool HeaderOk(byte[] b)
    {
        try
        {
            if (b == null || b.Length < 64 || Encoding.ASCII.GetString(b, 0, 4) != "LOOP") return false;
            long code = U32(b, 44), size = U32(b, 48), symT = U32(b, 12), symD = U32(b, 16), symTS = U32(b, 20);
            if (code < 64 || code + size > b.Length || symT + symTS > b.Length || symD >= b.Length) return false;
            for (int k = 0; k < symTS / 4; k++) { long o = symD + U32(b, (int)symT + 4 * k); if (o < 0 || o >= b.Length || Array.IndexOf(b, (byte)0, (int)o) < 0) return false; }
            return true;
        }
        catch { return false; }
    }
    public static bool Readable(byte[] b)
    {
        if (!HeaderOk(b)) return false;
        try { int c0, s0; FindRaw(b, out c0, out s0); return true; } catch { return false; }
    }

    // v1.6: never throws - a file it cannot follow has no sites (the uninstaller called this on a cut-short profile and died)
    static List<Site> Find(byte[] b, out int code, out int size)
    {
        code = 0; size = 0;
        if (!HeaderOk(b)) return new List<Site>();
        try { return FindRaw(b, out code, out size); } catch { code = 0; size = 0; return new List<Site>(); }
    }

    // set progress without ever throwing: null when the file cannot be changed safely (unknown opcodes, did not settle, result unreadable)
    public static byte[] TrySetProgress(byte[] b, Func<int, int, int> fn)
    {
        try
        {
            if (!Readable(b)) return null;
            var o = SetProgress(b, fn);
            if (!Readable(o)) return null;
            int c, s; foreach (var x in Find(o, out c, out s)) if (fn(x.Diff, x.Val) != x.Val) return null;
            return o;
        }
        catch { return null; }
    }
    public static bool HasProgress(byte[] b) { int c, s; return Find(b, out c, out s).Count > 0; }

    static List<Site> FindRaw(byte[] b, out int code, out int size)
    {
        code = 0; size = 0;
        var r = new List<Site>();
        if (b == null || b.Length < 64 || Encoding.ASCII.GetString(b, 0, 4) != "LOOP") return r;
        code = (int)U32(b, 44); size = (int)U32(b, 48);
        int symT = (int)U32(b, 12), symD = (int)U32(b, 16), symTS = (int)U32(b, 20), idx = -1;
        for (int k = 0; k < symTS / 4; k++)
        {
            int o = symD + (int)U32(b, symT + 4 * k), e = Array.IndexOf(b, (byte)0, o);
            if (Encoding.ASCII.GetString(b, o, e - o) == "GOActiveMission") { idx = k; break; }
        }
        if (idx < 0) return r;
        for (int p = code; p < code + size - 20; p++)
        {
            int q = -1;
            if (b[p] == 0x13 && idx < 256 && b[p + 1] == idx) q = p + 2;
            else if (b[p] == 0x14 && BitConverter.ToUInt16(b, p + 1) == idx) q = p + 3;
            else if (b[p] == 0x12 && U32(b, p + 1) == idx) q = p + 5;
            if (q < 0 || b[q] != 0x07 || U32(b, q + 1) != 2) continue;
            int o0 = code + (int)U32(b, q + 5), o1 = code + (int)U32(b, q + 9), bra = q + 13;
            if (b[bra] != 0x03 || o0 != bra + 5) continue;
            int dw, iw; int? d = ReadInt(b, o0, out dw), v = ReadInt(b, o1, out iw);
            if (d == null || v == null || b[o0 + dw] != 0 || b[o1 + iw] != 0) continue;
            r.Add(new Site { Diff = d.Value, Val = v.Value, At = o1, W = iw });
        }
        return r;
    }
    static int? ReadInt(byte[] b, int a, out int w)
    {
        w = 0;
        switch (b[a])
        {
            case 0x15: w = 1; return 0;
            case 0x16: w = 1; return 1;
            case 0x09: w = 2; return (sbyte)b[a + 1];
            case 0x0a: w = 3; return BitConverter.ToInt16(b, a + 1);
            case 0x08: w = 5; return BitConverter.ToInt32(b, a + 1);
        }
        return null;
    }
    static byte[] Enc(int v)
    {
        if (v == 0) return new byte[] { 0x15 };
        if (v == 1) return new byte[] { 0x16 };
        if (v >= -128 && v <= 127) return new byte[] { 0x09, (byte)(sbyte)v };
        if (v >= -32768 && v <= 32767) { var r = new byte[3]; r[0] = 0x0a; Array.Copy(BitConverter.GetBytes((short)v), 0, r, 1, 2); return r; }
        var x = new byte[5]; x[0] = 0x08; Array.Copy(BitConverter.GetBytes(v), 0, x, 1, 4); return x;
    }
    // MISSIONS\igi2.qvm: DefineMissionListItem(<id>); ... -> ids in order (any version's file), null when unreadable
    public static List<int> ListIds(byte[] b)
    {
        try
        {
            if (Encoding.ASCII.GetString(b, 0, 4) != "LOOP") return null;
            int symT = (int)U32(b, 12), symD = (int)U32(b, 16), symTS = (int)U32(b, 20), code = (int)U32(b, 44), size = (int)U32(b, 48), idx = -1;
            for (int k = 0; k < symTS / 4; k++)
            {
                int o = symD + (int)U32(b, symT + 4 * k), e = Array.IndexOf(b, (byte)0, o);
                if (Encoding.ASCII.GetString(b, o, e - o) == "DefineMissionListItem") { idx = k; break; }
            }
            if (idx < 0) return null;
            var r = new List<int>();
            for (int p = code; p < code + size - 12; p++)
            {
                int q = -1;
                if (b[p] == 0x13 && idx < 256 && b[p + 1] == idx) q = p + 2;
                else if (b[p] == 0x14 && BitConverter.ToUInt16(b, p + 1) == idx) q = p + 3;
                else if (b[p] == 0x12 && U32(b, p + 1) == idx) q = p + 5;
                if (q < 0 || b[q] != 0x07 || U32(b, q + 1) != 1) continue;
                int a = code + (int)U32(b, q + 5); if (b[q + 9] != 0x03 || a != q + 14) continue;
                int w; int? v = ReadInt(b, a, out w);
                if (v != null && b[a + w] == 0) { r.Add(v.Value); p = a + w; }
            }
            return r;
        }
        catch { return null; }
    }

    // a mission list file (same layout as the game's own): header, one symbol, the calls
    public static byte[] ListEncode(List<int> ids, byte[] like)
    {
        var code = new MemoryStream();
        foreach (var id in ids)
        {
            code.WriteByte(0x13); code.WriteByte(0);
            code.WriteByte(0x07); code.Write(BitConverter.GetBytes(1u), 0, 4);
            long tab = code.Position; code.Write(new byte[4], 0, 4);
            code.WriteByte(0x03); long bra = code.Position; code.Write(new byte[4], 0, 4);
            long start = code.Position;
            var arg = Enc(id);
            long at = code.Position; code.Write(arg, 0, arg.Length); code.WriteByte(0x00);
            long end = code.Position;
            code.Position = tab; code.Write(BitConverter.GetBytes((uint)at), 0, 4);
            code.Position = bra; code.Write(BitConverter.GetBytes((uint)(end - start)), 0, 4);
            code.Position = end; code.WriteByte(0x18);
        }
        code.WriteByte(0x00);
        var symD = Encoding.ASCII.GetBytes("DefineMissionListItem\0"); var symT = BitConverter.GetBytes(0u);
        int baseOff = 0x40, oSymT = baseOff, oSymD = oSymT + symT.Length, oStrT = oSymD + symD.Length, oStrD = oStrT, oCode = oStrD;
        var ms = new MemoryStream(); var w = new BinaryWriter(ms);
        w.Write(Encoding.ASCII.GetBytes("LOOP")); w.Write(U32(like, 4)); w.Write(U32(like, 8));
        w.Write((uint)oSymT); w.Write((uint)oSymD); w.Write((uint)symT.Length); w.Write((uint)symD.Length);
        w.Write((uint)oStrT); w.Write((uint)oStrD); w.Write(0u); w.Write(0u); w.Write((uint)oCode); w.Write((uint)code.Length);
        while (ms.Position < baseOff) w.Write((byte)0);
        w.Write(symT); w.Write(symD); w.Write(code.ToArray()); w.Flush();
        return ms.ToArray();
    }

    public static Dictionary<int, int> Progress(byte[] b)
    {
        int c, s; var r = new Dictionary<int, int>();
        foreach (var x in Find(b, out c, out s)) r[x.Diff] = x.Val;
        return r;
    }
    // set every GOActiveMission index to fn(difficulty, current); returns the new file
    public static byte[] SetProgress(byte[] b, Func<int, int, int> fn)
    {
        for (int guard = 0; guard < 16; guard++)
        {
            int code, size; var sites = Find(b, out code, out size);
            var s = sites.FirstOrDefault(x => fn(x.Diff, x.Val) != x.Val);
            if (s == null) return b;
            b = Replace(b, code, size, s.At, s.W, Enc(fn(s.Diff, s.Val)));
        }
        throw new Exception("config.qvm: progress did not settle");
    }
    static byte[] Replace(byte[] b, int code, int size, int at, int oldW, byte[] neu)
    {
        int d = neu.Length - oldW;
        var o = new byte[b.Length + d];
        Array.Copy(b, 0, o, 0, at); Array.Copy(neu, 0, o, at, neu.Length); Array.Copy(b, at + oldW, o, at + neu.Length, b.Length - at - oldW);
        if (d == 0) return o;
        // sweep the OLD code: fix CALL argument offsets (code-relative, absolute) after the change and BRA lengths spanning it
        int relAt = at - code;
        for (int p = code; p < code + size; )
        {
            byte op = b[p]; int np = p < at ? p : p + d;      // position of this opcode in the new file
            if (op == 0x07)
            {
                int n = (int)U32(b, p + 1);
                for (int k = 0; k < n; k++)
                {
                    int off = (int)U32(b, p + 5 + 4 * k);
                    if (off > relAt) Array.Copy(BitConverter.GetBytes((uint)(off + d)), 0, o, np + 5 + 4 * k, 4);
                }
                p += 5 + 4 * n; continue;
            }
            if (op == 0x03)
            {
                int len = (int)U32(b, p + 1), end = p + 5 + len;
                if (p < at && at < end) Array.Copy(BitConverter.GetBytes((uint)(len + d)), 0, o, np + 1, 4);
                p += 5; continue;
            }
            int l;
            if (!Len.TryGetValue(op, out l)) throw new Exception("config.qvm: unknown opcode " + op + " at " + p);
            p += l;
        }
        Array.Copy(BitConverter.GetBytes((uint)(size + d)), 0, o, 48, 4);      // code size
        return o;
    }
}

// ------------------------------------------------------------------------------------------------ install
class Options
{
    public string Dir;
    public bool Shortcut = true;
    public string Display = "sharp";
    public bool ForceUnknownExe;                 // test switch /unknownexe: treat the exe as unknown (no patch)
}

static class Installer
{
    public const string BK = "_Sandstorm_backup";

    public static int Silent(Payload c, Args a)
    {
        var o = new Options();
        o.Dir = CleanDir(a.Get("/D=") ?? (c.Full ? c.S("default_dir") : U.FindGog(c.S("gog_id"))));
        if (a.Has("/noshortcut")) o.Shortcut = false;
        if (a.Has("/unknownexe")) { o.ForceUnknownExe = true; AllowUnknownExe = true; }
        if (a.Get("/display=") != null) o.Display = a.Get("/display=").ToLowerInvariant();
        string err = Check(c, o.Dir);
        if (err != null) { Console.Error.WriteLine(err); return 2; }
        Run(c, o, (f, s) => { });
        Console.WriteLine("installed to " + o.Dir);
        return 0;
    }

    // "C:\Games\IGI 2", "\"C:\Games\IGI 2\"" (Explorer's Copy as path) and "C:\Games\IGI 2\igi2.exe" all mean the game folder
    public static string CleanDir(string dir)
    {
        if (dir == null) return null;
        dir = dir.Trim().Trim('"').Trim();
        try { if (dir.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) && File.Exists(dir)) dir = Path.GetDirectoryName(dir); } catch { }
        return dir.TrimEnd('\\', '/').Length >= 3 ? dir.TrimEnd('\\', '/') : dir;
    }

    static long FreeSpace(string dir)
    {
        try { return new DriveInfo(Path.GetPathRoot(Path.GetFullPath(dir))).AvailableFreeSpace; } catch { return long.MaxValue; }   // network paths: not checked
    }

    // null = fine, else the reason (v1.6: never throws - an odd path is a message, not a crash)
    public static string Check(Payload c, string dir)
    {
        try { return CheckCore(c, dir); }
        catch (Exception e) { Log.Write("check: " + e); return "This folder cannot be used: " + Program.Friendly(e); }
    }

    static string CheckCore(Payload c, string dir)
    {
        if (string.IsNullOrWhiteSpace(dir)) return "Choose a folder.";
        try { dir = Path.GetFullPath(dir); } catch { return "This is not a valid folder path: " + dir; }
        if (U.GameRunning(dir)) return "IGI 2 is running from this folder - close the game first.";
        if (c.Full)
        {
            if (File.Exists(Path.Combine(dir, "igi2.exe"))) return "That folder already holds an IGI 2 - choose an empty or new folder.";
            var root = Path.GetPathRoot(Path.GetFullPath(dir));
            if (FreeSpace(dir) < c.L("size") + (200L << 20)) return "Not enough free disk space on " + root + " (needs " + (c.L("size") >> 20) + " MB).";
            return null;
        }
        if (!U.IsGame(dir)) return "This is not an IGI 2 folder (igi2.exe and MISSIONS\\multiplayer expected).";
        string loc = Path.Combine(dir, "MISSIONS", c.S("location"));
        if (!Directory.Exists(Path.Combine(loc, c.S("base")))) return "The multiplayer map Sandstorm (MISSIONS\\multiplayer\\sandstorm) is missing in this IGI 2 folder.";
        if (!Directory.Exists(Path.Combine(loc, c.S("own_common")))) return "MISSIONS\\multiplayer\\common is missing in this IGI 2 folder.";
        if (!File.Exists(Path.Combine(dir, "MISSIONS", "igi2.qvm"))) return "MISSIONS\\igi2.qvm (the mission list) is missing in this IGI 2 folder.";
        if (!File.Exists(Path.Combine(dir, "MENUSYSTEM", "loadingscreen.res"))) return "MENUSYSTEM\\loadingscreen.res is missing in this IGI 2 folder.";
        if (!Directory.Exists(Path.Combine(dir, "LANGUAGE"))) return "The LANGUAGE folder is missing in this IGI 2 folder.";
        var bk = Path.Combine(dir, BK);
        bool ours = File.Exists(U.OrTemp(Path.Combine(bk, "manifest.txt")));
        if (Directory.Exists(Path.Combine(loc, c.S("folder"))) && !ours)
            return Directory.Exists(Path.Combine(dir, "_ThirdWarhead_backup"))
                ? "This folder has the Third Warhead campaign installed, which already holds Sandstorm. Uninstall Third Warhead first (or use a clean IGI 2 folder)."
                : "This folder already holds a Sandstorm mission that this setup did not install - remove it first.";
        if (FreeSpace(dir) < (ours ? 100L << 20 : c.L("size") + (100L << 20))) return "Not enough free disk space (needs about " + ((c.L("size") >> 20) + 100) + " MB).";
        // v1.6: we must be able to write here BEFORE anything changes (Program Files without admin = access denied)
        foreach (var w in new[] { dir, Path.Combine(dir, "MISSIONS"), Path.Combine(dir, "MENUSYSTEM") })
        {
            var e = U.CanWrite(w);
            if (e != null) return "Setup cannot write into " + w + " (" + e + ").\n\nIf the game is in Program Files: close this, right-click Setup.exe > Run as administrator. Or move the game folder (for example to C:\\Games) and pick it here.";
        }
        foreach (var f in new[] { "igi2.exe", @"MISSIONS\igi2.qvm", "config.qvm" })
        {
            var p = Path.Combine(dir, f); if (!File.Exists(p)) continue;
            try { using (File.Open(p, FileMode.Open, FileAccess.ReadWrite, FileShare.ReadWrite)) { } }
            catch (UnauthorizedAccessException) { U.ClearRO(p); try { using (File.Open(p, FileMode.Open, FileAccess.ReadWrite, FileShare.ReadWrite)) { } } catch (Exception e) { return "Setup cannot change " + f + " (" + e.Message + "). Run Setup as administrator, or check that no program (antivirus, game) holds the file."; } }
            catch (IOException e) { return f + " is in use by another program (" + e.Message + "). Close the game / tools using it and try again."; }
        }
        // the mission needs the engine fixes: an exe that cannot take them is refused (rig 11-24: with the stock exe the screen turns grey
        // about a minute into the mission, every run)
        if (!AllowUnknownExe)
        {
            var ex = Path.Combine(dir, "igi2.exe");
            var mf = Path.Combine(bk, "files", "igi2.exe");
            var src = File.ReadAllBytes(ours && File.Exists(mf) ? mf : ex);
            string why;
            if (ApplyExePatch(src, (Dictionary<string, object>)c.J["exe_patch"], out why) == null)
            {
                var prot = Protection(src);
                return "Operation Sandstorm needs its engine fixes, and this igi2.exe cannot take them (" + why + (prot.Length > 0 ? "; copy protection: " + prot : "") + ").\n\n" +
                       "Supported: the GOG igi2.exe (plain or with the widescreen patch) and exes of the same build such as the community 1.3 exe.\n\n" +
                       "Send this to 1QDeath (Discord) to get your version supported:\nsha1 " + Sha(src) + ", " + src.Length + " bytes";
            }
        }
        return null;
    }

    public static bool AllowUnknownExe;          // /unknownexe (testing): install without the fixes instead of refusing

    public static bool Changed;                  // the game folder was changed (past the preflight)
    public static string Step = "";              // the step running now (named in an error message)
    public static void Run(Payload c, Options o, Action<double, string> prog0)
    {
        Step = "Starting"; Changed = false;
        Action<double, string> prog = (f, s) => { Step = s; Log.Write("step " + s); prog0(f, s); };
        Directory.CreateDirectory(o.Dir);
        if (c.Full) RunFull(c, o, prog); else RunAddon(c, o, prog);
    }

    // ---------------------------------------------------------------- full game
    static void RunFull(Payload c, Options o, Action<double, string> prog)
    {
        string dir = Path.GetFullPath(o.Dir);
        Changed = true;
        long total = c.L("bytes_total"), done = 0;
        var list = new List<string>();
        foreach (var part in c.Parts)
            using (var z = ZipFile.OpenRead(part))
                foreach (var e in z.Entries)
                {
                    if (e.FullName.StartsWith("_setup/") || e.FullName.EndsWith("/")) continue;
                    var dst = Path.Combine(dir, e.FullName.Replace('/', '\\'));
                    Directory.CreateDirectory(Path.GetDirectoryName(dst));
                    e.ExtractToFile(dst, true);
                    list.Add(e.FullName.Replace('/', '\\'));
                    done += e.Length;
                    prog(total > 0 ? 0.92 * done / total : 0, e.FullName);
                }
        Directory.CreateDirectory(Path.Combine(dir, "savegames"));
        prog(0.93, "Display settings");
        U.RunDisplay(dir, o.Display);
        U.SharpLook(c, dir, o.Display);
        U.SafeConf(dir);
        string un = Path.Combine(dir, "Uninstall.exe");
        File.Copy(Program.ExePath, un, true);
        list.Add("Uninstall.exe");
        File.WriteAllLines(Path.Combine(dir, "uninstall.dat"), new[] { "full|" + c.S("key") + "|" + c.S("product") }.Concat(list.Select(x => "f|" + x)));
        if (o.Shortcut)
            try { var l = U.DesktopLnk(c.S("product")); U.Shortcut(l, Path.Combine(dir, "igi2.exe"), dir, Path.Combine(dir, "igi2.exe")); File.AppendAllText(Path.Combine(dir, "uninstall.dat"), "lnk|" + l + "\r\n"); }
            catch (Exception e) { Log.Write("shortcut: " + e); }
        U.Register(c, dir, un, total);
        prog(1, "Done");
    }

    // ---------------------------------------------------------------- add-on for the GOG game
    class Ctx
    {
        public string G, Bk; public List<string[]> Rows = new List<string[]>();
        public Dictionary<string, string> Files = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        // v1.6: the manifest is replaced whole (a crash mid-write keeps the previous complete one)
        public void Save() { Directory.CreateDirectory(Bk); U.WriteSafe(Path.Combine(Bk, "manifest.txt"), Encoding.UTF8.GetBytes(string.Join("\r\n", Rows.Select(r => string.Join("|", r))) + "\r\n")); }
        public void Row(params string[] r) { Rows.Add(r); Save(); }
        public void Backup(string rel)
        {
            if (Files.ContainsKey(rel)) return;
            var p = Path.Combine(G, rel);
            if (File.Exists(p))
            {
                var d = Path.Combine(Bk, "files", rel); Directory.CreateDirectory(Path.GetDirectoryName(d)); U.CopySafe(p, d);
                Files[rel] = "backup";
            }
            else Files[rel] = "new";
            Row("file", Files[rel], rel);
        }
        public string Orig(string rel) { string h; return Files.TryGetValue(rel, out h) && h == "backup" ? Path.Combine(Bk, "files", rel) : Path.Combine(G, rel); }
        public void Put(byte[] data, string rel)
        {
            Backup(rel); var d = Path.Combine(G, rel); Directory.CreateDirectory(Path.GetDirectoryName(d));
            U.WriteSafe(d, data);
        }
        public static Ctx Load(string g)
        {
            var c = new Ctx { G = g, Bk = Path.Combine(g, BK) };
            var m = U.OrTemp(Path.Combine(c.Bk, "manifest.txt"));
            if (File.Exists(m))
                foreach (var l in File.ReadAllLines(m))
                {
                    if (l.Trim().Length == 0) continue;
                    var r = l.Split('|'); if (r.Length < 2) continue;            // a cut row never breaks a later install
                    if (r[0] == "file") { if (r.Length < 3) continue; c.Files[r[2]] = r[1]; }
                    c.Rows.Add(r);
                }
            return c;
        }
    }

    static byte[] Entry(ZipArchive z, string name)
    {
        var e = z.GetEntry(name); if (e == null) throw new Exception("setup data: " + name + " missing");
        using (var s = e.Open()) using (var ms = new MemoryStream()) { s.CopyTo(ms); return ms.ToArray(); }
    }

    public static List<string> Warnings = new List<string>();
    static readonly Encoding L1 = Encoding.GetEncoding(28591);

    static void RunAddon(Payload c, Options o, Action<double, string> prog)
    {
        string g = Path.GetFullPath(o.Dir);
        var x = Ctx.Load(g);
        Warnings.Clear();
        string loc = Path.Combine(g, "MISSIONS", c.S("location")), target = Path.Combine(loc, c.S("folder")), baseDir = Path.Combine(loc, c.S("base"));
        string relDir = Path.Combine("MISSIONS", c.S("location"), c.S("folder"));
        using (var z = ZipFile.OpenRead(c.Parts[0]))
        {
            // ---- preflight: everything taken from the player's game is found BEFORE anything is changed
            prog(0.01, "Checking your game files");
            var missing = new List<string>();
            foreach (var kv in c.Map("copies"))
                if (!File.Exists(Path.Combine(g, kv.Value))) missing.Add(kv.Value + " (copied into the mission as " + kv.Key + ")");
            var built = new Dictionary<string, byte[]>(); var other = new Dictionary<string, int>();
            int pi = 0; var recsAll = Recipes(c).Where(r => (string)r["kind"] == "mission").ToList();
            foreach (var r in recsAll)
            {
                var rel = (string)r["rel"]; int oth;
                try { built[rel] = BuildRes(r, Entry(z, (string)r["bin"]), gr => x.Orig(gr), out oth); other[rel] = oth; }
                catch (Exception e) { missing.Add(e.Message); }
                prog(0.01 + 0.3 * (++pi) / recsAll.Count, rel);
            }
            if (missing.Count > 0)
                throw new Exception("Your IGI 2 lacks game data this mission is built from (nothing was changed):\n- " + string.Join("\n- ", missing.Take(12)) +
                                    (missing.Count > 12 ? "\n- ... " + (missing.Count - 12) + " more" : ""));
            // v1.6 preflight: the mission list must be readable and writable back BEFORE anything changes (it used to fail after the texts were in)
            var lst = Path.Combine("MISSIONS", "igi2.qvm");
            var lraw = File.ReadAllBytes(x.Orig(lst));
            var ids = Qvm.ListIds(lraw);
            byte[] listNew = null;
            if (ids != null && ids.Count > 0)
            {
                int mid0 = (int)c.L("mission_id");
                ids.RemoveAll(v => v == mid0); ids.Add(mid0);
                try { listNew = Qvm.ListEncode(ids, lraw); var back = Qvm.ListIds(listNew); if (back == null || !back.SequenceEqual(ids)) listNew = null; } catch { listNew = null; }
            }
            if (listNew == null)
                throw new Exception("MISSIONS\\igi2.qvm (the game's mission list) could not be read - it is damaged or from a version this setup does not know (" + lraw.Length + " bytes). Nothing was changed.\n\n" +
                                    "Restore that one file from your game's installer (GOG: Verify / Repair), then run Setup again.");
            // ---- from here on the game changes: the uninstaller and the Apps entry exist FIRST, so a stop at any later step can always be undone
            Changed = true;
            Directory.CreateDirectory(x.Bk);
            string un = Path.Combine(x.Bk, "Uninstall.exe");
            if (!string.Equals(Path.GetFullPath(Program.ExePath), Path.GetFullPath(un), StringComparison.OrdinalIgnoreCase)) U.CopySafe(Program.ExePath, un);
            U.Unblock(un);
            if (!x.Rows.Any(r => r[0] == "meta")) x.Row("meta", c.S("key"), c.S("product"));
            try { U.Register(c, g, un, c.L("size")); } catch (Exception e) { Log.Write("register: " + e); Warnings.Add("Windows did not let Setup add Operation Sandstorm to Settings > Apps (" + e.Message + "). To uninstall, run " + un + "."); }
            if (!x.Rows.Any(r => r[0] == "dir" && r.Length > 1 && r[1] == relDir)) x.Row("dir", relDir);
            // old Sandstorm mid-mission saves break a new build: moved into the backup folder (v1.6: never over an older one with the same name)
            var sg = Path.Combine(g, "savegames");
            if (Directory.Exists(sg))
                foreach (var f in Directory.GetFiles(sg, "*.igi2save"))
                {
                    var parts = Path.GetFileNameWithoutExtension(f).Split('-');
                    if (parts.Length == 4 && parts[2] == c.S("mission_id")) { var d = Path.Combine(x.Bk, "old_saves"); Directory.CreateDirectory(d); File.Move(f, U.FreeName(d, Path.GetFileName(f))); }
                }
            prog(0.32, "Mission folder");
            U.DeleteDir(target);
            foreach (var f in Directory.GetFiles(baseDir, "*", SearchOption.AllDirectories))
            {
                var n = Path.GetFileName(f).ToLowerInvariant(); if (n == "mission.qvm" || n == "objects.qvm") continue;
                var d = Path.Combine(target, f.Substring(baseDir.Length + 1)); Directory.CreateDirectory(Path.GetDirectoryName(d)); File.Copy(f, d, true); U.ClearRO(d);
            }
            var com = Path.Combine(loc, c.S("own_common"));
            foreach (var f in Directory.GetFiles(com, "*", SearchOption.AllDirectories))
            {
                var rel = f.Substring(com.Length + 1); if (rel.Split('\\')[0].Equals("sounds", StringComparison.OrdinalIgnoreCase)) continue;
                U.Link(f, Path.Combine(target, "common", rel));
            }
            foreach (var f in c.List("deleted")) U.DeleteFile(Path.Combine(target, f.Replace('/', '\\')));
            var files = c.List("files"); int i = 0;
            foreach (var f in files)
            {
                var d = Path.Combine(target, f.Replace('/', '\\')); Directory.CreateDirectory(Path.GetDirectoryName(d));
                U.DeleteFile(d);
                z.GetEntry("mission/" + f).ExtractToFile(d);
                prog(0.35 + 0.35 * (++i) / files.Count, f);
            }
            foreach (var kv in c.Map("copies"))
            {
                var d = Path.Combine(target, kv.Key.Replace('/', '\\')); Directory.CreateDirectory(Path.GetDirectoryName(d));
                U.CopySafe(Path.Combine(g, kv.Value), d);
            }
            foreach (var kv in built)
            {
                var d = Path.Combine(target, kv.Key.Replace('/', '\\')); Directory.CreateDirectory(Path.GetDirectoryName(d));
                U.WriteSafe(d, kv.Value);
            }
            prog(0.75, "Texts and pictures");
            LangAdd(x, c);                                    // our texts into EVERY language folder's files (English text)
            SpriteAdd(x, c, z);                               // the mission picture into missionsprites.res
            PatchLoading(x, z, c.List("loading"));
            foreach (var lang in new[] { "english", "USA" }) x.Put(Entry(z, "shared/intro/congratulations.jpg"), Path.Combine("SCREENS", "intro", lang, "congratulations.jpg"));
            // mission list: the player's own list + Sandstorm at the end (any version's list; read + checked in the preflight)
            prog(0.8, "Mission list and profile");
            x.Put(listNew, lst);
            // profile: Sandstorm (last in the list) unlocked
            Profile(x, z, ids.Count - 1);
            prog(0.88, "Game exe and display");
            HandleExe(x, c, o);
            if (z.GetEntry("exe/version.dll") != null && !File.Exists(Path.Combine(g, "version.dll"))) x.Put(Entry(z, "exe/version.dll"), "version.dll");
            if (z.GetEntry("exe/IGI2HD.asi") != null) x.Put(Entry(z, "exe/IGI2HD.asi"), "IGI2HD.asi");
            foreach (var f in c.List("hd")) x.Put(Entry(z, "exe/hd/" + f), Path.Combine("hd", f));
            bool dgv = File.Exists(Path.Combine(g, "dgVoodoo.conf"));
            if (dgv)
            {
                EditConf(x, c.S("extra_res"));
                if (z.GetEntry("display/IGI2_Display_Setup.cmd") != null) x.Put(Entry(z, "display/IGI2_Display_Setup.cmd"), "IGI2_Display_Setup.cmd");
            }
            else Warnings.Add("No dgVoodoo.conf in this game folder: the display options and the extra resolutions were skipped (the game keeps its own video settings).");
            x.Put(Entry(z, "Sandstorm - README.txt"), "Sandstorm - README.txt");
            if (dgv)
            {
                foreach (var f in new[] { "dgVoodoo.conf.display-backup", "config.qvm.display-backup" }) x.Backup(f);   // the display script's own backups: removed again on uninstall
                // v1.6: the display script sets the Windows high-DPI flag for igi2.exe - remember what was there so uninstall puts it back
                string exeFull = Path.Combine(g, "igi2.exe");
                if (o.Display != "none" && !x.Rows.Any(r => r[0] == "compat")) x.Row("compat", exeFull, U.CompatFlag(exeFull) ?? "-");
                var derr = U.RunDisplay(g, o.Display);
                if (derr != null) Warnings.Add("The picture settings script did not finish (" + derr + "): the game keeps its current resolution. Run IGI2_Display_Setup.cmd in the game folder to set it later.");
                U.SharpLook(c, g, o.Display);
                U.SafeConf(g);
                // the display script also writes config.qvm (the game's own resolution): the profile we hand back is the one after it
                var cr = x.Rows.LastOrDefault(r => r[0] == "config" && r.Length >= 3); var cq = Path.Combine(g, "config.qvm");
                if (cr != null && File.Exists(cq)) x.Row("config", cr[1], cr[2] == "*" ? "*" : U.Md5(cq));
            }
            // a desktop shortcut is a convenience: Windows blocking it (Controlled Folder Access, no WScript) never fails the install
            if (o.Shortcut)
            {
                try { var l = U.DesktopLnk("IGI 2 - Operation Sandstorm"); U.Shortcut(l, Path.Combine(g, "igi2.exe"), g, Path.Combine(g, "igi2.exe")); x.Row("lnk", l); }
                catch (Exception e) { Log.Write("shortcut: " + e); Warnings.Add("Windows did not allow a desktop shortcut (" + e.Message + "). Start the game with igi2.exe in " + g + "."); }
            }
            var vs = U.VirtualStoreProfile(g);
            if (vs != null) Warnings.Add("Windows keeps a separate copy of the game profile for this folder (" + vs + "), so the game may not show Sandstorm unlocked. Moving the game out of Program Files fixes it.");
            // ---- verify OUR files: shipped files, and rebuilt packs whose every chunk matched (the rest of the folder is the player's own map)
            prog(0.96, "Checking files");
            bool patched = File.Exists(Path.Combine(g, c.S("patch_mark")));
            var tree = c.Map(patched ? "tree_patch" : "tree");
            int bad = 0, nck = 0;
            foreach (var f in files.Concat(built.Keys.Where(k => other[k] == 0 || patched)))
            {
                string want; if (!tree.TryGetValue(f, out want)) continue;
                nck++; var p = Path.Combine(target, f.Replace('/', '\\'));
                if (!File.Exists(p) || U.Md5(p) != want) bad++;
            }
            int rebuiltOther = other.Count(kv => kv.Value > 0);
            x.Row("base", patched ? "patched" : "other-or-gog");
            x.Row("verify", bad.ToString(), nck.ToString(), rebuiltOther.ToString());
            if (bad > 0) Warnings.Add(bad + " of " + nck + " mission files differ from the build - please report it to 1QDeath (Discord).");
            if (rebuiltOther > 0 && !patched) Warnings.Add(rebuiltOther + " texture / sound packs were rebuilt from your game's own versions of the stock assets (your copy differs from GOG): the mission uses your game's art there.");
            foreach (var w in Warnings) { Console.WriteLine("WARNING: " + w); x.Row("warn", w.Replace("|", "/").Replace("\n", " ")); }
            prog(1, Warnings.Count == 0 ? "Done" : "Done (with notes)");
        }
    }

    // ---- profile (config.qvm): Sandstorm unlocked, the player's settings kept. v1.6 rules (reviewed 11-25):
    //  * the CURRENT file decides: readable -> it is changed in place; never replaced while it works
    //  * a damaged ORIGINAL backup (a v1.4 install that crashed after backing up a 0-byte profile) is refreshed from the working current file
    //  * current damaged but a good backup -> start from the backup (a retry after a cut write); else a fresh default profile + a note
    //  * the config row's md5 is "*" once the player changed the profile between two installs, so uninstall keeps their file (progress reset)
    static void Profile(Ctx x, ZipArchive z, int last)
    {
        const string rel = "config.qvm";
        var cfg = Path.Combine(x.G, rel);
        Func<int, int, int> unlock = (k, v) => last;
        var prev = x.Rows.LastOrDefault(r => r[0] == "config" && r.Length >= 3);
        bool sticky = x.Rows.Any(r => r[0] == "config" && r.Length >= 3 && r[2] == "*") || (prev != null && File.Exists(cfg) && U.Md5(cfg) != prev[2]);
        byte[] cur = File.Exists(cfg) ? File.ReadAllBytes(cfg) : null;
        string h; bool hadBackup = x.Files.TryGetValue(rel, out h) && h == "backup";
        byte[] orig = hadBackup ? (File.Exists(x.Orig(rel)) ? File.ReadAllBytes(x.Orig(rel)) : null) : (x.Files.ContainsKey(rel) ? null : cur);
        bool curOk = Qvm.Readable(cur);
        if (hadBackup && curOk && !Qvm.Readable(orig))
        {
            // the working profile becomes the original - but never with Sandstorm's own position in it (an earlier install may have put it there):
            // capped at the last original mission, so uninstall never leaves the campaign pointing at a mission that is gone
            // (a previous install's row knows the original position: use it, a key it lacks = 0)
            var known = prev != null ? ParseProgress(prev[1]) : null;
            var fixedOrig = Qvm.TrySetProgress(cur, (k, v) => known != null ? (known.ContainsKey(k) ? known[k] : 0) : Math.Min(v, Math.Max(0, last - 1))) ?? cur;
            Log.Write("config.qvm: the backed-up original is damaged (" + (orig == null ? "missing" : orig.Length + " bytes") + ") - the working profile becomes the original");
            Directory.CreateDirectory(Path.GetDirectoryName(x.Orig(rel)));
            U.WriteSafe(x.Orig(rel), fixedOrig); orig = fixedOrig;
        }
        byte[] neu = curOk ? Qvm.TrySetProgress(cur, unlock) : null;
        if (neu == null && !curOk && Qvm.Readable(orig)) { neu = Qvm.TrySetProgress(orig, unlock); if (neu != null) Log.Write("config.qvm: current damaged, rebuilt from the backup"); }
        if (neu == null)
        {
            var def = Entry(z, "shared/config_default.qvm");
            neu = Qvm.TrySetProgress(def, unlock) ?? def;
            if (cur != null)
            {
                Log.Write("config.qvm unusable (" + cur.Length + " bytes, readable " + curOk + "): default profile used");
                Warnings.Add("Your game profile (config.qvm) " + (curOk ? "is in a format this setup cannot change" : "was damaged") + ", so a fresh one was put in its place (your old file is kept in " + BK + "\\files). Set your video / control options again in the game.");
            }
        }
        if (!Qvm.HasProgress(neu)) Warnings.Add("Setup could not unlock Sandstorm in your game profile: if it is not selectable, finish the earlier missions or delete config.qvm in the game folder (the game makes a new one).");
        var basep = Qvm.Readable(orig) ? Qvm.Progress(orig) : new Dictionary<int, int>();
        // a previous install already recorded the true original's progress (empty = the original had none): keep it
        if (prev != null) basep = ParseProgress(prev[1]);
        x.Backup(rel);
        // the row goes in BEFORE the write: a stop in between leaves a row whose md5 does not match, so uninstall resets the progress instead
        // of guessing (v1.6 review)
        x.Row("config", string.Join(",", basep.Select(kv => kv.Key + "=" + kv.Value)), sticky ? "*" : U.Md5Of(neu));
        U.WriteSafe(cfg, neu);
    }
    public static Dictionary<int, int> ParseProgress(string s)
    {
        var r = new Dictionary<int, int>();
        foreach (var kv in (s ?? "").Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries))
        {
            var p = kv.Split('='); int a, b;
            if (p.Length == 2 && int.TryParse(p[0], System.Globalization.NumberStyles.Integer, System.Globalization.CultureInfo.InvariantCulture, out a) &&
                int.TryParse(p[1], System.Globalization.NumberStyles.Integer, System.Globalization.CultureInfo.InvariantCulture, out b)) r[a] = b;
        }
        return r;
    }

    // ---- the exe, by CONTENT: any igi2.exe of the GOG build (GOG, widescreen patch, community 1.3 exes ...) where every byte our patch
    //      replaces still holds the GOG original gets the fixes (its own other bytes - strings, tags, resources - stay); otherwise the
    //      mission is installed without them and a clear note says why
    static void HandleExe(Ctx x, Payload c, Options o)
    {
        var exe = Path.Combine(x.G, "igi2.exe");
        var src = File.ReadAllBytes(x.Files.ContainsKey("igi2.exe") ? x.Orig("igi2.exe") : exe);
        string sha = Sha(src);
        string why = null;
        var outp = o.ForceUnknownExe ? null : ApplyExePatch(src, (Dictionary<string, object>)c.J["exe_patch"], out why);
        if (o.ForceUnknownExe) why = "test switch /unknownexe";
        if (outp != null)
        {
            var p = (Dictionary<string, object>)c.J["exe_patch"];
            if (c.List("exe_orig_sha1").Contains(sha) && Sha(outp) != (string)p["result_sha1"]) throw new Exception("patched igi2.exe check failed");
            x.Backup("igi2.exe");
            x.Put(outp, "igi2.exe");
            x.Row("exe", "patched", sha, src.Length.ToString(), Sha(outp));
            return;
        }
        var prot = Protection(src);
        x.Row("exe", "unknown", sha, src.Length.ToString(), prot, why.Replace("|", "/"));
        Warnings.Add("Your igi2.exe cannot take the mission's engine fixes (" + why + "; sha1 " + sha + ", " + src.Length + " bytes" + (prot.Length > 0 ? ", copy protection: " + prot : "") +
                     "). The mission is installed WITHOUT them, so you lose: the fix for the freeze after a mission, Alt+Enter handling, " +
                     "the taskbar / focus fix, the DPI and resolution handling, the weapon reload / animation speed fix and the credits page. " +
                     "Send this hash to 1QDeath (Discord) to get your version supported.");
    }

    static string Sha(byte[] b) { using (var s1 = SHA1.Create()) return BitConverter.ToString(s1.ComputeHash(b)).Replace("-", "").ToLower(); }
    static int I(Dictionary<string, object> p, string k) { return Convert.ToInt32(p[k]); }

    static uint PeChecksum(byte[] b, int csOff)
    {
        ulong s = 0; int n = b.Length / 2 * 2;
        for (int i = 0; i < n; i += 2)
        {
            if (i >= csOff && i < csOff + 4) continue;
            s += (ulong)(b[i] | (b[i + 1] << 8)); s = (s & 0xffff) + (s >> 16);
        }
        if ((b.Length & 1) != 0) { s += b[b.Length - 1]; s = (s & 0xffff) + (s >> 16); }
        s = (s & 0xffff) + (s >> 16);
        return (uint)((s + (ulong)b.Length) & 0xffffffff);
    }

    // twin of recipe.apply_exe_patch2 (the build checks the Python one on GOG, GOG + widescreen patch and the community 1.3 exe)
    static byte[] ApplyExePatch(byte[] src, Dictionary<string, object> p, out string why)
    {
        why = null;
        if (src.Length != I(p, "gog_len")) { why = "size " + src.Length + " differs from the GOG build (" + I(p, "gog_len") + ")"; return null; }
        int pe = BitConverter.ToInt32(src, 0x3c);
        if (pe != I(p, "pe") || BitConverter.ToUInt16(src, pe + 20) != I(p, "opt") || BitConverter.ToUInt16(src, pe + 6) != I(p, "ns_gog")) { why = "the PE header layout differs from the GOG build"; return null; }
        var rec = new HashSet<int>();
        foreach (var f in new[] { new[] { I(p, "f_ns"), 2 }, new[] { I(p, "f_char"), 2 }, new[] { I(p, "f_soi"), 4 }, new[] { I(p, "f_cs"), 4 } })
            for (int k = 0; k < f[1]; k++) rec.Add(f[0] + k);
        var slots = (System.Collections.ArrayList)p["slots"]; int s0 = Convert.ToInt32(slots[0]), s1 = Convert.ToInt32(slots[1]);
        var tail = (string)p["tail"];
        var b = new byte[src.Length + tail.Length / 2];
        Array.Copy(src, b, src.Length);
        foreach (System.Collections.ArrayList run in (System.Collections.ArrayList)p["runs"])
        {
            int off = Convert.ToInt32(run[0]); string nh = (string)run[1], oh = (string)run[2];
            for (int k = 0; k < nh.Length / 2; k++)
            {
                int o = off + k; byte nb = Convert.ToByte(nh.Substring(2 * k, 2), 16), ob = Convert.ToByte(oh.Substring(2 * k, 2), 16);
                if (!rec.Contains(o))
                {
                    if (o >= s0 && o < s1) { if (src[o] != ob && src[o] != 0) { why = string.Format("section table slot 0x{0:x} is not free", o); return null; } }
                    else if (src[o] != ob) { why = string.Format("byte 0x{0:x} is 0x{1:x2}, the patch expects 0x{2:x2}", o, src[o], ob); return null; }
                }
                b[o] = nb;
            }
        }
        for (int k = 0; k < tail.Length / 2; k++) b[src.Length + k] = Convert.ToByte(tail.Substring(2 * k, 2), 16);
        Array.Copy(BitConverter.GetBytes((ushort)I(p, "ns_new")), 0, b, I(p, "f_ns"), 2);
        Array.Copy(BitConverter.GetBytes((ushort)(BitConverter.ToUInt16(src, I(p, "f_char")) | I(p, "laa"))), 0, b, I(p, "f_char"), 2);
        uint salign = BitConverter.ToUInt32(b, I(p, "f_salign")); ulong top = 0; int sec0 = pe + 24 + I(p, "opt");
        for (int k = 0; k < I(p, "ns_new"); k++) { uint vs = BitConverter.ToUInt32(b, sec0 + 40 * k + 8), va = BitConverter.ToUInt32(b, sec0 + 40 * k + 12); top = Math.Max(top, (ulong)va + vs); }
        Array.Copy(BitConverter.GetBytes((uint)((top + salign - 1) / salign * salign)), 0, b, I(p, "f_soi"), 4);
        uint cs = BitConverter.ToUInt32(src, I(p, "f_cs"));
        bool knownCs = false; foreach (var q in (System.Collections.ArrayList)p["known_cs"]) if (Convert.ToUInt32(q) == cs) knownCs = true;
        Array.Copy(BitConverter.GetBytes(knownCs ? Convert.ToUInt32(p["result_cs"]) : PeChecksum(b, I(p, "f_cs"))), 0, b, I(p, "f_cs"), 4);
        return b;
    }

    static string Protection(byte[] b)
    {
        try
        {
            int pe = BitConverter.ToInt32(b, 0x3c); int ns = BitConverter.ToUInt16(b, pe + 6); int opt = BitConverter.ToUInt16(b, pe + 20);
            var found = new List<string>();
            for (int k = 0; k < ns; k++)
            {
                var name = Encoding.ASCII.GetString(b, pe + 24 + opt + 40 * k, 8).TrimEnd('\0').ToLowerInvariant();
                if (name.StartsWith("stxt") || name == ".txt2" || name == ".txt") found.Add("SafeDisc (" + name + ")");
                if (name.Contains("securom") || name == ".dsstext") found.Add("SecuROM (" + name + ")");
            }
            return string.Join(", ", found.Distinct());
        }
        catch { return ""; }
    }

    // ---- structural edits that work on any version's files
    static bool PadOf(byte[] raw, List<Ilff.Chunk> ch, uint al, byte[] form) { return Ilff.Write(ch, al, form, true).Length == raw.Length; }

    static void AddNamed(List<Ilff.Chunk> ch, IEnumerable<KeyValuePair<string, byte[]>> entries, string tag, uint al)
    {
        var names = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        int pathIdx = -1;
        for (int k = 0; k < ch.Count; k++)
        {
            var t = Encoding.ASCII.GetString(ch[k].Tag);
            if (t == "NAME") names[Ilff.Name(ch[k])] = k;
            if (t == "PATH" && pathIdx < 0) pathIdx = k;
        }
        var add = new List<Ilff.Chunk>(); var newNames = new List<string>();
        foreach (var e in entries)
        {
            int k;
            if (names.TryGetValue(e.Key, out k) && k + 1 < ch.Count) { ch[k + 1].Data = e.Value; continue; }
            add.Add(new Ilff.Chunk { Tag = Encoding.ASCII.GetBytes("NAME"), Data = L1.GetBytes(e.Key + "\0"), Al = 4 });
            add.Add(new Ilff.Chunk { Tag = Encoding.ASCII.GetBytes(tag), Data = e.Value, Al = al });
            newNames.Add(e.Key);
        }
        if (pathIdx >= 0)
        {
            var lst = L1.GetString(ch[pathIdx].Data).TrimEnd('\0');
            foreach (var nm in newNames) lst += ";" + nm;
            ch[pathIdx].Data = L1.GetBytes(lst + "\0");
            // before the PATH entry's own NAME when it has one (never between another NAME and its data)
            int at = pathIdx > 0 && Encoding.ASCII.GetString(ch[pathIdx - 1].Tag) == "NAME" ? pathIdx - 1 : pathIdx;
            ch.InsertRange(at, add);
        }
        else ch.AddRange(add);
    }

    static void LangAdd(Ctx x, Payload c)
    {
        object o; if (!c.J.TryGetValue("lang", out o)) return;
        var lang = (Dictionary<string, object>)o;
        foreach (var dir in Directory.GetDirectories(Path.Combine(x.G, "LANGUAGE")))
        {
            var ln = Path.GetFileName(dir);
            foreach (var kv in lang)
            {
                var rel = Path.Combine("LANGUAGE", ln, kv.Key + ".res");
                if (!File.Exists(Path.Combine(x.G, rel))) continue;
                byte[] raw = File.ReadAllBytes(x.Files.ContainsKey(rel) ? x.Orig(rel) : Path.Combine(x.G, rel));
                List<Ilff.Chunk> ch; uint al; byte[] form;
                try { ch = Ilff.Read(raw, out al, out form); }
                catch (Exception e) { Warnings.Add("Language file " + rel + " could not be read (" + e.Message + "): the mission texts are missing in that language."); continue; }
                bool pad = PadOf(raw, ch, al, form);
                // the name prefix this file uses (LOCAL:<language>/...), taken from its own entries
                string prefix = "LOCAL:" + ln + "/";
                foreach (var q in ch) if (Encoding.ASCII.GetString(q.Tag) == "NAME") { var nm = Ilff.Name(q); int sl = nm.IndexOf('/'); if (nm.StartsWith("LOCAL:") && sl > 0) { prefix = nm.Substring(0, sl + 1); break; } }
                var entries = ((Dictionary<string, object>)kv.Value).Select(q => new KeyValuePair<string, byte[]>(prefix + q.Key, L1.GetBytes((string)q.Value + "\0"))).ToList();
                x.Backup(rel);
                AddNamed(ch, entries, "CSTR", 4);
                x.Put(Ilff.Write(ch, al, form, pad), rel);
            }
        }
    }

    static void SpriteAdd(Ctx x, Payload c, ZipArchive z)
    {
        var rel = Path.Combine("MENUSYSTEM", "missionsprites.res");
        if (!File.Exists(Path.Combine(x.G, rel))) { Warnings.Add("MENUSYSTEM\\missionsprites.res not found: the mission picture in the menu is missing."); return; }
        var raw = File.ReadAllBytes(x.Files.ContainsKey(rel) ? x.Orig(rel) : Path.Combine(x.G, rel));
        uint al; byte[] form; List<Ilff.Chunk> ch;
        try { ch = Ilff.Read(raw, out al, out form); }
        catch (Exception e) { Log.Write(rel + ": " + e); Warnings.Add(rel + " could not be read (" + e.Message + "): the mission picture in the menu is missing."); return; }
        bool pad = PadOf(raw, ch, al, form);
        var entries = c.Map("sprites").Select(kv => new KeyValuePair<string, byte[]>(kv.Key, Entry(z, kv.Value))).ToList();
        x.Backup(rel);
        AddNamed(ch, entries, "BODY", 4);
        x.Put(Ilff.Write(ch, al, form, pad), rel);
    }

    static List<Dictionary<string, object>> Recipes(Payload c)
    {
        var r = new List<Dictionary<string, object>>(); object o;
        if (c.J.TryGetValue("recipes", out o) && o is System.Collections.ArrayList) foreach (var q in (System.Collections.ArrayList)o) r.Add((Dictionary<string, object>)q);
        return r;
    }

    // a recipe: every chunk is either a reference (game file "g" + chunk name "n", GOG md5 "m") or ours (offset "o" / length "l" in the blob)
    static byte[] BuildRes(Dictionary<string, object> r, byte[] blob, Func<string, string> rootOf, out int other)
    {
        var rec = (Dictionary<string, object>)r["rec"];
        var cache = new Dictionary<string, Dictionary<string, byte[]>>(StringComparer.OrdinalIgnoreCase);
        Func<string, Dictionary<string, byte[]>> load = rel =>
        {
            Dictionary<string, byte[]> byName;
            if (cache.TryGetValue(rel, out byName)) return byName;
            byName = null;
            var path = rootOf(rel);
            if (File.Exists(path))
            {
                try
                {
                    uint a0; byte[] f0; var src = Ilff.Read(File.ReadAllBytes(path), out a0, out f0);
                    byName = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase);
                    for (int i = 0; i + 1 < src.Count; i++)
                        if (Encoding.ASCII.GetString(src[i].Tag) == "NAME") byName[Ilff.Name(src[i])] = src[i + 1].Data;
                }
                catch { byName = null; }
            }
            cache[rel] = byName; return byName;
        };
        var ch = new List<Ilff.Chunk>(); other = 0;
        foreach (Dictionary<string, object> c in (System.Collections.ArrayList)rec["chunks"])
        {
            byte[] d = null;
            if (c.ContainsKey("g"))
            {
                // candidates: the source the build used, then every other place in the GOG game with the same bytes
                var cands = new List<string[]> { new[] { (string)c["g"], (string)c["n"] } };
                object alt; if (c.TryGetValue("alt", out alt) && alt is System.Collections.ArrayList)
                    foreach (System.Collections.ArrayList q in (System.Collections.ArrayList)alt) cands.Add(new[] { (string)q[0], (string)q[1] });
                var want = (string)c["m"];
                foreach (var cd in cands)                         // pass 1: the same bytes anywhere
                {
                    var bn = load(cd[0]); byte[] v;
                    if (bn != null && bn.TryGetValue(cd[1], out v) && Hex(v) == want) { d = v; break; }
                }
                if (d == null)
                    foreach (var cd in cands)                     // pass 2: the same asset name (your version's art)
                    {
                        var bn = load(cd[0]); byte[] v;
                        if (bn != null && bn.TryGetValue(cd[1], out v)) { d = v; other++; break; }
                    }
                if (d == null)
                    throw new Exception("game file " + c["g"] + " has no chunk " + c["n"] + (cands.Count > 1 ? " (nor any of " + (cands.Count - 1) + " other places)" : "") + " - needed for " + r["rel"]);
            }
            else
            {
                int o = Convert.ToInt32(c["o"]), l = Convert.ToInt32(c["l"]);
                d = new byte[l]; Array.Copy(blob, o, d, 0, l);
            }
            ch.Add(new Ilff.Chunk { Tag = L1.GetBytes((string)c["t"]), Data = d, Al = Convert.ToUInt32(c["a"]) });
        }
        if (other > 0) Log.Write(r["rel"] + ": " + other + " chunks from a different game version");
        return Ilff.Write(ch, Convert.ToUInt32(rec["align"]), L1.GetBytes((string)rec["form"]), (bool)rec["pad_last"]);
    }

    static string Hex(byte[] d) { using (var m = MD5.Create()) return BitConverter.ToString(m.ComputeHash(d)).Replace("-", "").ToLower(); }

    static void PatchLoading(Ctx x, ZipArchive z, List<string> pics)
    {
        string rel = Path.Combine("MENUSYSTEM", "loadingscreen.res");
        x.Backup(rel);
        var raw = File.ReadAllBytes(x.Orig(rel)); uint al; byte[] form; List<Ilff.Chunk> ch;
        try { ch = Ilff.Read(raw, out al, out form); }
        catch (Exception e) { Log.Write(rel + ": " + e); Warnings.Add(rel + " could not be read (" + e.Message + "): the mission's loading pictures are missing."); return; }
        bool pad = Ilff.Write(ch, al, form, true).Length == raw.Length;
        // v1.6: a NAME is only usable with a data chunk after it (a file cut at a chunk boundary ends on a NAME); names compare case-insensitively
        var names = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        for (int i = 0; i + 1 < ch.Count; i++) if (Encoding.ASCII.GetString(ch[i].Tag) == "NAME") names[Ilff.Name(ch[i])] = i;
        uint bodyAl = names.ContainsKey("LOCAL:menusystem/loading.jpg") ? ch[names["LOCAL:menusystem/loading.jpg"] + 1].Al : 4;
        foreach (var f in pics)
        {
            var nm = "LOCAL:menusystem/" + f; var data = Entry(z, "shared/loading/" + f);
            if (names.ContainsKey(nm)) ch[names[nm] + 1].Data = data;
            else
            {
                ch.Add(new Ilff.Chunk { Tag = Encoding.ASCII.GetBytes("NAME"), Data = Encoding.GetEncoding(28591).GetBytes(nm + "\0"), Al = 4 });
                ch.Add(new Ilff.Chunk { Tag = Encoding.ASCII.GetBytes("BODY"), Data = data, Al = bodyAl });
            }
        }
        x.Put(Ilff.Write(ch, al, form, pad), rel);
    }

    static void EditConf(Ctx x, string extra)
    {
        string rel = "dgVoodoo.conf"; if (!File.Exists(Path.Combine(x.G, rel))) return; x.Backup(rel);
        var enc = Encoding.GetEncoding(28591); var p = Path.Combine(x.G, rel);
        var t = enc.GetString(File.ReadAllBytes(p));
        var m = Regex.Match(t, @"(?m)^(ExtraEnumeratedResolutions[ \t]*=)([^\r\n]*)");
        if (!m.Success) return;
        var have = m.Groups[2].Value.Split(',').Select(s => s.Trim()).Where(s => s.Length > 0).ToList();
        foreach (var r in extra.Split(',').Select(s => s.Trim()).Where(s => s.Length > 0)) if (!have.Contains(r, StringComparer.OrdinalIgnoreCase)) have.Add(r);
        if (have.Count > 16) { Log.Write("dgVoodoo.conf: resolution list capped at 16 (dropped " + string.Join(", ", have.Skip(16)) + ")"); have = have.Take(16).ToList(); }   // dgVoodoo: "max 16"
        t = t.Substring(0, m.Groups[2].Index) + " " + string.Join(", ", have) + t.Substring(m.Groups[2].Index + m.Groups[2].Length);
        U.WriteSafe(p, enc.GetBytes(t));
    }
}

// ------------------------------------------------------------------------------------------------ uninstall
static class Uninstaller
{
    // v1.6 (reviewed 11-25): every manifest row is undone on its own (one failure never stops the rest), the profile the player built is kept,
    // old saves are merged (never deleted), and the backup folder is only removed when it IS our backup folder and everything went back
    public static int Run(Args a)
    {
        bool silent = a.Has("/S");
        string here = Path.GetDirectoryName(Program.ExePath);
        bool full = File.Exists(Path.Combine(here, "uninstall.dat"));
        bool addon = File.Exists(U.OrTemp(Path.Combine(here, "manifest.txt"))) && string.Equals(Path.GetFileName(here.TrimEnd('\\')), Installer.BK, StringComparison.OrdinalIgnoreCase);
        if (!full && !addon) { Msg(silent, "Nothing to uninstall here."); return 1; }
        if (U.GameRunning(addon ? Path.GetDirectoryName(here) : here)) { Msg(silent, "IGI 2 is running - close the game first."); return 2; }
        string product = "Operation Sandstorm";
        if (!silent && MessageBox.Show("Remove " + product + "?", product, MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return 0;
        var errors = new List<string>();
        if (full)
        {
            var lines = File.ReadAllLines(Path.Combine(here, "uninstall.dat"));
            var head = lines[0].Split('|');
            foreach (var l in lines.Skip(1))
            {
                var r = l.Split(new[] { '|' }, 2); if (r.Length < 2) continue;
                try
                {
                    if (r[0] == "f" && r[1] != "Uninstall.exe") U.DeleteFile(Path.Combine(here, r[1]));
                    else if (r[0] == "lnk" && File.Exists(r[1])) File.Delete(r[1]);
                }
                catch { }
            }
            File.Delete(Path.Combine(here, "uninstall.dat"));
            // what the display script and the game wrote next to the files we installed (no player saves: savegames stays)
            foreach (var f in new[] { "dgVoodoo.conf.display-backup", "config.qvm.display-backup", "MultiMonitor.log", "Multiplayer.log", "igi2.RPT",
                                      "warninglog.txt", "flymode.log", "flymode_maxdamage.txt", @"hd\hdmod.log" })
                try { U.DeleteFile(Path.Combine(here, f)); } catch { }
            foreach (var d in Directory.GetDirectories(here, "*", SearchOption.AllDirectories).OrderByDescending(s => s.Length))
                try { if (!Directory.EnumerateFileSystemEntries(d).Any()) Directory.Delete(d); } catch { }
            if (head.Length > 1) U.Unregister(head[1]);
        }
        else
        {
            string g = Path.GetDirectoryName(here);
            var rows = File.ReadAllLines(U.OrTemp(Path.Combine(here, "manifest.txt"))).Where(l => l.Trim().Length > 0).Select(l => l.Split('|')).Where(r => r.Length >= 2).ToList();
            string key = "IGI2_OperationSandstorm"; string cfgRow = null, cfgMd5 = null;
            foreach (var r in rows)
            {
                if (r[0] == "meta" && r.Length >= 3) { key = r[1]; product = r[2]; }
                if (r[0] == "config" && r.Length >= 3) { cfgRow = r[1]; cfgMd5 = r[2]; }
            }
            Action<string, Action> step = (what, act) => { try { act(); } catch (Exception e) { Log.Write("uninstall " + what + ": " + e); errors.Add(what + ": " + e.Message); } };
            foreach (var r in rows.Where(r => r[0] == "dir"))
            {
                var rel = r[1];
                // only a folder inside MISSIONS (the mission folder we made) - never anything else
                if (!rel.StartsWith("MISSIONS\\", StringComparison.OrdinalIgnoreCase) || rel.Contains("..")) continue;
                step(rel, () => U.DeleteDir(Path.Combine(g, rel)));
            }
            foreach (var r in rows.Where(r => r[0] == "file" && r.Length >= 3))
            {
                var rel = r[2]; var p = Path.Combine(g, rel); var bp = Path.Combine(here, "files", rel);
                if (rel.Contains("..")) continue;
                if (rel.Equals("config.qvm", StringComparison.OrdinalIgnoreCase)) { step(rel, () => RestoreProfile(p, bp, r[1] == "backup", cfgRow, cfgMd5)); continue; }
                step(rel, () =>
                {
                    if (r[1] == "backup")
                    {
                        if (!File.Exists(bp)) throw new Exception("the backup copy is missing (" + bp + ")");
                        U.CopySafe(bp, p);
                    }
                    else U.DeleteFile(p);
                });
            }
            foreach (var r in rows.Where(r => r[0] == "compat" && r.Length >= 3)) step("compatibility flag", () => U.SetCompatFlag(r[1], r[2] == "-" ? null : r[2]));
            foreach (var lang in new[] { "english", "USA" })
            {
                var d = Path.Combine(g, "SCREENS", "intro", lang);
                try { if (Directory.Exists(d) && !Directory.EnumerateFileSystemEntries(d).Any()) Directory.Delete(d); } catch { }
            }
            if (rows.Any(r => r[0] == "file" && r.Length >= 3 && r[1] == "new" && r[2].Equals("IGI2HD.asi", StringComparison.OrdinalIgnoreCase)))
            {
                var hd = Path.Combine(g, "hd");                 // the log our HD add-on wrote, then the folder if it is empty
                try { U.DeleteFile(Path.Combine(hd, "hdmod.log")); if (Directory.Exists(hd) && !Directory.EnumerateFileSystemEntries(hd).Any()) Directory.Delete(hd); } catch { }
            }
            foreach (var r in rows.Where(r => r[0] == "lnk")) try { if (File.Exists(r[1])) File.Delete(r[1]); } catch { }
            // old Sandstorm saves: merged into <game>\savegames_sandstorm_old (a name already there gets " (2)")
            var old = Path.Combine(here, "old_saves");
            if (Directory.Exists(old))
                step("old saves", () =>
                {
                    var keep = Path.Combine(g, "savegames_sandstorm_old"); Directory.CreateDirectory(keep);
                    foreach (var f in Directory.GetFiles(old)) File.Move(f, U.FreeName(keep, Path.GetFileName(f)));
                    Directory.Delete(old, false);
                });
            if (errors.Count == 0) U.Unregister(key);
        }
        if (errors.Count > 0)
        {
            // keep the uninstaller, the backups and the Apps entry: the player can run it again after fixing the cause
            Msg(silent, "Some files could not be put back (close the game and any program using its files, then uninstall again):\n- " + string.Join("\n- ", errors.Take(10)) +
                        (Log.PathName != null ? "\n\nDetails: " + Log.PathName : ""));
            return 3;
        }
        Msg(silent, product + " was removed.");
        // delete this exe (and the backup folder) after it exits: retried until the exe is free (the message above has already been closed)
        string self = Program.ExePath;
        string sys = Environment.SystemDirectory;
        string script = "/c for /l %i in (1,1,20) do (ping -n 2 127.0.0.1 >nul & del /f /q \"" + self + "\" 2>nul & if not exist \"" + self + "\" (" +
                        (addon ? "rmdir /s /q \"" + here + "\"" : "rmdir \"" + here + "\"") + " & exit))";
        try { Process.Start(new ProcessStartInfo(Path.Combine(sys, "cmd.exe"), script) { CreateNoWindow = true, UseShellExecute = false, WindowStyle = ProcessWindowStyle.Hidden, WorkingDirectory = sys }); } catch { }
        return 0;
    }

    // the profile: back to the original only when the player did not touch it since the install (md5 matches); otherwise their file stays with the
    // campaign position put back. A damaged original never replaces a working profile.
    static void RestoreProfile(string p, string bp, bool hadBackup, string cfgRow, string cfgMd5)
    {
        byte[] cur = File.Exists(p) ? File.ReadAllBytes(p) : null;
        bool curOk = Qvm.Readable(cur);
        byte[] bk = hadBackup && File.Exists(bp) ? File.ReadAllBytes(bp) : null;
        bool bkOk = Qvm.Readable(bk);
        bool untouched = cur != null && cfgMd5 != null && cfgMd5 != "*" && U.Md5(p) == cfgMd5;
        // no profile row at all (an install that stopped before the profile step): a working original simply goes back
        if (cfgMd5 == null && hadBackup && bkOk) { U.CopySafe(bp, p); return; }
        var basep = Installer.ParseProgress(cfgRow);
        Func<int, int, int> back = (k, v) => basep.ContainsKey(k) ? basep[k] : 0;
        if (untouched && (!hadBackup || bkOk || !curOk))
        {
            if (hadBackup) { if (bk == null) throw new Exception("the backup copy is missing"); U.CopySafe(bp, p); } else U.DeleteFile(p);
            return;
        }
        if (curOk)
        {
            var o = Qvm.TrySetProgress(cur, back);
            if (o != null) { U.WriteSafe(p, o); return; }
            if (bkOk) { U.CopySafe(bp, p); return; }
            return;                                           // keep the working profile as it is
        }
        // the current profile is damaged or gone: the original if there was one
        if (hadBackup && bk != null) U.CopySafe(bp, p);
        else if (!hadBackup) U.DeleteFile(p);
    }
    static void Msg(bool silent, string s) { if (silent) Console.WriteLine(s); else MessageBox.Show(s, "Operation Sandstorm"); }
}

// ------------------------------------------------------------------------------------------------ wizard
class Wizard : Form
{
    // plug and play: Welcome (picture + one line) -> folder (auto-detected; display choice as one small dropdown) -> installing -> Finish (Play)
    Payload C; Options O = new Options(); int page = 0;
    Label title; Panel body; Button back, next, cancel;
    TextBox dirBox; ComboBox displayBox; CheckBox launch; ProgressBar bar; Label progLabel;
    bool installing; DateTime shown = DateTime.Now;

    public Wizard(Payload c)
    {
        C = c;
        O.Dir = c.Full ? c.S("default_dir") : U.FindGog(c.S("gog_id"));
        Text = c.S("product") + " Setup";
        ClientSize = new Size(560, 400); FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 9.5f); BackColor = Color.White;
        try { Icon = Icon.ExtractAssociatedIcon(Program.ExePath); } catch { }
        title = new Label { Left = 20, Top = 16, Width = 520, Height = 30, Font = new Font("Segoe UI", 14f, FontStyle.Bold) };
        body = new Panel { Left = 20, Top = 52, Width = 520, Height = 290 };
        Controls.Add(title); Controls.Add(body);
        Controls.Add(new Label { Left = 0, Top = 350, Width = 560, Height = 1, BorderStyle = BorderStyle.Fixed3D });
        back = new Button { Text = "< Back", Left = 290, Top = 362, Width = 80 };
        next = new Button { Text = "Next >", Left = 375, Top = 362, Width = 80 };
        cancel = new Button { Text = "Cancel", Left = 465, Top = 362, Width = 80 };
        back.Click += (s, e) => Show(page - 1);
        next.Click += (s, e) => Next();
        cancel.Click += (s, e) => { if (!installing) Close(); };
        Controls.Add(back); Controls.Add(next); Controls.Add(cancel);
        AcceptButton = next;
        FormClosing += (s, e) => { if (installing) e.Cancel = true; };
        Show(0);
    }

    void Show(int p)
    {
        page = p; body.Controls.Clear(); shown = DateTime.Now;
        back.Visible = p == 1; next.Enabled = true; cancel.Enabled = p < 3;
        next.Text = p == 1 ? "Install" : p == 3 ? "Finish" : "Next >";
        if (p == 0)
        {
            title.Text = ""; title.Height = 0; body.Top = 10; body.Height = 335;
            body.Controls.Add(new PictureBox { Left = 0, Top = 0, Width = 520, Height = 290, SizeMode = PictureBoxSizeMode.Zoom, Image = Payload.Art("welcome.png") ?? Payload.Avatar() });
            body.Controls.Add(new Label { Left = 0, Top = 300, Width = 520, Height = 28, TextAlign = ContentAlignment.MiddleCenter, Font = new Font("Segoe UI", 11f),
                                          Text = "Operation Sandstorm - a new IGI 2 mission by 1QDeath" });
            return;
        }
        title.Height = 30; body.Top = 52; body.Height = 290;
        if (p == 1)
        {
            title.Text = C.Full ? "Where to install" : "Your IGI 2 folder";
            body.Controls.Add(new Label { Left = 0, Top = 0, Width = 520, Height = 22, ForeColor = Color.DimGray,
                                          Text = C.Full ? "The game is installed into this folder." : string.IsNullOrEmpty(O.Dir) ? "Pick your IGI 2 folder (the one with igi2.exe in it) with Browse..." : "Setup found this IGI 2 folder - change it if needed." });
            dirBox = new TextBox { Left = 0, Top = 28, Width = 420, Text = O.Dir };
            var br = new Button { Left = 428, Top = 26, Width = 90, Text = "Browse..." };
            br.Click += (s, e) =>
            {
                using (var f = new FolderBrowserDialog { SelectedPath = dirBox.Text })
                    if (f.ShowDialog(this) == DialogResult.OK) dirBox.Text = C.Full && !U.IsGame(f.SelectedPath) && Directory.EnumerateFileSystemEntries(f.SelectedPath).Any()
                        ? Path.Combine(f.SelectedPath, "IGI2 Sandstorm") : f.SelectedPath;
            };
            body.Controls.Add(dirBox); body.Controls.Add(br);
            body.Controls.Add(new Label { Left = 0, Top = 74, Width = 60, Height = 22, Text = "Picture:" });
            displayBox = new ComboBox { Left = 62, Top = 71, Width = 230, DropDownStyle = ComboBoxStyle.DropDownList };
            displayBox.Items.AddRange(new object[] { "Sharp (recommended)", "Low-end PC", "Very low" });
            displayBox.SelectedIndex = O.Display == "low" ? 1 : O.Display == "verylow" ? 2 : 0;
            body.Controls.Add(displayBox);
        }
        else if (p == 2)
        {
            title.Text = "Installing";
            bar = new ProgressBar { Left = 0, Top = 20, Width = 518, Height = 22, Maximum = 1000 };
            progLabel = new Label { Left = 0, Top = 50, Width = 518, Height = 40, ForeColor = Color.DimGray };
            body.Controls.Add(bar); body.Controls.Add(progLabel);
            next.Enabled = false;
        }
        else
        {
            title.Text = "Ready";
            body.Controls.Add(new Label { Left = 0, Top = 0, Width = 518, Height = 60, Text = "Operation Sandstorm is installed. Start IGI 2 and pick it in the mission list." });
            launch = new CheckBox { Left = 0, Top = 70, Width = 300, Text = "Play now", Checked = true };
            body.Controls.Add(launch);
        }
    }

    void Next()
    {
        if (page == 1)
        {
            O.Dir = Installer.CleanDir(dirBox.Text); dirBox.Text = O.Dir;
            O.Display = displayBox.SelectedIndex == 1 ? "low" : displayBox.SelectedIndex == 2 ? "verylow" : "sharp";
            var err = Installer.Check(C, O.Dir);
            if (err != null) { MessageBox.Show(this, err, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning); return; }
            if ((DateTime.Now - shown).TotalMilliseconds < 600) return;      // a double-click on "Next" never also clicks "Install"
            Show(2); StartInstall(); return;
        }
        if (page == 3)
        {
            if (launch.Checked) try { Process.Start(new ProcessStartInfo(Path.Combine(O.Dir, "igi2.exe")) { WorkingDirectory = O.Dir }); } catch { }
            Close(); return;
        }
        Show(page + 1);
    }

    void StartInstall()
    {
        installing = true;
        var t = new Thread(() =>
        {
            Exception err = null;
            try { Installer.Run(C, O, (f, s) => BeginInvoke((Action)(() => { bar.Value = Math.Max(0, Math.Min(1000, (int)(f * 1000))); progLabel.Text = s; }))); }
            catch (Exception e) { err = e; }
            BeginInvoke((Action)(() =>
            {
                installing = false;
                if (err != null)
                {
                    Log.Write("ERROR at \"" + Installer.Step + "\": " + err);
                    bool changed = Installer.Changed;
                    MessageBox.Show(this, "Setup failed (" + Installer.Step + "): " + Program.Friendly(err) +
                                    (changed ? "\n\nRun Setup again after fixing this, or remove what was installed with Windows Settings > Apps > Operation Sandstorm (every changed file is backed up in " + Installer.BK + ")."
                                             : "\n\nNothing in your game was changed.") +
                                    (Log.PathName != null ? "\n\nIf it keeps failing, send this file to 1QDeath (Discord):\n" + Log.PathName : ""), Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
                    Close();
                }
                else
                {
                    if (Installer.Warnings.Count > 0) MessageBox.Show(this, string.Join("\n\n", Installer.Warnings), Text + " - please read", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    Show(3);
                }
            }));
        });
        t.IsBackground = true; t.Start();
    }

    public static void Shots(Payload c, string dir)
    {
        Directory.CreateDirectory(dir);
        var w = new Wizard(c);
        w.CreateControl(); w.Show();
        for (int p = 0; p <= 3; p++)
        {
            w.Show(p);
            if (p == 2) { w.bar.Value = 420; w.progLabel.Text = @"MISSIONS\multiplayer\sandstorm_sp\textures\sandstorm.res"; }
            Application.DoEvents();
            using (var b = new Bitmap(w.Width, w.Height)) { w.DrawToBitmap(b, new Rectangle(0, 0, w.Width, w.Height)); b.Save(Path.Combine(dir, "page" + p + ".png")); }
        }
        w.installing = false; w.Close();
    }
}
