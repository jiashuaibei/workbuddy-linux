# WorkBuddy Linux Tracker

网页：https://workbuddy-linux-tracker.vercel.app/

网页由 Vercel 托管，导入此仓库并将 Root Directory 设为 `web`，框架选择 Other。推送网页更新后由 Vercel 自动部署。版本追踪仍由下述 GitHub Actions 执行；当前 GitHub 账号限制阻止定时任务运行，数据暂由手动检查更新。网页上线不代表每小时检查已恢复。

追踪 WorkBuddy 官网公开更新接口，提供官方 Linux DEB / RPM 下载链接和历史版本记录。非腾讯官方项目。

项目已停止对麒麟安装包进行二次封装。旧 v5.4.5 Release 是历史社区构建，不属于本站追踪的官方原包。旧构建脚本仅作为历史参考保留，自动化不再调用它们。

## 官方来源

- [DEB 更新接口](https://www.workbuddy.cn/v2/update?platform=workbuddy-linux-x64-deb)
- [RPM 更新接口](https://www.workbuddy.cn/v2/update?platform=workbuddy-linux-x64-rpm)

更新接口域名为 `www.workbuddy.cn`；下载链接目前由接口指向 `download.codebuddy.cn`。网页展示实际下载域名，直接链接官方文件，不镜像、不重打包、不伪装链接。仅允许已核对的 HTTPS 域名；未来域名变化需要人工审核后修改允许列表。

## 追踪与历史

运行 `python3 scripts/track_official.py`，数据写入 `web/data/releases.json`。保留完整产品版本，不将其等同于 DEB 内部的简短版本字段。历史从首次运行开始，不声称覆盖此前所有版本；同格式、版本、URL、接口 SHA-256 相同时去重，变更时新增记录。某个接口失败不会清空上一次有效记录。

接口 SHA-256 仅原样记录，没有下载并校验文件。曾观察到接口值与文件哈希不一致，因此网页明确标注「未验证」。上游时间戳和本站首次发现时间分别记录。历史链接能否继续下载由上游决定。

## 自动检查与网页

`.github/workflows/track-releases.yml` 每小时第 17 分钟（UTC）检查一次，也支持手动运行。可修改 cron 为 `17 */3 * * *`，改为每 3 小时。GitHub 调度可能延迟；公共仓库长期无活动可能暂停定时工作流，Actions 额度或账单异常也会阻止运行。

在 GitHub 仓库 Settings → Pages 中选择 GitHub Actions，然后运行 **Track official Linux releases**。同一工作流保存观测记录并部署 `web/`，无需额外网站服务。必须允许 Actions 写入仓库，分支保护也需允许该更新。网页超过 3 小时无数据更新会显示提醒。

本地预览：`python3 -m http.server 8001 --bind 127.0.0.1 --directory web`。

测试：`python3 -m unittest discover -s tests -v`。

## 范围

当前仅追踪接口已明确提供的 x86_64 DEB / RPM。格式不等于发行版兼容性保证。源码采用 MIT 许可证，WorkBuddy 二进制及品牌归其权利人所有。
