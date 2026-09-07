# workbuddy-linux

面向 Ubuntu、Debian 和 Fedora 的 WorkBuddy Linux 社区打包项目。本项目追踪 Kylin 软件仓库公开发布的 WorkBuddy 安装包，在不修改 WorkBuddy 程序主体的前提下，生成：

从 GitHub 克隆源码后，请先运行 `chmod +x scripts/*.sh scripts/upstream.py`，再执行下文的构建命令。

- 适用于 Ubuntu、Debian 及其衍生发行版的 DEB 包；
- 适用于 Fedora 的原生 RPM 包。

> [!IMPORTANT]
> 这是非官方社区项目，与腾讯、麒麟软件、openKylin 社区没有隶属或授权关系。仓库中的 MIT 许可证仅覆盖本项目自行编写的脚本和文档，WorkBuddy 程序及品牌权利仍属于相应权利人。

## 为什么需要这个项目

WorkBuddy Linux 版目前主要通过统信 UOS 和银河麒麟的软件商店分发。Kylin 版本采用 DEB 格式，程序主体能够在通用 Linux 桌面环境运行，但官方没有直接提供面向 Ubuntu、Debian 或 Fedora 的安装入口。

本项目把发行版适配限制在安装包层：保留上游 Electron 应用、`app.asar`、内置 Node/Python 运行时及原生模块，只调整依赖、安装脚本、桌面入口、URL 协议和 RPM 元数据。

## 版本规则

应用版本号始终与上游完全一致。例如，上游版本为 `5.4.5` 时：

```text
DEB Version: 5.4.5
RPM Version: 5.4.5
Git tag:     v5.4.5
```

RPM 格式要求存在独立的 `Release` 字段，本项目使用 `Release: 1`。它是打包修订号，不属于 WorkBuddy 应用版本。

自动追踪不会修改、补零或重新解释上游版本号。

## 支持范围

| 产物 | 目标系统 | 当前架构 |
|---|---|---|
| DEB | Ubuntu 20.04 及更新版本、Debian 11 及更新版本 | amd64 |
| RPM | 当前受支持的 Fedora 桌面版本 | x86_64 |

实际支持范围由上游二进制决定。当前 WorkBuddy 主程序最高要求 GLIBC 2.25，内置 Node 运行时最高要求 GLIBC 2.28。

## 安装

从项目的 GitHub Releases 下载与系统匹配的文件。

Ubuntu 或 Debian：

```bash
sudo apt install ./workbuddy-linux_VERSION_amd64.deb
```

Fedora：

```bash
sudo dnf install ./workbuddy-linux-VERSION-1.*.x86_64.rpm
```

安装后可以从应用菜单启动 WorkBuddy，也可以运行：

```bash
workbuddy
```

## 从源码构建

构建脚本接受本地 Kylin DEB，也接受公开下载 URL。

构建 Ubuntu/Debian 包：

```bash
./scripts/build-deb.sh workbuddy_VERSION_amd64.deb dist
```

构建 Fedora RPM：

```bash
./scripts/build-rpm.sh workbuddy_VERSION_amd64.deb dist
```

同时构建两种格式：

```bash
./scripts/build-all.sh workbuddy_VERSION_amd64.deb dist
```

本地构建 RPM 需要 `rpmbuild`。在 Ubuntu/Debian 上对应软件包通常名为 `rpm`；在 Fedora 上为 `rpm-build`。

## 查询上游版本

列出公开仓库中的 amd64 版本：

```bash
python3 scripts/upstream.py list --arch amd64
```

查询最新版本：

```bash
python3 scripts/upstream.py latest --arch amd64
```

默认上游地址为：

```text
https://software.openkylin.top/openkylin/yangtze/pool/main/deb/workbuddy/
```

可以通过 `WORKBUDDY_UPSTREAM_INDEX` 环境变量覆盖，方便镜像和测试。

## 自动发布流程

GitHub Actions 每天检查一次上游目录。发现尚无对应 `vVERSION` Release 的版本时，会依次执行：

1. 下载 Kylin 原始 DEB；
2. 读取并校验上游 `Version` 和 `Architecture`；
3. 构建 Ubuntu/Debian DEB；
4. 构建 Fedora RPM；
5. 校验两个产物的内部版本字段；
6. 生成 SHA-256 文件并创建 GitHub Release。

也可以从 Actions 页面手动运行 **Track WorkBuddy releases**。

## 打包原则

- 不反编译或修改 `app.asar`；
- 不重编译、不替换 WorkBuddy ELF 和原生模块；
- 保持应用版本与上游一致；
- DEB 和 RPM 使用同一份上游 payload；
- 不使用 `alien` 进行 DEB 到 RPM 的机械转换；
- 默认保留 Electron sandbox，不添加 `--no-sandbox`；
- 每个 Release 同时记录上游包及社区产物的 SHA-256。

## 已知限制

- WorkBuddy 的 Linux 更新界面可能仍跳转到官方网页或 Kylin 软件商店；请通过本项目 Release 更新社区包。
- Fedora 的 SELinux、Wayland、系统托盘和 `workbuddy://` 回调需要在每个新版本中持续验证。
- 项目仅追踪公开可取得的 Kylin 构建。银河麒麟商店可能按设备和系统版本返回不同文件，因此不能假定所有商店包与公开仓库文件逐字节相同。
- 上游可能随时调整下载地址、依赖或许可条款，自动发布因此可能暂停。

## 参与贡献

欢迎提交兼容性报告和打包改进。报告问题时请提供发行版版本、桌面环境、CPU 架构、安装日志和启动日志，避免提交账号、令牌或个人文件。

脚本和文档采用 [MIT License](LICENSE)。WorkBuddy 二进制不适用该许可证。
