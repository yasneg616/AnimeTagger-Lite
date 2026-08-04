# Windows onedir 构建

正式便携包只使用 Python 3.11 x64 与 PyInstaller `onedir`；不使用 onefile、
UPX、Nuitka 或系统级依赖安装。CPU/CUDA 从同一源码构建，不能混合两个环境。

## 环境

- CPU：`D:/tagger/.venv311-cpu/`，只允许 `onnxruntime`。
- CUDA：`D:/tagger/.venv311-cuda/`，只允许 `onnxruntime-gpu`。
- 精确验证版本见 `requirements-cpu.lock.txt` 与
  `requirements-cuda.lock.txt`。
- 项目根必须有用户确认的 `LICENSE`；构建器不会代替项目所有者选择许可证。

建立 CPU 环境的示例：

```powershell
& 'C:\Path\To\Python311\python.exe' -m venv .venv311-cpu
.\.venv311-cpu\Scripts\python.exe -m pip install --upgrade pip
.\.venv311-cpu\Scripts\python.exe -m pip install -r packaging\requirements-cpu.lock.txt
```

CUDA 环境同理使用 `requirements-cuda.lock.txt`。不得在任一环境同时安装
`onnxruntime` 和 `onnxruntime-gpu`。

## 正式构建

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build_cpu.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build_cuda.ps1
```

脚本严格检查 Python 3.11 x64、CPU/GPU Runtime 冲突、`pip check`、
`compileall`、完整 pytest（不允许 skip）、真实模型 SHA、真实图片哈希、真实
Provider、CLI/GUI smoke，然后清理对应 PyInstaller 缓存、构建、审计、压缩并
计算 SHA-256。错误会立即停止；脚本不修改系统环境，也不上传任何文件。

默认输出到 `release/`。GUI 正式包没有控制台；本地诊断可显式增加
`-DebugConsole`。调试构建不得作为正式发行物。

## 清理

先用 `-WhatIf` 查看目标：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\clean.ps1 -WhatIf
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\clean.ps1
```

清理脚本只处理项目内列明的 build/dist、PyInstaller 工作目录、正式 ZIP/报告
和 `.final-release-smoke`。它不会删除源码、模型、`validation-images`、用户
图片、Caption、配置或项目外的隔离 Smoke。

## 发行内容边界

构建审计拒绝模型权重、`selected_tags.csv`、验证图片、tests、pytest、
QtWebEngine、PyTorch、TensorFlow、Hugging Face Hub、用户配置/日志、绝对开发
路径和 CPU/CUDA 混装。图片格式插件及 pillow-heif 原生库必须在隔离 Smoke
中实际验证后才可发布。
