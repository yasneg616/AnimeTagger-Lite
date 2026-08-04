# Windows 构建可复现性

## 已验证工具链

- Python：python.org 官方 CPython 3.11.9 x64 用户级安装
- 解释器基座：
  `%LOCALAPPDATA%/Programs/Python/Python311-Stage5/python.exe`
- CPU 环境：`D:/tagger/.venv311-cpu/`
- CUDA 环境：`D:/tagger/.venv311-cuda/`
- PyInstaller：6.21.0，onedir，UPX 关闭
- CPU ORT：onnxruntime 1.28.0
- CUDA ORT：onnxruntime-gpu 1.28.0

上述绝对路径只记录本机验收环境，不会写入发行目录或 ZIP。安装器来源、签名和
哈希的既有证据见 `docs/stage5-acceptance.md`。

精确顶层依赖锁位于：

- `packaging/requirements-cpu.lock.txt`
- `packaging/requirements-cuda.lock.txt`

锁文件属于开发/构建输入，不会复制进发行包。正式 requirements 继续不包含
PyInstaller、pytest 或 pytest-qt。

## 新建环境

```powershell
& 'C:\Path\To\Python311\python.exe' -m venv .venv311-cpu
.\.venv311-cpu\Scripts\python.exe -m pip install --upgrade pip
.\.venv311-cpu\Scripts\python.exe -m pip install -r packaging\requirements-cpu.lock.txt

& 'C:\Path\To\Python311\python.exe' -m venv .venv311-cuda
.\.venv311-cuda\Scripts\python.exe -m pip install --upgrade pip
.\.venv311-cuda\Scripts\python.exe -m pip install -r packaging\requirements-cuda.lock.txt
```

CPU 环境不得出现 `onnxruntime-gpu`；CUDA 环境不得出现 `onnxruntime`。

## 构建

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build_cpu.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build_cuda.ps1
```

每次正式构建不可跳过以下步骤：Python/架构与 Runtime 冲突检查、`pip check`、
`compileall -q app tests scripts`、完整 pytest、CLI help、GUI offscreen 启动、
官方模型 SHA、5–20 张用户验证图片、实际 Provider、图片前后哈希、PyInstaller、
目录内容审计、原子 ZIP 和 SHA-256。

`packaging/clean.ps1 -WhatIf` 可先预览清理目标。脚本不访问项目外路径，也不会
删除模型、验证图片、源码、Caption、配置或用户数据。

## 输出与元数据

默认 `release/` 生成：

- 两个正式 ZIP；
- `BUILD-REPORT-cpu.json` / `BUILD-REPORT-cuda.json`；
- `BUILD_REPORT.md`；
- `SHA256SUMS.txt`；
- 手工维护且经实际状态复核的 `RELEASE_NOTES.md`。

报告记录版本、构建时间、Python、PyInstaller、ORT 类型/版本、目录/ZIP 大小、
Provider、pytest 摘要、SHA-256 和 Git commit。没有 Git 元数据时必须写
`unavailable`。

Python/PyInstaller/上游 wheel 在未来可能改变；若锁定版本无法取得，必须明确
更新锁、许可证和全套 Smoke，不能静默换版本后沿用旧报告。
