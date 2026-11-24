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
    public static bool GameRunning() { return Process.GetProcessesByName("igi2").Length > 0; }
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
        if (Encoding.ASCII.GetString(d, 0, 4) != "ILFF") throw new Exception("not an ILFF file");
        align = BitConverter.ToUInt32(d, 8); form = new byte[4]; Array.Copy(d, 16, form, 0, 4);
        var r = new List<Chunk>(); int p = 20;
        while (p < d.Length)
        {
            var tg = new byte[4]; Array.Copy(d, p, tg, 0, 4);
            var c = new Chunk { Tag = tg, Al = BitConverter.ToUInt32(d, p + 8) };
            int sz = (int)BitConverter.ToUInt32(d, p + 4); uint nx = BitConverter.ToUInt32(d, p + 12);
            c.Data = new byte[sz]; Array.Copy(d, p + 16, c.Data, 0, sz); r.Add(c);
            if (nx == 0) break; p += (int)nx;
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

    static List<Site> Find(byte[] b, out int code, out int size)
    {
        code = (int)U32(b, 44); size = (int)U32(b, 48);
        var r = new List<Site>();
        if (Encoding.ASCII.GetString(b, 0, 4) != "LOOP") return r;
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
}

static class Installer
{
    public const string BK = "_Sandstorm_backup";

    public static int Silent(Payload c, Args a)
    {
        var o = new Options();
        o.Dir = a.Get("/D=") ?? (c.Full ? c.S("default_dir") : U.FindGog(c.S("gog_id")));
        if (a.Has("/noshortcut")) o.Shortcut = false;
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
        if (U.GameRunning()) return "IGI 2 is running - close the game first.";
        if (c.Full)
        {
            if (File.Exists(Path.Combine(dir, "igi2.exe"))) return "That folder already holds an IGI 2 - choose an empty or new folder.";
            var root = Path.GetPathRoot(Path.GetFullPath(dir));
            if (new DriveInfo(root).AvailableFreeSpace < c.L("size") + (200L << 20)) return "Not enough free disk space on " + root + " (needs " + (c.L("size") >> 20) + " MB).";
            return null;
        }
        if (!U.IsGame(dir)) return "This is not an IGI 2 folder (igi2.exe and MISSIONS\\multiplayer expected).";
        string loc = Path.Combine(dir, "MISSIONS", c.S("location"));
        if (!Directory.Exists(Path.Combine(loc, c.S("base")))) return "The multiplayer map Sandstorm of IGI 2 is missing in this folder.";
        var bk = Path.Combine(dir, BK);
        bool ours = File.Exists(Path.Combine(bk, "manifest.txt"));
        if (Directory.Exists(Path.Combine(loc, c.S("folder"))) && !ours) return "This folder already holds a Sandstorm mission that this setup did not install - remove it first.";
        if (!ours)
        {
            foreach (var kv in c.Map("shared"))
            {
                var p = Path.Combine(dir, kv.Key);
                if (!File.Exists(p) || U.Md5(p) != kv.Value) return "This IGI 2 has changed game files (" + kv.Key + " - another mod?). Setup needs the GOG game files.";
            }
            var ex = U.Sha1(Path.Combine(dir, "igi2.exe"));
            if (!c.List("exe_orig_sha1").Contains(ex) && ex != c.S("exe_new_sha1")) return "This igi2.exe is not one Setup knows (GOG or GOG with the widescreen patch).";
            var lst = Path.Combine(dir, "MISSIONS", "igi2.qvm");
            if (!File.Exists(lst)) return "MISSIONS\\igi2.qvm is missing.";
        }
        if (!File.Exists(Path.Combine(dir, "dgVoodoo.conf"))) return "dgVoodoo.conf is missing next to igi2.exe (the GOG game ships it).";
        if (new DriveInfo(Path.GetPathRoot(Path.GetFullPath(dir))).AvailableFreeSpace < c.L("size") + (100L << 20) && !ours) return "Not enough free disk space.";
        return null;
    }

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

    static void RunAddon(Payload c, Options o, Action<double, string> prog)
    {
        string g = Path.GetFullPath(o.Dir);
        var x = Ctx.Load(g);
        Log.PathName = null;
        string loc = Path.Combine(g, "MISSIONS", c.S("location")), target = Path.Combine(loc, c.S("folder")), baseDir = Path.Combine(loc, c.S("base"));
        string relDir = Path.Combine("MISSIONS", c.S("location"), c.S("folder"));
        if (!x.Rows.Any(r => r[0] == "dir" && r[1] == relDir)) x.Row("dir", relDir);
        using (var z = ZipFile.OpenRead(c.Parts[0]))
        {
            // old Sandstorm mid-mission saves break a new build: moved into the backup folder
            var sg = Path.Combine(g, "savegames");
            if (Directory.Exists(sg))
                foreach (var f in Directory.GetFiles(sg, "*.igi2save"))
                {
                    var parts = Path.GetFileNameWithoutExtension(f).Split('-');
                    if (parts.Length == 4 && parts[2] == c.S("mission_id")) { var d = Path.Combine(x.Bk, "old_saves"); Directory.CreateDirectory(d); File.Move(f, Path.Combine(d, Path.GetFileName(f))); }
                }
            prog(0.02, "Mission folder");
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
                prog(0.05 + 0.75 * (++i) / files.Count, f);
            }
            // mission files that are the player's own game files (copied, not shipped)
            foreach (var kv in c.Map("copies"))
            {
                var d = Path.Combine(target, kv.Key.Replace('/', '\\')); Directory.CreateDirectory(Path.GetDirectoryName(d));
                if (File.Exists(d)) File.Delete(d);
                File.Copy(Path.Combine(g, kv.Value), d);
            }
            // the .res files are rebuilt from the player's own game files + our chunks (recipes)
            var recs = Recipes(c);
            int ri = 0;
            foreach (var r in recs.Where(r => (string)r["kind"] == "mission"))
            {
                var rel = (string)r["rel"];
                var d = Path.Combine(target, rel.Replace('/', '\\'));
                Directory.CreateDirectory(Path.GetDirectoryName(d));
                var data = BuildRes(r, Entry(z, (string)r["bin"]), gr => x.Orig(gr));
                if (File.Exists(d)) File.Delete(d);
                File.WriteAllBytes(d, data);
                prog(0.6 + 0.2 * (++ri) / recs.Count, rel);
            }
            prog(0.82, "Texts and pictures");
            foreach (var kv in c.Map("shared"))
            {
                var r = recs.FirstOrDefault(q => (string)q["kind"] == "shared" && ((string)q["rel"]).Replace('/', '\\').Equals(kv.Key, StringComparison.OrdinalIgnoreCase));
                if (r != null) { x.Backup(kv.Key); x.Put(BuildRes(r, Entry(z, (string)r["bin"]), gr => x.Orig(gr)), kv.Key); }
                else x.Put(Entry(z, "shared/" + kv.Key.Replace('\\', '/')), kv.Key);
            }
            PatchLoading(x, z, c.List("loading"));
            foreach (var lang in new[] { "english", "USA" }) x.Put(Entry(z, "shared/intro/congratulations.jpg"), Path.Combine("SCREENS", "intro", lang, "congratulations.jpg"));
            x.Put(Entry(z, "shared/igi2.qvm"), Path.Combine("MISSIONS", "igi2.qvm"));
            // profile: Sandstorm (last in the list) unlocked
            int last = (int)c.L("n_ids") - 1;
            var cfg = Path.Combine(g, "config.qvm");
            if (File.Exists(cfg))
            {
                x.Backup("config.qvm");
                var b = File.ReadAllBytes(x.Orig("config.qvm"));
                var basep = Qvm.Progress(b);
                File.WriteAllBytes(cfg, Qvm.SetProgress(File.ReadAllBytes(cfg), (k, cur) => last));
                x.Row("config", string.Join(",", basep.Select(kv => kv.Key + "=" + kv.Value)), U.Md5(cfg));
            }
            else x.Put(Entry(z, "shared/config_default.qvm"), "config.qvm");
            prog(0.9, "Game exe and display");
            PatchExe(x, c);
            // our ASI loader only where none is there (a patched game brings its own), then the HD menu add-on (when shipped)
            if (z.GetEntry("exe/version.dll") != null && !File.Exists(Path.Combine(g, "version.dll"))) x.Put(Entry(z, "exe/version.dll"), "version.dll");
            if (z.GetEntry("exe/IGI2HD.asi") != null) x.Put(Entry(z, "exe/IGI2HD.asi"), "IGI2HD.asi");
            foreach (var f in c.List("hd")) x.Put(Entry(z, "exe/hd/" + f), Path.Combine("hd", f));
            EditConf(x, c.S("extra_res"));
            if (z.GetEntry("display/IGI2_Display_Setup.cmd") != null) x.Put(Entry(z, "display/IGI2_Display_Setup.cmd"), "IGI2_Display_Setup.cmd");
            x.Put(Entry(z, "Sandstorm - README.txt"), "Sandstorm - README.txt");
        }
        foreach (var f in new[] { "dgVoodoo.conf.display-backup", "config.qvm.display-backup" }) x.Backup(f);   // the display script's own backups: removed again on uninstall
        U.RunDisplay(g, o.Display);
        U.SharpLook(c, g, o.Display);
        string un = Path.Combine(x.Bk, "Uninstall.exe");
        File.Copy(Application.ExecutablePath, un, true);
        x.Row("meta", c.S("key"), c.S("product"));
        if (o.Shortcut) { var l = U.DesktopLnk("IGI 2 - Operation Sandstorm"); U.Shortcut(l, Path.Combine(g, "igi2.exe"), g, Path.Combine(g, "igi2.exe")); x.Row("lnk", l); }
        U.Register(c, g, un, c.L("size"));
        prog(0.96, "Checking files");
        int bad = 0;
        bool patched = File.Exists(Path.Combine(g, c.S("patch_mark")));
        x.Row("base", patched ? "patched" : "gog");
        foreach (var kv in c.Map(patched ? "tree_patch" : "tree"))
        {
            var p = Path.Combine(target, kv.Key.Replace('/', '\\'));
            if (!File.Exists(p) || U.Md5(p) != kv.Value) bad++;
        }
        x.Row("verify", bad.ToString());
        if (bad > 0) Console.Error.WriteLine("verify: " + bad + " files differ");
        prog(1, bad == 0 ? "Done" : "Done (" + bad + " mission files differ from the expected game files)");
    }

    static List<Dictionary<string, object>> Recipes(Payload c)
    {
        var r = new List<Dictionary<string, object>>(); object o;
        if (c.J.TryGetValue("recipes", out o) && o is System.Collections.ArrayList) foreach (var q in (System.Collections.ArrayList)o) r.Add((Dictionary<string, object>)q);
        return r;
    }

    // a recipe: every chunk is either a reference (game file "g" + chunk name "n", GOG md5 "m") or ours (offset "o" / length "l" in the blob)
    static byte[] BuildRes(Dictionary<string, object> r, byte[] blob, Func<string, string> rootOf)
    {
        var rec = (Dictionary<string, object>)r["rec"];
        var cache = new Dictionary<string, Dictionary<string, byte[]>>(StringComparer.OrdinalIgnoreCase);
        var ch = new List<Ilff.Chunk>(); int other = 0;
        foreach (Dictionary<string, object> c in (System.Collections.ArrayList)rec["chunks"])
        {
            byte[] d;
            if (c.ContainsKey("g"))
            {
                var rel = (string)c["g"];
                Dictionary<string, byte[]> byName;
                if (!cache.TryGetValue(rel, out byName))
                {
                    var path = rootOf(rel);
                    if (!File.Exists(path)) throw new Exception("game file missing: " + rel);
                    uint a0; byte[] f0; var src = Ilff.Read(File.ReadAllBytes(path), out a0, out f0);
                    byName = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase);
                    for (int i = 0; i + 1 < src.Count; i++)
                        if (Encoding.ASCII.GetString(src[i].Tag) == "NAME") byName[Ilff.Name(src[i])] = src[i + 1].Data;
                    cache[rel] = byName;
                }
                if (!byName.TryGetValue((string)c["n"], out d)) throw new Exception("game file " + rel + " has no " + c["n"]);
                using (var m = MD5.Create()) if (BitConverter.ToString(m.ComputeHash(d)).Replace("-", "").ToLower() != (string)c["m"]) other++;
            }
            else
            {
                int o = Convert.ToInt32(c["o"]), l = Convert.ToInt32(c["l"]);
                d = new byte[l]; Array.Copy(blob, o, d, 0, l);
            }
            ch.Add(new Ilff.Chunk { Tag = Encoding.GetEncoding(28591).GetBytes((string)c["t"]), Data = d, Al = Convert.ToUInt32(c["a"]) });
        }
        if (other > 0) Log.Write(r["rel"] + ": " + other + " chunks from a patched game");
        return Ilff.Write(ch, Convert.ToUInt32(rec["align"]), Encoding.GetEncoding(28591).GetBytes((string)rec["form"]), (bool)rec["pad_last"]);
    }

    // igi2.exe is not shipped: the player's own exe (GOG, or GOG with the widescreen patch: 4 header bytes apart) gets our byte patches
    static void PatchExe(Ctx x, Payload c)
    {
        var p = (Dictionary<string, object>)c.J["exe_patch"];
        x.Backup("igi2.exe");
        var src = File.ReadAllBytes(x.Orig("igi2.exe"));
        string sha; using (var s1 = SHA1.Create()) sha = BitConverter.ToString(s1.ComputeHash(src)).Replace("-", "").ToLower();
        if (!c.List("exe_orig_sha1").Contains(sha) && sha != (string)p["result_sha1"]) throw new Exception("igi2.exe is not a GOG exe Setup knows (sha1 " + sha.Substring(0, 8) + ")");
        var size = Convert.ToInt32(p["size"]);
        var b = new byte[size];
        Array.Copy(src, b, Math.Min(src.Length, size));
        foreach (System.Collections.ArrayList run in (System.Collections.ArrayList)p["runs"])
        {
            int off = Convert.ToInt32(run[0]); var hex = (string)run[1];
            for (int i = 0; i < hex.Length / 2; i++) b[off + i] = Convert.ToByte(hex.Substring(2 * i, 2), 16);
        }
        var tail = (string)p["tail"]; int t0 = size - tail.Length / 2;
        for (int i = 0; i < tail.Length / 2; i++) b[t0 + i] = Convert.ToByte(tail.Substring(2 * i, 2), 16);
        using (var s1 = SHA1.Create()) sha = BitConverter.ToString(s1.ComputeHash(b)).Replace("-", "").ToLower();
        if (sha != (string)p["result_sha1"]) throw new Exception("patched igi2.exe check failed");
        x.Put(b, "igi2.exe");
    }

    static void PatchLoading(Ctx x, ZipArchive z, List<string> pics)
    {
        string rel = Path.Combine("MENUSYSTEM", "loadingscreen.res");
        x.Backup(rel);
        var raw = File.ReadAllBytes(x.Orig(rel)); uint al; byte[] form;
        var ch = Ilff.Read(raw, out al, out form);
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
        string rel = "dgVoodoo.conf"; x.Backup(rel);
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
        if (U.GameRunning()) { Msg(silent, "IGI 2 is running - close the game first."); return 2; }
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
    Payload C; Options O = new Options(); int page = 0;
    Panel side, body; Label title, sub; Button back, next, cancel;
    TextBox dirBox; CheckBox shortcut, launch; RadioButton rSharp, rLow, rVery; ProgressBar bar; Label progLabel, finishLabel;
    bool installing, finished;

    public Wizard(Payload c)
    {
        C = c;
        O.Dir = c.Full ? c.S("default_dir") : U.FindGog(c.S("gog_id"));
        Text = c.S("product") + " Setup";
        ClientSize = new Size(640, 480); FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 9f); BackColor = Color.White;
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
        // header art (Jones in the sandstorm, Made by 1QDeath) across the top of every page
        side = new Panel { Left = 0, Top = 0, Width = 640, Height = 85, BackColor = Color.FromArgb(40, 24, 10) };
        side.Controls.Add(new PictureBox { Left = 0, Top = 0, Width = 640, Height = 85, SizeMode = PictureBoxSizeMode.StretchImage, Image = Payload.Art("header.png") ?? Payload.Avatar() });
        Controls.Add(side);
        title = new Label { Left = 18, Top = 93, Width = 600, Height = 30, Font = new Font("Segoe UI", 14f, FontStyle.Bold) };
        sub = new Label { Left = 20, Top = 124, Width = 600, Height = 28, ForeColor = Color.DimGray };
        Controls.Add(title); Controls.Add(sub);
        body = new Panel { Left = 20, Top = 154, Width = 600, Height = 270 };
        Controls.Add(body);
        Controls.Add(new Label { Left = 0, Top = 430, Width = 640, Height = 1, BorderStyle = BorderStyle.Fixed3D });
        Controls.Add(new Label { Left = 12, Top = 447, Width = 300, Height = 20, ForeColor = Color.Gray, Text = c.S("made_by") + "  |  " + c.S("discord") });
        back = new Button { Text = "< Back", Left = 375, Top = 443, Width = 80 };
        next = new Button { Text = "Next >", Left = 460, Top = 443, Width = 80 };
        cancel = new Button { Text = "Cancel", Left = 550, Top = 443, Width = 80 };
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
        back.Enabled = p > 0 && p < 3; next.Enabled = true; cancel.Enabled = p < 4;
        next.Text = p == 2 ? "Install" : p == 4 ? "Finish" : "Next >";
        if (p == 0)
        {
            title.Text = "Welcome"; sub.Text = C.S("product") + " " + C.S("version");
            var t = C.S("welcome") + "\n\n" + C.S("made_by") + "   -   " + C.S("discord");
            if (C.S("thanks").Length > 0) t += "\n\n" + C.S("thanks");
            t += "\n\nIGI 2: Covert Strike (c) Innerloop Studios / Codemasters.\nClose IGI 2 before you continue.";
            var art = Payload.Art("welcome.png") ?? Payload.Avatar();
            body.Controls.Add(new PictureBox { Left = 0, Top = 0, Width = 340, Height = 258, SizeMode = PictureBoxSizeMode.Zoom, Image = art });
            body.Controls.Add(new Label { Left = 352, Top = 2, Width = 248, Height = 262, Text = t });
        }
        else if (p == 1)
        {
            title.Text = C.Full ? "Install location" : "Your IGI 2 folder";
            sub.Text = C.Full ? "The game will be installed into this folder." : "Choose the folder of your GOG IGI 2 (the one with igi2.exe).";
            dirBox = new TextBox { Left = 0, Top = 20, Width = 320, Text = O.Dir };
            var br = new Button { Left = 330, Top = 18, Width = 85, Text = "Browse..." };
            br.Click += (s, e) =>
            {
                using (var f = new FolderBrowserDialog { SelectedPath = dirBox.Text, Description = sub.Text })
                    if (f.ShowDialog(this) == DialogResult.OK) dirBox.Text = C.Full && !U.IsGame(f.SelectedPath) && Directory.EnumerateFileSystemEntries(f.SelectedPath).Any()
                        ? Path.Combine(f.SelectedPath, "IGI 2 Operation Sandstorm") : f.SelectedPath;
            };
            body.Controls.Add(dirBox); body.Controls.Add(br);
            body.Controls.Add(new Label { Left = 0, Top = 60, Width = 415, Height = 60, ForeColor = Color.DimGray,
                Text = C.Full ? "Space needed: about " + (C.L("size") >> 20) + " MB." : "Every game file Setup changes is backed up first; uninstalling puts it back." });
        }
        else if (p == 2)
        {
            title.Text = "Options"; sub.Text = "Pick the picture setting (change it later with IGI2_Display_Setup.cmd in the game folder).";
            shortcut = new CheckBox { Left = 0, Top = 5, Width = 400, Text = "Create a desktop shortcut", Checked = O.Shortcut };
            var g = new GroupBox { Left = 0, Top = 40, Width = 415, Height = 130, Text = "Display" };
            rSharp = new RadioButton { Left = 12, Top = 22, Width = 390, Text = "Sharp - the full resolution of your screen (recommended)", Checked = O.Display == "sharp" };
            rLow = new RadioButton { Left = 12, Top = 55, Width = 390, Text = "Low-end PC - 1280x720, low detail, 60 fps cap", Checked = O.Display == "low" };
            rVery = new RadioButton { Left = 12, Top = 88, Width = 390, Text = "Very low - 960x540, low detail, 60 fps cap", Checked = O.Display == "verylow" };
            g.Controls.Add(rSharp); g.Controls.Add(rLow); g.Controls.Add(rVery);
            body.Controls.Add(shortcut); body.Controls.Add(g);
        }
        else if (p == 3)
        {
            title.Text = "Installing"; sub.Text = "Please wait while " + C.S("product") + " is installed.";
            bar = new ProgressBar { Left = 0, Top = 30, Width = 415, Height = 22, Maximum = 1000 };
            progLabel = new Label { Left = 0, Top = 60, Width = 415, Height = 40, ForeColor = Color.DimGray };
            body.Controls.Add(bar); body.Controls.Add(progLabel);
            back.Enabled = next.Enabled = false;
        }
        else
        {
            title.Text = "Finished"; sub.Text = C.S("product") + " is installed.";
            finishLabel = new Label { Left = 0, Top = 5, Width = 415, Height = 120,
                Text = "Start IGI 2 and choose Operation Sandstorm in the mission list.\n\nUninstall: Windows Settings > Apps > " + C.S("product") + ".\n\n" + C.S("made_by") + "   -   " + C.S("discord") };
            launch = new CheckBox { Left = 0, Top = 140, Width = 400, Text = "Launch IGI 2 now", Checked = true };
            body.Controls.Add(finishLabel); body.Controls.Add(launch);
        }
    }

    void Next()
    {
        if (page == 1)
        {
            O.Dir = dirBox.Text.Trim();
            var err = Installer.Check(C, O.Dir);
            if (err != null) { MessageBox.Show(this, err, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning); return; }
        }
        if (page == 2)
        {
            O.Shortcut = shortcut.Checked; O.Display = rLow.Checked ? "low" : rVery.Checked ? "verylow" : "sharp";
            Show(3); StartInstall(); return;
        }
        if (page == 4)
        {
            if (launch.Checked) try { Process.Start(new ProcessStartInfo(Path.Combine(O.Dir, "igi2.exe")) { WorkingDirectory = O.Dir }); } catch { }
            finished = true; Close(); return;
        }
        Show(page + 1);
    }

    void StartInstall()
    {
        installing = true;
        var t = new Thread(() =>
        {
            Exception err = null;
            try
            {
                Installer.Run(C, O, (f, s) => BeginInvoke((Action)(() => { bar.Value = Math.Max(0, Math.Min(1000, (int)(f * 1000))); progLabel.Text = s; })));
            }
            catch (Exception e) { err = e; }
            BeginInvoke((Action)(() =>
            {
                installing = false;
                if (err != null) { MessageBox.Show(this, "Setup failed: " + err.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error); Close(); }
                else Show(4);
            }));
        });
        t.IsBackground = true; t.Start();
    }

    public static void Shots(Payload c, string dir)
    {
        Directory.CreateDirectory(dir);
        var w = new Wizard(c);
        w.CreateControl(); w.Show();
        for (int p = 0; p <= 4; p++)
        {
            w.Show(p);
            if (p == 3) { w.bar.Value = 420; w.progLabel.Text = "MISSIONS\\multiplayer\\sandstorm_sp\\textures\\sandstorm.res"; }
            Application.DoEvents();
            using (var b = new Bitmap(w.Width, w.Height)) { w.DrawToBitmap(b, new Rectangle(0, 0, w.Width, w.Height)); b.Save(Path.Combine(dir, "page" + p + ".png")); }
        }
        w.installing = false; w.Close();
    }
}
