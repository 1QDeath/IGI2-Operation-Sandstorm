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
    [STAThread]
    static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        var a = new Args(args);
        try { Log.PathName = Path.Combine(Path.GetTempPath(), "Sandstorm_Setup.log"); Log.Write("---- " + Application.ExecutablePath + " " + string.Join(" ", args)); } catch { }
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
            MessageBox.Show(e.Message, "Operation Sandstorm", MessageBoxButtons.OK, MessageBoxIcon.Error);
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
        p.Dir = Path.GetDirectoryName(Application.ExecutablePath);
        var first = Directory.GetFiles(p.Dir, "*.dat").OrderBy(x => x).FirstOrDefault(x =>
        {
            try { using (var z = ZipFile.OpenRead(x)) return z.GetEntry("_setup/setup.json") != null; } catch { return false; }
        });
        if (first == null) throw new Exception("The setup data file (Sandstorm*.dat) is missing next to Setup.exe.");
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
    public static string Sha1(string p) { using (var m = SHA1.Create()) using (var f = File.OpenRead(p)) return Hex(m.ComputeHash(f)); }
    static string Hex(byte[] b) { var s = new StringBuilder(); foreach (var x in b) s.Append(x.ToString("x2")); return s.ToString(); }
    public static void Link(string src, string dst)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(dst));
        if (!CreateHardLink(dst, src, IntPtr.Zero)) File.Copy(src, dst, true);
    }
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
    public static void RunDisplay(string game, string mode)
    {
        var cmd = Path.Combine(game, "IGI2_Display_Setup.cmd");
        if (mode == "none" || !File.Exists(cmd)) return;
        var psi = new ProcessStartInfo("cmd.exe", "/c \"\"" + cmd + "\" /" + mode + " /nostart\"");
        psi.WorkingDirectory = game; psi.CreateNoWindow = true; psi.UseShellExecute = false; psi.WindowStyle = ProcessWindowStyle.Hidden;
        psi.RedirectStandardInput = true;                       // a "pause" in the script reads end-of-input instead of waiting
        using (var p = Process.Start(psi)) { p.StandardInput.Close(); p.WaitForExit(120000); Log.Write("display " + mode + " exit " + (p.HasExited ? p.ExitCode.ToString() : "timeout")); }
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
        File.WriteAllBytes(p, enc.GetBytes(t));
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
        File.WriteAllBytes(p, enc.GetBytes(t));
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
    public static bool Readable(byte[] b)
    {
        try
        {
            if (b == null || b.Length < 64 || Encoding.ASCII.GetString(b, 0, 4) != "LOOP") return false;
            long code = U32(b, 44), size = U32(b, 48), symT = U32(b, 12), symD = U32(b, 16), symTS = U32(b, 20);
            if (code + size > b.Length || symT + symTS > b.Length || symD >= b.Length) return false;
            for (int k = 0; k < symTS / 4; k++) { long o = symD + U32(b, (int)symT + 4 * k); if (o < 0 || o >= b.Length || Array.IndexOf(b, (byte)0, (int)o) < 0) return false; }
            int c0, s0; Find(b, out c0, out s0);
            return true;
        }
        catch { return false; }
    }

    static List<Site> Find(byte[] b, out int code, out int size)
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
        o.Dir = a.Get("/D=") ?? (c.Full ? c.S("default_dir") : U.FindGog(c.S("gog_id")));
        if (a.Has("/noshortcut")) o.Shortcut = false;
        if (a.Has("/unknownexe")) { o.ForceUnknownExe = true; AllowUnknownExe = true; }
        if (a.Get("/display=") != null) o.Display = a.Get("/display=").ToLowerInvariant();
        string err = Check(c, o.Dir);
        if (err != null) { Console.Error.WriteLine(err); return 2; }
        Run(c, o, (f, s) => { });
        Console.WriteLine("installed to " + o.Dir);
        return 0;
    }

    // null = fine, else the reason
    public static string Check(Payload c, string dir)
    {
        if (string.IsNullOrWhiteSpace(dir)) return "Choose a folder.";
        if (U.GameRunning(dir)) return "IGI 2 is running from this folder - close the game first.";
        if (c.Full)
        {
            if (File.Exists(Path.Combine(dir, "igi2.exe"))) return "That folder already holds an IGI 2 - choose an empty or new folder.";
            var root = Path.GetPathRoot(Path.GetFullPath(dir));
            if (new DriveInfo(root).AvailableFreeSpace < c.L("size") + (200L << 20)) return "Not enough free disk space on " + root + " (needs " + (c.L("size") >> 20) + " MB).";
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
        bool ours = File.Exists(Path.Combine(bk, "manifest.txt"));
        if (Directory.Exists(Path.Combine(loc, c.S("folder"))) && !ours) return "This folder already holds a Sandstorm mission that this setup did not install - remove it first.";
        if (new DriveInfo(Path.GetPathRoot(Path.GetFullPath(dir))).AvailableFreeSpace < c.L("size") + (100L << 20) && !ours) return "Not enough free disk space.";
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

    public static void Run(Payload c, Options o, Action<double, string> prog)
    {
        Directory.CreateDirectory(o.Dir);
        if (c.Full) RunFull(c, o, prog); else RunAddon(c, o, prog);
    }

    // ---------------------------------------------------------------- full game
    static void RunFull(Payload c, Options o, Action<double, string> prog)
    {
        string dir = Path.GetFullPath(o.Dir);
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
        File.Copy(Application.ExecutablePath, un, true);
        list.Add("Uninstall.exe");
        File.WriteAllLines(Path.Combine(dir, "uninstall.dat"), new[] { "full|" + c.S("key") + "|" + c.S("product") }.Concat(list.Select(x => "f|" + x)));
        if (o.Shortcut) { var l = U.DesktopLnk(c.S("product")); U.Shortcut(l, Path.Combine(dir, "igi2.exe"), dir, Path.Combine(dir, "igi2.exe")); File.AppendAllText(Path.Combine(dir, "uninstall.dat"), "lnk|" + l + "\r\n"); }
        U.Register(c, dir, un, total);
        prog(1, "Done");
    }

    // ---------------------------------------------------------------- add-on for the GOG game
    class Ctx
    {
        public string G, Bk; public List<string[]> Rows = new List<string[]>();
        public Dictionary<string, string> Files = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        public void Save() { Directory.CreateDirectory(Bk); File.WriteAllLines(Path.Combine(Bk, "manifest.txt"), Rows.Select(r => string.Join("|", r))); }
        public void Row(params string[] r) { Rows.Add(r); Save(); }
        public void Backup(string rel)
        {
            if (Files.ContainsKey(rel)) return;
            var p = Path.Combine(G, rel);
            if (File.Exists(p))
            {
                var d = Path.Combine(Bk, "files", rel); Directory.CreateDirectory(Path.GetDirectoryName(d)); File.Copy(p, d, true);
                Files[rel] = "backup";
            }
            else Files[rel] = "new";
            Row("file", Files[rel], rel);
        }
        public string Orig(string rel) { string h; return Files.TryGetValue(rel, out h) && h == "backup" ? Path.Combine(Bk, "files", rel) : Path.Combine(G, rel); }
        public void Put(byte[] data, string rel)
        {
            Backup(rel); var d = Path.Combine(G, rel); Directory.CreateDirectory(Path.GetDirectoryName(d));
            if (File.Exists(d)) File.Delete(d);
            File.WriteAllBytes(d, data);
        }
        public static Ctx Load(string g)
        {
            var c = new Ctx { G = g, Bk = Path.Combine(g, BK) };
            var m = Path.Combine(c.Bk, "manifest.txt");
            if (File.Exists(m)) foreach (var l in File.ReadAllLines(m)) { var r = l.Split('|'); c.Rows.Add(r); if (r[0] == "file") c.Files[r[2]] = r[1]; }
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
            if (!x.Rows.Any(r => r[0] == "dir" && r[1] == relDir)) x.Row("dir", relDir);
            // old Sandstorm mid-mission saves break a new build: moved into the backup folder
            var sg = Path.Combine(g, "savegames");
            if (Directory.Exists(sg))
                foreach (var f in Directory.GetFiles(sg, "*.igi2save"))
                {
                    var parts = Path.GetFileNameWithoutExtension(f).Split('-');
                    if (parts.Length == 4 && parts[2] == c.S("mission_id")) { var d = Path.Combine(x.Bk, "old_saves"); Directory.CreateDirectory(d); File.Move(f, Path.Combine(d, Path.GetFileName(f))); }
                }
            prog(0.32, "Mission folder");
            if (Directory.Exists(target)) Directory.Delete(target, true);
            foreach (var f in Directory.GetFiles(baseDir, "*", SearchOption.AllDirectories))
            {
                var n = Path.GetFileName(f).ToLowerInvariant(); if (n == "mission.qvm" || n == "objects.qvm") continue;
                var d = Path.Combine(target, f.Substring(baseDir.Length + 1)); Directory.CreateDirectory(Path.GetDirectoryName(d)); File.Copy(f, d, true);
            }
            var com = Path.Combine(loc, c.S("own_common"));
            foreach (var f in Directory.GetFiles(com, "*", SearchOption.AllDirectories))
            {
                var rel = f.Substring(com.Length + 1); if (rel.Split('\\')[0].Equals("sounds", StringComparison.OrdinalIgnoreCase)) continue;
                U.Link(f, Path.Combine(target, "common", rel));
            }
            foreach (var f in c.List("deleted")) { var p = Path.Combine(target, f.Replace('/', '\\')); if (File.Exists(p)) File.Delete(p); }
            var files = c.List("files"); int i = 0;
            foreach (var f in files)
            {
                var d = Path.Combine(target, f.Replace('/', '\\')); Directory.CreateDirectory(Path.GetDirectoryName(d));
                if (File.Exists(d)) File.Delete(d);
                z.GetEntry("mission/" + f).ExtractToFile(d);
                prog(0.35 + 0.35 * (++i) / files.Count, f);
            }
            foreach (var kv in c.Map("copies"))
            {
                var d = Path.Combine(target, kv.Key.Replace('/', '\\')); Directory.CreateDirectory(Path.GetDirectoryName(d));
                if (File.Exists(d)) File.Delete(d);
                File.Copy(Path.Combine(g, kv.Value), d);
            }
            foreach (var kv in built)
            {
                var d = Path.Combine(target, kv.Key.Replace('/', '\\')); Directory.CreateDirectory(Path.GetDirectoryName(d));
                if (File.Exists(d)) File.Delete(d);
                File.WriteAllBytes(d, kv.Value);
            }
            prog(0.75, "Texts and pictures");
            LangAdd(x, c);                                    // our texts into EVERY language folder's files (English text)
            SpriteAdd(x, c, z);                               // the mission picture into missionsprites.res
            PatchLoading(x, z, c.List("loading"));
            foreach (var lang in new[] { "english", "USA" }) x.Put(Entry(z, "shared/intro/congratulations.jpg"), Path.Combine("SCREENS", "intro", lang, "congratulations.jpg"));
            // mission list: the player's own list + Sandstorm at the end (any version's list)
            var lst = Path.Combine("MISSIONS", "igi2.qvm");
            x.Backup(lst);
            var lraw = File.ReadAllBytes(x.Orig(lst));
            var ids = Qvm.ListIds(lraw);
            if (ids == null || ids.Count == 0) throw new Exception("MISSIONS\\igi2.qvm (the mission list) could not be read.");
            int mid = (int)c.L("mission_id");
            ids.Remove(mid); ids.Add(mid);
            x.Put(Qvm.ListEncode(ids, lraw), lst);
            // profile: Sandstorm (last in the list) unlocked
            int last = ids.Count - 1;
            var cfg = Path.Combine(g, "config.qvm");
            // v1.5 (a friend's v1.4 install died here: "Index was out of range ... startIndex"): a damaged profile (0 bytes / cut short
            // after a game crash) is replaced by the default one - backed up, restored on uninstall
            bool cfgOk = File.Exists(cfg) && Qvm.Readable(File.ReadAllBytes(x.Files.ContainsKey("config.qvm") && x.Files["config.qvm"] == "backup" ? x.Orig("config.qvm") : cfg)) && Qvm.Readable(File.ReadAllBytes(cfg));
            if (File.Exists(cfg) && !cfgOk)
            {
                Log.Write("config.qvm unreadable (" + new FileInfo(cfg).Length + " bytes): default profile used");
                Warnings.Add("Your game profile (config.qvm) was damaged, so it was replaced by a fresh one (the old file is in " + BK + "). Set your video / control options again in the game.");
                x.Put(Qvm.SetProgress(Entry(z, "shared/config_default.qvm"), (k, cur) => last), "config.qvm");
            }
            else if (cfgOk)
            {
                x.Backup("config.qvm");
                var b = File.ReadAllBytes(x.Orig("config.qvm"));
                var basep = Qvm.Progress(b);
                File.WriteAllBytes(cfg, Qvm.SetProgress(File.ReadAllBytes(cfg), (k, cur) => last));
                x.Row("config", string.Join(",", basep.Select(kv => kv.Key + "=" + kv.Value)), U.Md5(cfg));
            }
            else x.Put(Qvm.SetProgress(Entry(z, "shared/config_default.qvm"), (k, cur) => last), "config.qvm");
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
                U.RunDisplay(g, o.Display);
                U.SharpLook(c, g, o.Display);
                U.SafeConf(g);
                // the display script also writes config.qvm (the game's own resolution): the profile we hand back is the one after it
                var cr = x.Rows.LastOrDefault(r => r[0] == "config"); var cq = Path.Combine(g, "config.qvm");
                if (cr != null && File.Exists(cq)) x.Row("config", cr[1], U.Md5(cq));
            }
            string un = Path.Combine(x.Bk, "Uninstall.exe");
            File.Copy(Application.ExecutablePath, un, true);
            x.Row("meta", c.S("key"), c.S("product"));
            if (o.Shortcut) { var l = U.DesktopLnk("IGI 2 - Operation Sandstorm"); U.Shortcut(l, Path.Combine(g, "igi2.exe"), g, Path.Combine(g, "igi2.exe")); x.Row("lnk", l); }
            U.Register(c, g, un, c.L("size"));
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
            ch.InsertRange(Math.Max(0, pathIdx - 1), add);
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
        var names = new Dictionary<string, int>();
        for (int i = 0; i < ch.Count; i++) if (Encoding.ASCII.GetString(ch[i].Tag) == "NAME") names[Ilff.Name(ch[i])] = i;
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
        foreach (var r in extra.Split(',').Select(s => s.Trim()).Where(s => s.Length > 0)) if (!have.Contains(r)) have.Add(r);
        t = t.Substring(0, m.Groups[2].Index) + " " + string.Join(", ", have) + t.Substring(m.Groups[2].Index + m.Groups[2].Length);
        File.WriteAllBytes(p, enc.GetBytes(t));
    }
}

// ------------------------------------------------------------------------------------------------ uninstall
static class Uninstaller
{
    public static int Run(Args a)
    {
        bool silent = a.Has("/S");
        string here = Path.GetDirectoryName(Application.ExecutablePath);
        bool full = File.Exists(Path.Combine(here, "uninstall.dat"));
        bool addon = File.Exists(Path.Combine(here, "manifest.txt"));
        if (!full && !addon) { Msg(silent, "Nothing to uninstall here."); return 1; }
        if (U.GameRunning(addon ? Path.GetDirectoryName(here) : here)) { Msg(silent, "IGI 2 is running - close the game first."); return 2; }
        string product = "Operation Sandstorm";
        if (!silent && MessageBox.Show("Remove " + product + "?", product, MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return 0;
        string selfDir = here;
        if (full)
        {
            var lines = File.ReadAllLines(Path.Combine(here, "uninstall.dat"));
            var head = lines[0].Split('|');
            foreach (var l in lines.Skip(1))
            {
                var r = l.Split(new[] { '|' }, 2);
                try
                {
                    if (r[0] == "f" && r[1] != "Uninstall.exe") { var p = Path.Combine(here, r[1]); if (File.Exists(p)) File.Delete(p); }
                    else if (r[0] == "lnk" && File.Exists(r[1])) File.Delete(r[1]);
                }
                catch { }
            }
            File.Delete(Path.Combine(here, "uninstall.dat"));
            // what the display script and the game wrote next to the files we installed (no player saves: savegames stays)
            foreach (var f in new[] { "dgVoodoo.conf.display-backup", "config.qvm.display-backup", "MultiMonitor.log", "Multiplayer.log", "igi2.RPT",
                                      "warninglog.txt", "flymode.log", "flymode_maxdamage.txt", @"hd\hdmod.log" })
                try { var p = Path.Combine(here, f); if (File.Exists(p)) File.Delete(p); } catch { }
            // whatever the game wrote itself (saves, profile, logs) stays only if the player asks: here we remove the folder tree we made
            foreach (var d in Directory.GetDirectories(here, "*", SearchOption.AllDirectories).OrderByDescending(s => s.Length))
                try { if (!Directory.EnumerateFileSystemEntries(d).Any()) Directory.Delete(d); } catch { }
            U.Unregister(head[1]);
        }
        else
        {
            string g = Path.GetDirectoryName(here);
            var rows = File.ReadAllLines(Path.Combine(here, "manifest.txt")).Select(l => l.Split('|')).ToList();
            string key = "IGI2_OperationSandstorm"; string cfgRow = null, cfgMd5 = null;
            foreach (var r in rows) { if (r[0] == "meta") { key = r[1]; product = r[2]; } if (r[0] == "config") { cfgRow = r[1]; cfgMd5 = r[2]; } }
            foreach (var r in rows.Where(r => r[0] == "dir")) { var p = Path.Combine(g, r[1]); if (Directory.Exists(p)) Directory.Delete(p, true); }
            foreach (var r in rows.Where(r => r[0] == "file"))
            {
                var p = Path.Combine(g, r[2]);
                if (r[2].Equals("config.qvm", StringComparison.OrdinalIgnoreCase) && r[1] == "backup" && cfgMd5 != null && File.Exists(p) && U.Md5(p) != cfgMd5)
                {
                    // the player played since: keep the profile, put the campaign position back
                    var basep = cfgRow.Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries).Select(s => s.Split('=')).ToDictionary(s => int.Parse(s[0]), s => int.Parse(s[1]));
                    File.WriteAllBytes(p, Qvm.SetProgress(File.ReadAllBytes(p), (k, cur) => basep.ContainsKey(k) ? basep[k] : 0));
                    continue;
                }
                if (r[1] == "backup") { if (File.Exists(p)) File.Delete(p); File.Copy(Path.Combine(here, "files", r[2]), p); }
                else if (File.Exists(p)) File.Delete(p);
            }
            foreach (var lang in new[] { "english", "USA" })
            {
                var d = Path.Combine(g, "SCREENS", "intro", lang);
                try { if (Directory.Exists(d) && !Directory.EnumerateFileSystemEntries(d).Any()) Directory.Delete(d); } catch { }
            }
            if (rows.Any(r => r[0] == "file" && r[1] == "new" && r[2].Equals("IGI2HD.asi", StringComparison.OrdinalIgnoreCase)))
            {
                var hd = Path.Combine(g, "hd");                 // the log our HD add-on wrote, then the folder if it is empty
                try { if (File.Exists(Path.Combine(hd, "hdmod.log"))) File.Delete(Path.Combine(hd, "hdmod.log")); if (Directory.Exists(hd) && !Directory.EnumerateFileSystemEntries(hd).Any()) Directory.Delete(hd); } catch { }
            }
            foreach (var r in rows.Where(r => r[0] == "lnk")) try { if (File.Exists(r[1])) File.Delete(r[1]); } catch { }
            var old = Path.Combine(here, "old_saves");
            if (Directory.Exists(old)) { var keep = Path.Combine(g, "savegames_sandstorm_old"); if (!Directory.Exists(keep)) Directory.Move(old, keep); }
            U.Unregister(key);
        }
        // delete this exe (and its folder when empty) after it exits
        string self = Application.ExecutablePath;
        string script = "/c ping -n 3 127.0.0.1 >nul & del /f /q \"" + self + "\"" + (addon ? " & rmdir /s /q \"" + here + "\"" : " & rmdir \"" + here + "\"");
        Process.Start(new ProcessStartInfo("cmd.exe", script) { CreateNoWindow = true, UseShellExecute = false, WindowStyle = ProcessWindowStyle.Hidden });
        Msg(silent, product + " was removed.");
        return 0;
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
    bool installing;

    public Wizard(Payload c)
    {
        C = c;
        O.Dir = c.Full ? c.S("default_dir") : U.FindGog(c.S("gog_id"));
        Text = c.S("product") + " Setup";
        ClientSize = new Size(560, 400); FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 9.5f); BackColor = Color.White;
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
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
        page = p; body.Controls.Clear();
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
                                          Text = C.Full ? "The game is installed into this folder." : "Setup found this IGI 2 folder - change it if needed." });
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
            O.Dir = dirBox.Text.Trim();
            O.Display = displayBox.SelectedIndex == 1 ? "low" : displayBox.SelectedIndex == 2 ? "verylow" : "sharp";
            var err = Installer.Check(C, O.Dir);
            if (err != null) { MessageBox.Show(this, err, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning); return; }
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
                    Log.Write("ERROR at \"" + progLabel.Text + "\": " + err);
                    MessageBox.Show(this, "Setup failed (" + progLabel.Text + "): " + err.Message + "\n\nYour game files changed so far are in " + Installer.BK + " and come back with Uninstall." +
                                    (Log.PathName != null ? "\n\nPlease send this file to 1QDeath (Discord):\n" + Log.PathName : ""), Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
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
