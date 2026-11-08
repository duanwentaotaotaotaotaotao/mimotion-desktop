# MiMotion Desktop · 桌面助手

面向 Windows 64 位的 MiMotion 桌面软件，提供账号与步数设置、手动运行、运行记录、Windows 自动任务，以及内嵌的在线运动轨迹编辑器。

当前版本：**1.1.0**。

## 下载与使用

从 [Releases](https://github.com/duanwentaotaotaotaotaotao/mimotion-desktop/releases/latest) 下载 Windows exe 或完整压缩包。发布的 exe 已包含 Python 及运行依赖，无需另外安装 Python。

1. 双击软件，选择自己的 mimotion 项目或数据目录。本机存在 `E:\mimotion` 时会优先读取；其他情况可在界面中设置账号。
2. 在“账号与步数”设置 Zepp Life 手机号/邮箱和目标，点击“保存设置”。已有密码留空保留。
3. 回到“运行面板”点击“立即运行”，在“运行记录”查看结果。打开窗口不会自动提交步数。
4. 在“自动任务”查看或调整运行时间。自动执行需要电脑开机并登录 Windows。
5. 左侧“运动轨迹”加载 [sport.gyvv.top 原站](https://sport.gyvv.top/)，可使用地图、路线编辑和 FIT/TCX/GPX/CSV 等导出功能；“大窗口”适合地图编辑。

![运行面板，示例账号与离线数据](docs/images/overview.png)

## 运动轨迹模块

该模块通过 WebView2 在软件中加载原站，需要联网。地图、网页和生成服务由原站提供，本项目未复制网站源码、地图密钥或服务端代码。

- 导出文件默认保存到所选项目的“轨迹导出”，也可以在页面工具栏更改位置。
- 同名下载会另存为新文件。
- 浏览器路线与设置持久保存在项目的 `.mimotion-desktop/sport-web-profile`。
- 原有 MiMotion/Zepp 账号配置不会自动填入该网站。
- 使用系统的 Microsoft Edge WebView2 Runtime；缺少时需安装 [微软官方运行环境](https://developer.microsoft.com/microsoft-edge/webview2/)。

![内置浏览器加载原站与地图](docs/images/sport.png)

## 本地数据

账号与配置保存在所选目录的 `.env`，保存前会在 `backups/` 备份。登录缓存、日志、浏览器资料和导出文件也保存在该目录，不属于源码。

仓库和 Release 不包含个人账号、密码、已有令牌缓存或浏览器资料。分享自己的数据目录前请自行检查这些本地文件。

软件显示的是接口执行结果；其他运动平台的显示仍取决于其绑定及同步状态。在线轨迹工具的功能和服务可用性取决于原站。

## 从源码运行与构建

已在 Windows 11 64 位、Python 3.14 上构建验证。建议在虚拟环境中安装依赖。

```powershell
python -m pip install -r requirements-build.txt
python app.py
```

构建独立 exe：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

构建脚本会编译 WebView2 宿主、运行核心测试并生成 `dist/MiMotion.exe`。宿主编译需要 .NET Framework 4.8 的 C# 编译器，所需 WebView2 SDK DLL 和许可已保存在 `assets/sport_host/`。普通用户使用发布版无需编译。

核心测试：

```powershell
python -m unittest discover -s . -p test_backend.py -v
```

离线模拟（使用专门的测试目录和虚构账号）：

```powershell
python app.py --project .\test-data --demo
```

`--demo` 不连接 Zepp，也不修改自动任务；仍会在测试目录保存设置和模拟日志。运动轨迹页面加载的是独立在线工具，访问它仍需要网络。

## 代码结构

- `app.py`：桌面界面与页面导航。
- `backend.py`：配置、独立运行进程、日志与 Windows 自动任务。
- `sport.py`、`sport_host_src/`：WebView2 内嵌页面、下载与生命周期管理。
- `engine.py`、`util/`：基于上游本机版本的 MiMotion 核心；打包副本修复了首次登录未设置实例 `user_id` 的问题。
- `assets/`：图标、宿主程序、WebView2 SDK 文件与第三方许可。

更多操作和验证范围见 [使用说明](docs/使用说明.txt) 与 [验证记录](docs/验证记录.md)。验证覆盖核心模拟、内嵌地图、窗口回收、localStorage 和 Blob 下载，未验证真实账号向第三方平台的同步结果。

## 来源与许可

- MiMotion 上游：[TonyJiangWJ/mimotion](https://github.com/TonyJiangWJ/mimotion)，沿用 Apache-2.0；见 [LICENSE](LICENSE)、[原许可证](LICENSE-mimotion.txt) 和 [NOTICE](NOTICE.txt)。
- 在线运动轨迹工具：[sport.gyvv.top](https://sport.gyvv.top/)，由原站独立提供。
- WebView2 SDK 许可：[LICENSE-WebView2.txt](assets/sport_host/LICENSE-WebView2.txt)。
- 其他依赖许可：[THIRD-PARTY-LICENSES.txt](assets/THIRD-PARTY-LICENSES.txt)。
