using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace MiMotion.SportHost
{
    internal sealed class Options
    {
        internal IntPtr Parent;
        internal string Project;
        internal string StatusFile;
        internal string QuitFile;
        internal string ExportDir;
        internal string SelfTest;
        internal string InspectReport;

        internal static Options Parse(string[] arguments)
        {
            var result = new Options();
            for (int index = 0; index < arguments.Length; index++)
            {
                string argument = arguments[index];
                if (index + 1 >= arguments.Length) throw new ArgumentException("参数缺少对应值：" + argument);
                string value = arguments[++index];
                switch (argument)
                {
                    case "--parent": result.Parent = new IntPtr(long.Parse(value)); break;
                    case "--project": result.Project = Path.GetFullPath(value); break;
                    case "--status-file": result.StatusFile = Path.GetFullPath(value); break;
                    case "--quit-file": result.QuitFile = Path.GetFullPath(value); break;
                    case "--export-dir": result.ExportDir = Path.GetFullPath(value); break;
                    case "--self-test": result.SelfTest = Path.GetFullPath(value); break;
                    case "--inspect-report": result.InspectReport = Path.GetFullPath(value); break;
                    default: throw new ArgumentException("未知参数：" + argument);
                }
            }
            if (String.IsNullOrEmpty(result.Project))
                result.Project = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "data");
            return result;
        }
    }

    internal static class Native
    {
        internal const int GWL_STYLE = -16;
        internal const long WS_CHILD = 0x40000000L;
        internal const long WS_POPUP = 0x80000000L;
        internal const long WS_CAPTION = 0x00C00000L;
        internal const long WS_THICKFRAME = 0x00040000L;
        internal const uint SWP_FRAMECHANGED = 0x0020;
        internal const uint SWP_NOACTIVATE = 0x0010;
        internal const uint SWP_NOZORDER = 0x0004;
        [StructLayout(LayoutKind.Sequential)]
        internal struct RECT { internal int Left, Top, Right, Bottom; }
        [DllImport("user32.dll")] internal static extern bool IsWindow(IntPtr hwnd);
        [DllImport("user32.dll")] internal static extern bool IsWindowVisible(IntPtr hwnd);
        [DllImport("user32.dll")] internal static extern IntPtr GetParent(IntPtr hwnd);
        [DllImport("user32.dll", SetLastError = true)] internal static extern IntPtr SetParent(IntPtr child, IntPtr parent);
        [DllImport("user32.dll")] internal static extern bool GetClientRect(IntPtr hwnd, out RECT rect);
        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] internal static extern IntPtr GetWindowLongPtr(IntPtr hwnd, int index);
        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] internal static extern IntPtr SetWindowLongPtr(IntPtr hwnd, int index, IntPtr value);
        [DllImport("user32.dll")] internal static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int width, int height, uint flags);
        [DllImport("user32.dll")] internal static extern IntPtr GetWindowDpiAwarenessContext(IntPtr hwnd);
        [DllImport("user32.dll")] internal static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
        [DllImport("shcore.dll")] internal static extern int SetProcessDpiAwareness(int value);

        internal static void MatchDpi(IntPtr parent)
        {
            try
            {
                if (parent != IntPtr.Zero)
                {
                    IntPtr context = GetWindowDpiAwarenessContext(parent);
                    if (context != IntPtr.Zero) { SetThreadDpiAwarenessContext(context); return; }
                }
                SetProcessDpiAwareness(2);
            }
            catch (EntryPointNotFoundException) { }
            catch (DllNotFoundException) { }
        }
    }

    internal static class JsonFile
    {
        private static readonly JavaScriptSerializer Serializer = new JavaScriptSerializer();
        internal static void Write(string path, object value)
        {
            if (String.IsNullOrEmpty(path)) return;
            string folder = Path.GetDirectoryName(path);
            if (!String.IsNullOrEmpty(folder)) Directory.CreateDirectory(folder);
            string temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                File.WriteAllText(temp, Serializer.Serialize(value), new UTF8Encoding(false));
                if (File.Exists(path)) File.Replace(temp, path, null);
                else File.Move(temp, path);
            }
            finally { if (File.Exists(temp)) File.Delete(temp); }
        }
        internal static Dictionary<string, object> Read(string path)
        {
            return Serializer.Deserialize<Dictionary<string, object>>(File.ReadAllText(path, Encoding.UTF8));
        }
        internal static Dictionary<string, object> Parse(string text)
        {
            return Serializer.Deserialize<Dictionary<string, object>>(text);
        }
    }

    internal sealed class QuietPopup : Form
    {
        protected override bool ShowWithoutActivation { get { return true; } }
        internal QuietPopup()
        {
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            Size = new Size(2, 2);
            Opacity = 0;
            StartPosition = FormStartPosition.Manual;
            Location = new Point(-10000, -10000);
        }
    }

    internal sealed class HostForm : Form
    {
        internal const string SiteUrl = "https://sport.gyvv.top/";
        private readonly Options options;
        private WebView2 browser;
        private readonly Label status;
        private readonly Label failure;
        private readonly FlowLayoutPanel tools;
        private readonly Timer timer;
        private readonly List<Dictionary<string, object>> downloads = new List<Dictionary<string, object>>();
        private readonly HashSet<string> reserved = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private readonly List<Form> popups = new List<Form>();
        private readonly string profileDirectory;
        private readonly string preferenceFile;
        private string exportDirectory;
        private string state = "loading";
        private string message = "正在连接运动轨迹网站…";
        private string runtime = "";
        private CoreWebView2Environment environment;
        private bool initializing;
        private bool closing;
        private bool inspectionStarted;
        private bool recreateBrowser;
        private bool testJsPassed;
        private bool testDownloadPassed;
        private object testPriorStorage;
        private DateTime started = DateTime.UtcNow;
        private int previousWidth = -1;
        private int previousHeight = -1;

        internal HostForm(Options value)
        {
            options = value;
            string local = Path.Combine(options.Project, ".mimotion-desktop");
            profileDirectory = Path.Combine(local, "sport-web-profile");
            preferenceFile = Path.Combine(local, "sport-settings.json");
            exportDirectory = Path.Combine(options.Project, "轨迹导出");
            if (String.IsNullOrEmpty(options.ExportDir) && File.Exists(preferenceFile))
            {
                try
                {
                    Dictionary<string, object> preference = JsonFile.Read(preferenceFile);
                    if (preference.ContainsKey("export_dir"))
                        exportDirectory = Path.GetFullPath(Convert.ToString(preference["export_dir"]));
                }
                catch (Exception) { }
            }
            if (!String.IsNullOrEmpty(options.ExportDir)) exportDirectory = options.ExportDir;
            Directory.CreateDirectory(local);
            Directory.CreateDirectory(exportDirectory);
            Text = "MiMotion · 运动轨迹" + (!String.IsNullOrEmpty(options.SelfTest) ? " · 离线检查" : "");
            Font = new Font("Microsoft YaHei UI", 9F);
            AutoScaleMode = AutoScaleMode.None;
            BackColor = Color.White;
            ClientSize = new Size(1150, 760);
            MinimumSize = options.Parent == IntPtr.Zero ? new Size(700, 450) : Size.Empty;
            StartPosition = FormStartPosition.CenterScreen;
            if (options.Parent != IntPtr.Zero)
            {
                FormBorderStyle = FormBorderStyle.None;
                ShowInTaskbar = false;
                StartPosition = FormStartPosition.Manual;
                Location = Point.Empty;
            }
            tools = new FlowLayoutPanel();
            tools.Dock = DockStyle.Top;
            tools.Height = 43;
            tools.Padding = new Padding(7, 5, 0, 4);
            tools.BackColor = Color.FromArgb(238, 243, 233);
            tools.WrapContents = false;
            tools.AutoScroll = true;
            tools.Controls.Add(MakeButton("后退", delegate { if (browser.CoreWebView2 != null && browser.CanGoBack) browser.GoBack(); }));
            tools.Controls.Add(MakeButton("刷新", delegate { Retry(); }));
            tools.Controls.Add(MakeButton("网站首页", delegate { if (browser.CoreWebView2 != null) browser.CoreWebView2.Navigate(SiteUrl); else Retry(); }));
            tools.Controls.Add(MakeButton("导出文件夹", delegate { OpenExportFolder(); }));
            tools.Controls.Add(MakeButton("保存位置", delegate { ChooseExportFolder(); }));
            tools.Controls.Add(MakeButton("浏览器打开", delegate { OpenExternal(SiteUrl); }));
            var attribution = new Label();
            attribution.AutoSize = true;
            attribution.ForeColor = Color.FromArgb(90, 111, 98);
            attribution.Text = "sport.gyvv.top · 在线工具";
            attribution.Padding = new Padding(10, 5, 5, 0);
            tools.Controls.Add(attribution);
            status = new Label();
            status.Dock = DockStyle.Bottom;
            status.Height = 28;
            status.Padding = new Padding(9, 4, 8, 2);
            status.BackColor = Color.FromArgb(244, 246, 241);
            status.ForeColor = Color.FromArgb(32, 54, 48);
            status.AutoEllipsis = true;
            status.Text = message;
            failure = new Label();
            failure.Dock = DockStyle.Top;
            failure.Height = 63;
            failure.Padding = new Padding(12, 8, 12, 6);
            failure.BackColor = Color.FromArgb(251, 240, 234);
            failure.ForeColor = Color.FromArgb(145, 59, 46);
            failure.Visible = false;
            browser = new WebView2();
            browser.Dock = DockStyle.Fill;
            browser.DefaultBackgroundColor = Color.White;
            Controls.Add(browser);
            Controls.Add(failure);
            Controls.Add(tools);
            Controls.Add(status);
            timer = new Timer();
            timer.Interval = 200;
            timer.Tick += OnTimer;
            Shown += async delegate
            {
                try { AttachParent(); if (!closing) await Initialize(); }
                catch (Exception exception)
                {
                    ShowError("运动轨迹页面暂时无法嵌入，请重新打开此模块。", exception.Message);
                    if (!String.IsNullOrEmpty(options.SelfTest)) WriteSelfTest(false, exception.Message);
                    Close();
                }
            };
            FormClosing += delegate { closing = true; timer.Stop(); };
            FormClosed += delegate
            {
                foreach (Form popup in popups.ToArray()) { try { popup.Close(); } catch (Exception) { } }
                browser.Dispose();
            };
            timer.Start();
        }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams result = base.CreateParams;
                if (options != null && options.Parent != IntPtr.Zero)
                {
                    result.Parent = options.Parent;
                    result.Style = (int)(((long)result.Style | Native.WS_CHILD) & ~Native.WS_POPUP & ~Native.WS_CAPTION & ~Native.WS_THICKFRAME);
                    result.ExStyle &= ~0x00040000; // WS_EX_APPWINDOW
                }
                return result;
            }
        }

        private Button MakeButton(string caption, Action action)
        {
            var button = new Button();
            button.Text = caption;
            button.AutoSize = true;
            button.Height = 30;
            button.MinimumSize = new Size(58, 29);
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderColor = Color.FromArgb(218, 227, 211);
            button.BackColor = Color.FromArgb(247, 250, 244);
            button.ForeColor = Color.FromArgb(32, 54, 48);
            button.Margin = new Padding(0, 0, 6, 0);
            button.Click += delegate { action(); };
            return button;
        }

        private void AttachParent()
        {
            if (options.Parent == IntPtr.Zero) return;
            if (!Native.IsWindow(options.Parent)) { Close(); return; }
            Native.SetParent(Handle, options.Parent);
            long style = Native.GetWindowLongPtr(Handle, Native.GWL_STYLE).ToInt64();
            Native.SetWindowLongPtr(Handle, Native.GWL_STYLE,
                new IntPtr((style | Native.WS_CHILD) & ~Native.WS_POPUP & ~Native.WS_CAPTION & ~Native.WS_THICKFRAME));
            if (Native.GetParent(Handle) != options.Parent)
                throw new InvalidOperationException("无法把运动轨迹页面嵌入主窗口。请重新打开该模块。");
            ResizeToParent();
        }

        private void ResizeToParent()
        {
            if (options.Parent == IntPtr.Zero || closing) return;
            Native.RECT rectangle;
            if (!Native.GetClientRect(options.Parent, out rectangle)) return;
            int width = Math.Max(1, rectangle.Right - rectangle.Left);
            int height = Math.Max(1, rectangle.Bottom - rectangle.Top);
            if (width != previousWidth || height != previousHeight)
            {
                Native.SetWindowPos(Handle, IntPtr.Zero, 0, 0, width, height,
                    Native.SWP_NOACTIVATE | Native.SWP_NOZORDER | Native.SWP_FRAMECHANGED);
                previousWidth = width;
                previousHeight = height;
            }
            // Native child visibility follows the Tk parent; never force focus or show an orphan window.
        }

        private void OnTimer(object sender, EventArgs arguments)
        {
            if (closing) return;
            if ((!String.IsNullOrEmpty(options.QuitFile) && File.Exists(options.QuitFile)) ||
                (options.Parent != IntPtr.Zero && !Native.IsWindow(options.Parent)))
            {
                Close();
                return;
            }
            ResizeToParent();
            if (!String.IsNullOrEmpty(options.SelfTest) && (DateTime.UtcNow - started).TotalSeconds > 45)
            {
                WriteSelfTest(false, "离线检查等待超时。");
                Close();
            }
        }

        private async Task Initialize()
        {
            if (initializing || closing) return;
            initializing = true;
            failure.Visible = false;
            SetState("loading", "正在加载运动轨迹网站…");
            try
            {
                runtime = CoreWebView2Environment.GetAvailableBrowserVersionString();
                environment = await CoreWebView2Environment.CreateAsync(null, profileDirectory, null);
                await browser.EnsureCoreWebView2Async(environment);
                if (closing) return;
                ConfigureBrowser(browser, null);
                browser.CoreWebView2.NavigationStarting += OnNavigationStarting;
                browser.CoreWebView2.NavigationCompleted += OnNavigationCompleted;
                browser.CoreWebView2.DocumentTitleChanged += delegate { WriteStatus(); };
                browser.CoreWebView2.ProcessFailed += delegate(object sender, CoreWebView2ProcessFailedEventArgs args)
                {
                    recreateBrowser = true;
                    ShowError("网页进程已停止。可点击“刷新”重试。", args.ProcessFailedKind.ToString());
                };
                if (!String.IsNullOrEmpty(options.SelfTest)) NavigateSelfTest();
                else browser.CoreWebView2.Navigate(SiteUrl);
            }
            catch (WebView2RuntimeNotFoundException)
            {
                if (closing) return;
                ShowError("当前电脑缺少 Microsoft Edge WebView2 运行环境。可用“浏览器打开”继续访问网站，或安装微软 WebView2 后重试。", "runtime_missing");
                if (!String.IsNullOrEmpty(options.SelfTest)) { WriteSelfTest(false, "runtime_missing"); Close(); }
            }
            catch (Exception exception)
            {
                if (closing) return;
                ShowError("页面暂时无法打开，可点击“刷新”重试。", exception.Message);
                if (!String.IsNullOrEmpty(options.SelfTest)) { WriteSelfTest(false, exception.Message); Close(); }
            }
            finally { initializing = false; }
        }

        private void ConfigureBrowser(WebView2 view, Form popup)
        {
            CoreWebView2 core = view.CoreWebView2;
            core.Settings.AreHostObjectsAllowed = false;
            core.Settings.IsWebMessageEnabled = false;
            core.Settings.IsStatusBarEnabled = false;
            core.Settings.AreDefaultContextMenusEnabled = true;
            core.DownloadStarting += delegate(object sender, CoreWebView2DownloadStartingEventArgs args) { OnDownload(args, popup); };
            core.NewWindowRequested += async delegate(object sender, CoreWebView2NewWindowRequestedEventArgs args)
            {
                await OnNewWindow(args);
            };
            core.PermissionRequested += delegate(object sender, CoreWebView2PermissionRequestedEventArgs args)
            {
                if (args.PermissionKind == CoreWebView2PermissionKind.Geolocation)
                {
                    args.State = MessageBox.Show(this, "运动轨迹网站请求获取当前位置，用于地图定位。是否允许本次定位？", "地图定位",
                        MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes ? CoreWebView2PermissionState.Allow : CoreWebView2PermissionState.Deny;
                    args.SavesInProfile = false;
                }
            };
        }

        private static bool IsSite(string url)
        {
            Uri parsed;
            return Uri.TryCreate(url, UriKind.Absolute, out parsed) && parsed.Scheme == "https" &&
                String.Equals(parsed.Host, "sport.gyvv.top", StringComparison.OrdinalIgnoreCase);
        }

        private bool IsTest(string url)
        {
            return !String.IsNullOrEmpty(options.SelfTest) && url.StartsWith("https://mimotion-test.invalid/", StringComparison.OrdinalIgnoreCase);
        }

        private void OnNavigationStarting(object sender, CoreWebView2NavigationStartingEventArgs args)
        {
            if (!IsSite(args.Uri) && !IsTest(args.Uri) && args.Uri != "about:blank" &&
                !args.Uri.StartsWith("blob:https://sport.gyvv.top/", StringComparison.OrdinalIgnoreCase))
            {
                args.Cancel = true;
                SetState("ready", "外部链接可通过“浏览器打开”访问；当前保留运动轨迹页面。");
                return;
            }
            SetState("loading", "正在加载网页…");
        }

        private async void OnNavigationCompleted(object sender, CoreWebView2NavigationCompletedEventArgs args)
        {
            if (closing) return;
            if (!args.IsSuccess)
            {
                ShowError("网站暂时无法连接。检查网络后点击“刷新”，或在浏览器中打开。", args.WebErrorStatus.ToString());
                return;
            }
            failure.Visible = false;
            SetState("ready", "网站已载入 · 导出文件保存在：" + exportDirectory);
            if (!String.IsNullOrEmpty(options.SelfTest))
            {
                try
                {
                    string json = await browser.CoreWebView2.ExecuteScriptAsync("({js:1+1===2,storage:localStorage.getItem('mimotion_self_test'),prior:window.priorStorage,secure:isSecureContext})");
                    Dictionary<string, object> data = JsonFile.Parse(json);
                    testJsPassed = Convert.ToBoolean(data["js"]) && Convert.ToString(data["storage"]) == "persistent-ok";
                    testPriorStorage = data.ContainsKey("prior") ? data["prior"] : null;
                    CompleteSelfTest();
                }
                catch (Exception exception) { WriteSelfTest(false, exception.Message); Close(); }
            }
            if (!String.IsNullOrEmpty(options.InspectReport) && !inspectionStarted)
            {
                inspectionStarted = true;
                try
                {
                    await Task.Delay(10000);
                    if (closing || browser.CoreWebView2 == null) return;
                    string json = await browser.CoreWebView2.ExecuteScriptAsync(
                        "({title:document.title,readyState:document.readyState,secure:isSecureContext," +
                        "map:!!document.querySelector('.leaflet-container'),leaflet:typeof window.L!== 'undefined'," +
                        "tiles:document.querySelectorAll('img.leaflet-tile').length," +
                        "loadedTiles:Array.from(document.querySelectorAll('img.leaflet-tile')).filter(x=>x.complete&&x.naturalWidth>0).length," +
                        "bodyText:(document.body?document.body.innerText:'').slice(0,1000)})");
                    Dictionary<string, object> report = JsonFile.Parse(json);
                    report["source"] = SafeSource();
                    report["runtime"] = runtime;
                    report["embedded"] = options.Parent != IntPtr.Zero;
                    report["host_hwnd"] = Handle.ToInt64();
                    string screenshot = Path.ChangeExtension(options.InspectReport, ".png");
                    try
                    {
                        using (var stream = new FileStream(screenshot, FileMode.Create, FileAccess.Write, FileShare.Read))
                            await browser.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream);
                        report["screenshot"] = screenshot;
                    }
                    catch (Exception exception) { report["screenshot_error"] = exception.Message; }
                    JsonFile.Write(options.InspectReport, report);
                }
                catch (Exception exception)
                {
                    JsonFile.Write(options.InspectReport, new { error = exception.Message, source = SafeSource() });
                }
            }
        }

        private async Task OnNewWindow(CoreWebView2NewWindowRequestedEventArgs args)
        {
            string url = args.Uri;
            if (IsSite(url))
            {
                args.Handled = true;
                browser.CoreWebView2.Navigate(url);
                return;
            }
            if (url.StartsWith("blob:https://sport.gyvv.top/", StringComparison.OrdinalIgnoreCase) ||
                (IsTest(browser.CoreWebView2.Source) && url.StartsWith("blob:https://mimotion-test.invalid/", StringComparison.OrdinalIgnoreCase)))
            {
                CoreWebView2Deferral deferral = args.GetDeferral();
                try
                {
                    var popup = new QuietPopup();
                    var view = new WebView2();
                    view.Dock = DockStyle.Fill;
                    popup.Controls.Add(view);
                    popups.Add(popup);
                    popup.FormClosed += delegate { popups.Remove(popup); view.Dispose(); };
                    popup.Show();
                    await view.EnsureCoreWebView2Async(environment);
                    ConfigureBrowser(view, popup);
                    args.NewWindow = view.CoreWebView2;
                    args.Handled = true;
                    var closeTimer = new Timer();
                    closeTimer.Interval = 30000;
                    closeTimer.Tick += delegate { closeTimer.Stop(); closeTimer.Dispose(); if (!popup.IsDisposed) popup.Close(); };
                    closeTimer.Start();
                }
                catch (Exception exception) { args.Handled = true; SetState("error", "无法打开下载窗口：" + exception.Message); }
                finally { deferral.Complete(); }
                return;
            }
            args.Handled = true;
            Uri parsed;
            if (args.IsUserInitiated && Uri.TryCreate(url, UriKind.Absolute, out parsed) && parsed.Scheme == "https") OpenExternal(url);
        }

        private string UniqueExportPath(string suggested)
        {
            string file = Path.GetFileName(suggested ?? "");
            foreach (char invalid in Path.GetInvalidFileNameChars()) file = file.Replace(invalid, '_');
            file = file.Trim().TrimEnd('.');
            if (String.IsNullOrEmpty(file)) file = "运动轨迹-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".dat";
            string deviceStem = Path.GetFileNameWithoutExtension(file).TrimEnd(' ', '.');
            if (Regex.IsMatch(deviceStem, @"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$", RegexOptions.IgnoreCase)) file = "_" + file;
            // Bound path component size without accepting directory traversal from response filenames.
            if (file.Length > 180) file = file.Substring(0, 160) + Path.GetExtension(file).Substring(0, Math.Min(16, Path.GetExtension(file).Length));
            Directory.CreateDirectory(exportDirectory);
            string stem = Path.GetFileNameWithoutExtension(file);
            string extension = Path.GetExtension(file);
            string full = Path.Combine(exportDirectory, file);
            int index = 1;
            while (File.Exists(full) || reserved.Contains(full)) full = Path.Combine(exportDirectory, stem + " (" + index++ + ")" + extension);
            reserved.Add(full);
            return full;
        }

        private void OnDownload(CoreWebView2DownloadStartingEventArgs args, Form popup)
        {
            try
            {
                string path = UniqueExportPath(args.ResultFilePath);
                args.ResultFilePath = path;
                args.Handled = true;
                CoreWebView2DownloadOperation operation = args.DownloadOperation;
                var item = new Dictionary<string, object>();
                item["name"] = Path.GetFileName(path);
                item["state"] = "downloading";
                downloads.Add(item);
                SetState("ready", "正在保存：" + Path.GetFileName(path));
                operation.StateChanged += delegate
                {
                    if (closing) return;
                    if (operation.State == CoreWebView2DownloadState.Completed)
                    {
                        item["state"] = "completed";
                        SetState("ready", "已保存：" + path);
                        if (!String.IsNullOrEmpty(options.SelfTest))
                        {
                            try { testDownloadPassed = File.ReadAllText(path, Encoding.UTF8).Contains("mimotion-offline-export"); }
                            catch (IOException) { testDownloadPassed = false; }
                            CompleteSelfTest();
                        }
                        if (popup != null && !popup.IsDisposed) popup.Close();
                    }
                    else if (operation.State == CoreWebView2DownloadState.Interrupted)
                    {
                        item["state"] = "interrupted";
                        item["reason"] = operation.InterruptReason.ToString();
                        SetState("error", "文件未保存完成，请重新导出。");
                        if (popup != null && !popup.IsDisposed) popup.Close();
                    }
                };
            }
            catch (Exception exception)
            {
                args.Cancel = true;
                SetState("error", "无法保存导出文件：" + exception.Message);
            }
        }

        private async void Retry()
        {
            if (initializing || closing) return;
            failure.Visible = false;
            try
            {
                if (!recreateBrowser && browser.CoreWebView2 != null)
                {
                    SetState("loading", "正在刷新…");
                    browser.Reload();
                    return;
                }
            }
            catch (Exception) { recreateBrowser = true; }
            if (recreateBrowser)
            {
                Controls.Remove(browser);
                browser.Dispose();
                browser = new WebView2();
                browser.Dock = DockStyle.Fill;
                browser.DefaultBackgroundColor = Color.White;
                Controls.Add(browser);
                browser.SendToBack();
                recreateBrowser = false;
            }
            await Initialize();
        }

        private void OpenExportFolder()
        {
            try { Directory.CreateDirectory(exportDirectory); Process.Start(new ProcessStartInfo(exportDirectory) { UseShellExecute = true }); }
            catch (Exception exception) { SetState("error", "文件夹暂时无法打开：" + exception.Message); }
        }

        private void ChooseExportFolder()
        {
            using (var dialog = new FolderBrowserDialog())
            {
                dialog.Description = "选择运动轨迹文件的保存位置";
                dialog.SelectedPath = exportDirectory;
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                exportDirectory = Path.GetFullPath(dialog.SelectedPath);
                JsonFile.Write(preferenceFile, new { export_dir = exportDirectory });
                SetState("ready", "导出文件将保存在：" + exportDirectory);
            }
        }

        private static void OpenExternal(string url)
        {
            Uri parsed;
            if (!Uri.TryCreate(url, UriKind.Absolute, out parsed) || parsed.Scheme != "https") return;
            try { Process.Start(new ProcessStartInfo(url) { UseShellExecute = true }); }
            catch (Exception) { }
        }

        private string SafeSource()
        {
            try
            {
                if (browser.CoreWebView2 == null) return SiteUrl;
                string value = browser.CoreWebView2.Source;
                if (value.StartsWith("blob:", StringComparison.OrdinalIgnoreCase)) return "blob:download";
                Uri uri;
                return Uri.TryCreate(value, UriKind.Absolute, out uri) ? uri.GetLeftPart(UriPartial.Path) : "";
            }
            catch (Exception) { return SiteUrl; }
        }

        private void SetState(string value, string text)
        {
            state = value;
            message = text;
            status.Text = text;
            WriteStatus();
        }

        private void ShowError(string text, string detail)
        {
            failure.Text = text;
            failure.Visible = true;
            SetState("error", text);
            // Details stay in the status report, never in page JavaScript or an account log.
            WriteStatus(detail);
        }

        private void WriteStatus(string detail = null)
        {
            try
            {
                string title = browser.CoreWebView2 == null ? "" : browser.CoreWebView2.DocumentTitle;
                JsonFile.Write(options.StatusFile, new
                {
                    state = state, hwnd = IsHandleCreated ? Handle.ToInt64() : 0,
                    title = title, source = SafeSource(), message = message, export_dir = exportDirectory,
                    downloads = downloads.TakeLastCompat(20).ToArray(), runtime = runtime,
                    detail = detail, embedded = options.Parent != IntPtr.Zero,
                    updated_utc = DateTime.UtcNow.ToString("o")
                });
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }

        private void NavigateSelfTest()
        {
            string folder = Path.Combine(options.Project, ".mimotion-desktop", "sport-self-test");
            Directory.CreateDirectory(folder);
            string html = "<!doctype html><meta charset='utf-8'><title>MiMotion offline WebView check</title>" +
                "<h1>MiMotion offline WebView check</h1><p>No external requests.</p><script>" +
                "window.priorStorage=localStorage.getItem('mimotion_self_test');localStorage.setItem('mimotion_self_test','persistent-ok');" +
                "setTimeout(function(){var a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['mimotion-offline-export,ok\\n'],{type:'text/csv'}));" +
                "a.download='mimotion-offline-export.csv';document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href)},2000)},500);</script>";
            File.WriteAllText(Path.Combine(folder, "index.html"), html, new UTF8Encoding(false));
            browser.CoreWebView2.SetVirtualHostNameToFolderMapping("mimotion-test.invalid", folder, CoreWebView2HostResourceAccessKind.DenyCors);
            browser.CoreWebView2.Navigate("https://mimotion-test.invalid/index.html");
        }

        private void CompleteSelfTest()
        {
            if (!testJsPassed || !testDownloadPassed || closing) return;
            WriteSelfTest(true, "JavaScript、持久化存储与 Blob 文件导出检查通过。");
            BeginInvoke(new Action(Close));
        }

        private void WriteSelfTest(bool passed, string text)
        {
            if (String.IsNullOrEmpty(options.SelfTest)) return;
            JsonFile.Write(options.SelfTest, new
            {
                passed = passed, javascript = testJsPassed, storage = testJsPassed,
                previous_storage = testPriorStorage, blob_download = testDownloadPassed,
                message = text, runtime = runtime, export_dir = exportDirectory, downloads = downloads
            });
            Environment.ExitCode = passed ? 0 : 1;
        }
    }

    internal static class EnumerableCompat
    {
        internal static IEnumerable<T> TakeLastCompat<T>(this IList<T> source, int count)
        {
            for (int index = Math.Max(0, source.Count - count); index < source.Count; index++) yield return source[index];
        }
    }

    internal static class Program
    {
        [STAThread]
        private static void Main(string[] arguments)
        {
            Options options = null;
            try
            {
                options = Options.Parse(arguments);
                if (options.Parent != IntPtr.Zero && !Native.IsWindow(options.Parent)) return;
                if (!String.IsNullOrEmpty(options.QuitFile) && File.Exists(options.QuitFile)) return;
                Native.MatchDpi(options.Parent);
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new HostForm(options));
            }
            catch (Exception exception)
            {
                Environment.ExitCode = 1;
                if (options != null)
                {
                    JsonFile.Write(options.StatusFile, new { state = "error", message = "运动轨迹模块暂时无法启动。", detail = exception.ToString() });
                    if (!String.IsNullOrEmpty(options.SelfTest))
                        JsonFile.Write(options.SelfTest, new { passed = false, error = exception.Message });
                }
                if (options == null || (options.Parent == IntPtr.Zero && String.IsNullOrEmpty(options.SelfTest)))
                    MessageBox.Show("运动轨迹模块暂时无法启动：" + exception.Message, "MiMotion", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
        }
    }
}
