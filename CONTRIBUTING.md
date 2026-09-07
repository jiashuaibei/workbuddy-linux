# Contributing

感谢参与 workbuddy-linux。

提交兼容性问题时，请包含：

- 发行版及版本；
- CPU 架构；
- X11 或 Wayland 会话；
- 安装命令和完整错误；
- `workbuddy` 的终端启动日志。

请删除日志中的账号、访问令牌、Cookie、本地路径和个人文件内容。

代码提交应遵循以下原则：

- 不修改 WorkBuddy 应用 payload；
- 不默认禁用 Electron sandbox；
- 不在仓库中提交 DEB、RPM、AppImage 或解包后的上游文件；
- 保持 DEB/RPM 的 `Version` 与上游完全一致；
- 修改打包脚本后运行 `bash ./scripts/test.sh`。
