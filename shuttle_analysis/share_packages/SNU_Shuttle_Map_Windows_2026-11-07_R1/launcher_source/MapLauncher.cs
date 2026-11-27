using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("서울대 하교길 실험실 실행기")]
[assembly: AssemblyDescription("Read-only loopback launcher for the packaged shuttle simulation")]
[assembly: AssemblyVersion("2.0.0.0")]
[assembly: AssemblyFileVersion("2.0.0.0")]

namespace SnuShuttleMap
{
    internal static class Program
    {
        internal const string AppId = "SNU-Shuttle-Map-v2-20261107";
        internal static readonly string Root = Path.GetFullPath(AppDomain.CurrentDomain.BaseDirectory);
        internal static readonly string Key = Hash(Encoding.UTF8.GetBytes(Root.TrimEnd(Path.DirectorySeparatorChar).ToUpperInvariant())).Substring(0, 24);
        internal static readonly string StateDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SNUShuttleMap", Key);
        internal static readonly string StateFile = Path.Combine(StateDirectory, "instance.txt");
        internal static string Digest;
        internal static EventWaitHandle StopEvent;

        [STAThread]
        private static int Main(string[] args)
        {
            bool headless = Array.IndexOf(args, "--headless") >= 0;
            bool noBrowser = headless || Array.IndexOf(args, "--no-browser") >= 0;
            if (Array.IndexOf(args, "--stop") >= 0)
            {
                try { using (EventWaitHandle ev = EventWaitHandle.OpenExisting("Local\\SNUMapStop-" + Key)) { ev.Set(); } }
                catch (WaitHandleCannotBeOpenedException) { }
                return 0;
            }
            Directory.CreateDirectory(StateDirectory);
            bool owns = false;
            using (Mutex mutex = new Mutex(false, "Local\\SNUMap-" + Key))
            {
                LocalServer server = null;
                try
                {
                    try { owns = mutex.WaitOne(0); } catch (AbandonedMutexException) { owns = true; }
                    if (!owns)
                    {
                        for (int attempt = 0; attempt < 30; attempt++)
                        {
                            Dictionary<string, string> s = ReadState();
                            int port;
                            if (s.ContainsKey("port") && int.TryParse(s["port"], out port) && s.ContainsKey("digest") && Probe(port, s["digest"]))
                            {
                                if (!noBrowser) OpenBrowser("http://127.0.0.1:" + port + "/");
                                return 0;
                            }
                            Thread.Sleep(100);
                        }
                        throw new IOException("실행 중인 지도를 확인할 수 없습니다. 이전 실행기 창을 닫은 뒤 다시 실행해 주세요.");
                    }
                    Dictionary<string, string> assets = VerifyPackage();
                    Digest = Hash(File.ReadAllBytes(Path.Combine(Root, "assets.sha256")));
                    StopEvent = new EventWaitHandle(false, EventResetMode.ManualReset, "Local\\SNUMapStop-" + Key);
                    StopEvent.Reset();
                    server = new LocalServer(assets, Digest);
                    server.Start();
                    WriteState(server.Port);
                    Log("started port=" + server.Port + " headless=" + headless);
                    if (headless) StopEvent.WaitOne();
                    else
                    {
                        Application.EnableVisualStyles();
                        Application.SetCompatibleTextRenderingDefault(false);
                        Application.Run(new LauncherForm(server.Url, !noBrowser));
                    }
                    return 0;
                }
                catch (Exception e)
                {
                    Log("error " + e.ToString());
                    if (!headless) MessageBox.Show(e.Message, "하교길 실험실을 열지 못했습니다", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return 1;
                }
                finally
                {
                    if (owns)
                    {
                        if (server != null) server.Dispose();
                        Dictionary<string, string> s = ReadState();
                        if (s.ContainsKey("pid") && s["pid"] == Process.GetCurrentProcess().Id.ToString(CultureInfo.InvariantCulture))
                            try { File.Delete(StateFile); } catch (IOException) { }
                        if (StopEvent != null) StopEvent.Dispose();
                        mutex.ReleaseMutex();
                        Log("stopped");
                    }
                }
            }
        }

        internal static string Hash(byte[] bytes)
        {
            using (SHA256 hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
        }
        private static Dictionary<string, string> VerifyPackage()
        {
            string manifest = Path.Combine(Root, "assets.sha256");
            if (!File.Exists(manifest)) throw new IOException("ZIP 안에서 직접 실행하지 말고 전체 압축을 먼저 풀어 주세요. 실행기와 public 폴더가 같은 폴더에 있어야 합니다.");
            Dictionary<string, string> assets = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (string line in File.ReadAllLines(manifest, Encoding.UTF8))
            {
                if (String.IsNullOrWhiteSpace(line)) continue;
                if (line.Length < 68 || line.Substring(64, 2) != "  ") throw new IOException("파일 목록 형식이 올바르지 않습니다. ZIP을 다시 풀어 주세요.");
                string relative = line.Substring(66);
                if (!relative.StartsWith("public/", StringComparison.Ordinal) || relative.Contains("..") || relative.Contains("\\") || relative.Contains(":"))
                    throw new IOException("올바르지 않은 배포 파일 경로입니다.");
                string full = Path.GetFullPath(Path.Combine(Root, relative.Replace('/', Path.DirectorySeparatorChar)));
                if (!full.StartsWith(Root, StringComparison.OrdinalIgnoreCase) || !File.Exists(full) || Hash(File.ReadAllBytes(full)) != line.Substring(0, 64))
                    throw new IOException("자료가 누락되거나 변경되었습니다: " + relative + "\r\nZIP 전체를 새 폴더에 다시 풀어 주세요.");
                assets.Add(relative.Substring(7), full);
            }
            if (!assets.ContainsKey("index.html") || !assets.ContainsKey("data/capacity_v2/common.json.gz") || !assets.ContainsKey("data/capacity_v2/charts.json.gz"))
                throw new IOException("지도 자료를 찾지 못했습니다. public 폴더를 포함해 압축을 풀어 주세요.");
            return assets;
        }
        private static void WriteState(int port)
        {
            string[] lines = { "port=" + port, "pid=" + Process.GetCurrentProcess().Id, "digest=" + Digest, "app=" + AppId };
            string tmp = StateFile + ".tmp";
            File.WriteAllLines(tmp, lines, new UTF8Encoding(false));
            if (File.Exists(StateFile)) File.Delete(StateFile);
            File.Move(tmp, StateFile);
        }
        private static Dictionary<string, string> ReadState()
        {
            Dictionary<string, string> s = new Dictionary<string, string>();
            try
            {
                foreach (string line in File.ReadAllLines(StateFile, Encoding.UTF8))
                { int at = line.IndexOf('='); if (at > 0) s[line.Substring(0, at)] = line.Substring(at + 1); }
            }
            catch (IOException) { }
            return s;
        }
        private static bool Probe(int port, string digest)
        {
            if (port < 1024 || port > 65535) return false;
            try
            {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + "/__launcher/health");
                req.Proxy = null; req.Timeout = 400;
                using (WebResponse response = req.GetResponse())
                using (StreamReader reader = new StreamReader(response.GetResponseStream()))
                    return reader.ReadToEnd() == AppId + "\n" + digest;
            }
            catch (WebException) { return false; }
        }
        internal static void OpenBrowser(string url)
        {
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            Log("browser requested " + url);
        }
        internal static void Log(string message)
        {
            try { File.AppendAllText(Path.Combine(StateDirectory, "launcher.log"), DateTime.UtcNow.ToString("o") + " " + message + Environment.NewLine, Encoding.UTF8); }
            catch (IOException) { }
        }
    }

    internal sealed class LocalServer : IDisposable
    {
        private readonly Dictionary<string, string> assets;
        private readonly string digest;
        private TcpListener listener;
        private Thread thread;
        private volatile bool running;
        internal int Port { get; private set; }
        internal string Url { get { return "http://127.0.0.1:" + Port + "/"; } }
        internal LocalServer(Dictionary<string, string> assets, string digest) { this.assets = assets; this.digest = digest; }
        internal void Start()
        {
            listener = new TcpListener(IPAddress.Loopback, 0);
            listener.Start(); Port = ((IPEndPoint)listener.LocalEndpoint).Port;
            running = true; thread = new Thread(Accept); thread.IsBackground = true; thread.Start();
        }
        private void Accept()
        {
            while (running)
            {
                try { TcpClient client = listener.AcceptTcpClient(); ThreadPool.QueueUserWorkItem(delegate { Handle(client); }); }
                catch (SocketException) { if (running) Program.Log("listener closed unexpectedly"); }
                catch (ObjectDisposedException) { break; }
            }
        }
        private void Handle(TcpClient client)
        {
            using (client)
            {
                client.ReceiveTimeout = 15000; client.SendTimeout = 15000;
                try
                {
                    using (NetworkStream stream = client.GetStream())
                    {
                        StringBuilder header = new StringBuilder(); int value;
                        while ((value = stream.ReadByte()) >= 0 && header.Length < 16384)
                        {
                            header.Append((char)value);
                            if (header.Length >= 4 && header.ToString(header.Length - 4, 4) == "\r\n\r\n") break;
                        }
                        string[] lines = header.ToString().Split(new[] { "\r\n" }, StringSplitOptions.None);
                        string[] request = lines[0].Split(' ');
                        if (request.Length != 3 || header.Length >= 16384) { Reply(stream, 400, "Bad request", false); return; }
                        bool head = request[0] == "HEAD";
                        if (request[0] != "GET" && !head) { Reply(stream, 405, "Read-only server", false); return; }
                        Dictionary<string, string> headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                        foreach (string line in lines) { int split = line.IndexOf(':'); if (split > 0) headers[line.Substring(0, split)] = line.Substring(split + 1).Trim(); }
                        string host;
                        if (!headers.TryGetValue("Host", out host) || (host != "127.0.0.1:" + Port && host != "localhost:" + Port)) { Reply(stream, 403, "Local host only", head); return; }
                        string path = Uri.UnescapeDataString(request[1].Split('?')[0]);
                        if (!path.StartsWith("/", StringComparison.Ordinal) || path.StartsWith("//", StringComparison.Ordinal) || path.Contains("\\") || path.Contains(":") || path.Contains("\0")) { Reply(stream, 403, "Invalid path", head); return; }
                        foreach (string part in path.Split('/')) if (part == "." || part == "..") { Reply(stream, 403, "Invalid path", head); return; }
                        if (path == "/__launcher/health") { Send(stream, 200, Encoding.UTF8.GetBytes(Program.AppId + "\n" + digest), "text/plain; charset=utf-8", false, head); return; }
                        string relative = path == "/" ? "index.html" : path.Substring(1), file;
                        bool compressedJson = false;
                        if (!assets.TryGetValue(relative, out file))
                        {
                            if (!relative.EndsWith(".json", StringComparison.OrdinalIgnoreCase) || !assets.TryGetValue(relative + ".gz", out file)) { Reply(stream, 404, "Not found", head); return; }
                            compressedJson = true;
                        }
                        byte[] bytes = File.ReadAllBytes(file);
                        string accept;
                        bool gzip = compressedJson && headers.TryGetValue("Accept-Encoding", out accept) && AcceptsGzip(accept);
                        if (compressedJson && !gzip)
                            using (MemoryStream input = new MemoryStream(bytes))
                            using (GZipStream decompressor = new GZipStream(input, CompressionMode.Decompress))
                            using (MemoryStream output = new MemoryStream()) { decompressor.CopyTo(output); bytes = output.ToArray(); }
                        Send(stream, 200, bytes, Mime(relative), gzip, head);
                    }
                }
                catch (IOException) { }
                catch (SocketException) { }
                catch (UriFormatException) { }
            }
        }
        private static bool AcceptsGzip(string header)
        {
            foreach (string item in header.Split(','))
            {
                string[] parts = item.Trim().Split(';');
                if (!parts[0].Trim().Equals("gzip", StringComparison.OrdinalIgnoreCase)) continue;
                double quality = 1;
                foreach (string parameter in parts)
                    if (parameter.Trim().StartsWith("q=", StringComparison.OrdinalIgnoreCase))
                        double.TryParse(parameter.Trim().Substring(2), NumberStyles.Float, CultureInfo.InvariantCulture, out quality);
                return quality > 0;
            }
            return false;
        }
        private static string Mime(string path)
        {
            switch (Path.GetExtension(path).ToLowerInvariant())
            {
                case ".html": return "text/html; charset=utf-8";
                case ".js": return "text/javascript; charset=utf-8";
                case ".css": return "text/css; charset=utf-8";
                case ".json": return "application/json; charset=utf-8";
                case ".png": return "image/png";
                case ".svg": return "image/svg+xml";
                case ".ico": return "image/x-icon";
                case ".gz": return "application/gzip";
                default: return "text/plain; charset=utf-8";
            }
        }
        private static void Reply(Stream stream, int code, string text, bool head)
        { Send(stream, code, Encoding.UTF8.GetBytes(text), "text/plain; charset=utf-8", false, head); }
        private static void Send(Stream stream, int code, byte[] body, string type, bool gzip, bool head)
        {
            string status = code == 200 ? "OK" : code == 403 ? "Forbidden" : code == 404 ? "Not Found" : code == 405 ? "Method Not Allowed" : "Bad Request";
            string header = "HTTP/1.1 " + code + " " + status + "\r\nContent-Type: " + type + "\r\nContent-Length: " + body.Length + "\r\nConnection: close\r\nCache-Control: no-cache\r\nX-Content-Type-Options: nosniff\r\nVary: Accept-Encoding\r\n";
            if (gzip) header += "Content-Encoding: gzip\r\n";
            if (code == 405) header += "Allow: GET, HEAD\r\n";
            byte[] bytes = Encoding.ASCII.GetBytes(header + "\r\n");
            stream.Write(bytes, 0, bytes.Length); if (!head) stream.Write(body, 0, body.Length);
        }
        public void Dispose() { running = false; if (listener != null) listener.Stop(); if (thread != null) thread.Join(1000); }
    }

    internal sealed class LauncherForm : Form
    {
        internal LauncherForm(string url, bool autoOpen)
        {
            Text = "서울대 하교길 실험실 실행기";
            ClientSize = new Size(550, 285); MinimumSize = new Size(520, 320);
            StartPosition = FormStartPosition.CenterScreen; AutoScaleMode = AutoScaleMode.Font;
            Font = new Font("맑은 고딕", 10F); BackColor = Color.FromArgb(248, 250, 245);
            Color green = Color.FromArgb(27, 90, 80);
            Label title = new Label { Text = "하교길 실험실이 실행 중입니다", AutoSize = true, Font = new Font(Font.FontFamily, 17F, FontStyle.Bold), ForeColor = green, Location = new Point(27, 25) };
            Label description = new Label { Text = "브라우저에서 요일·시간·배차를 선택해 보세요.\r\n이 창을 닫으면 지도 서버도 종료됩니다.", Location = new Point(29, 74), AutoSize = true, ForeColor = Color.FromArgb(75, 101, 89) };
            LinkLabel address = new LinkLabel { Text = url, AutoSize = true, Location = new Point(29, 132), LinkColor = green };
            Button open = new Button { Text = "지도 다시 열기", Size = new Size(180, 44), Location = new Point(29, 172), BackColor = green, ForeColor = Color.White, FlatStyle = FlatStyle.Flat };
            open.FlatAppearance.BorderSize = 0;
            Button close = new Button { Text = "종료", Size = new Size(95, 44), Location = new Point(220, 172), BackColor = Color.White, FlatStyle = FlatStyle.Flat };
            Label note = new Label { Text = "별도 설치 없음 · 배경 지도는 인터넷 연결 필요", AutoSize = true, ForeColor = Color.FromArgb(107, 124, 110), Location = new Point(29, 240), Font = new Font(Font.FontFamily, 9F) };
            Action openBrowser = delegate
            {
                try { Program.OpenBrowser(url); }
                catch (Exception) { MessageBox.Show("브라우저를 열지 못했습니다. 아래 주소를 브라우저 주소창에 입력해 주세요.\r\n" + url, "지도 주소", MessageBoxButtons.OK, MessageBoxIcon.Information); }
            };
            open.Click += delegate { openBrowser(); }; address.LinkClicked += delegate { openBrowser(); }; close.Click += delegate { Close(); };
            Controls.AddRange(new Control[] { title, description, address, open, close, note });
            Shown += delegate { if (autoOpen) openBrowser(); };
            FormClosed += delegate { Program.StopEvent.Set(); };
            System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer { Interval = 400 };
            timer.Tick += delegate { if (Program.StopEvent.WaitOne(0)) Close(); };
            timer.Start(); Disposed += delegate { timer.Dispose(); };
        }
    }
}
