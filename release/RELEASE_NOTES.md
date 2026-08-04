# AnimeTagger Lite 1.0.0 Release Notes

AnimeTagger Lite 1.0.0 已完成正式 CPU/CUDA 构建、真实模型与真实图片验收、
项目外 ZIP 隔离 Smoke、发行静态审计和 Microsoft Defender 最终扫描。

项目自身采用标准 MIT License，版权行为 `Copyright (c) 2026 yasneg`。随包
第三方组件与 WD ViT Tagger v3 模型继续分别遵守其上游许可证，不由项目 MIT
License 替代或重新授权。

## 正式发行物

| 变体 | ZIP 大小 | SHA-256 |
|---|---:|---|
| CPU | 78,922,383 bytes | `efc21ba19da6205eeb2a166e89a1cc83ec9d742e53d9db37f962fff9296c2e7c` |
| CUDA | 1,435,178,834 bytes | `83d5b6a56feab1d4dade2c74d7def3cabaf7df65b67f270a4ab66a5e5bd11ec8` |

完整构建元数据与可复制的校验值见 `BUILD_REPORT.md` 和 `SHA256SUMS.txt`。

## 主要功能

- 本地 WD ViT Tagger v3 ONNX 动漫图片标签识别。
- 标签筛选、编辑、正向/反向提示词与原子 TXT/JSON 导出。
- PySide6 单图/多图队列和文件夹批处理。
- LoRA Caption、CSV、Manifest、暂停、取消、失败重试和显式恢复。
- 完全离线的 Windows PyInstaller onedir 便携包。

## CPU 与 CUDA

- CPU 版只包含 `onnxruntime`，兼容性更高。
- CUDA 版只包含 `onnxruntime-gpu` 与官方 NVIDIA CUDA/cuDNN Python 运行库，
  需要兼容 NVIDIA 驱动；本次真实 Session 为 `CUDAExecutionProvider`，没有
  静默回退。
- 两个 ZIP 必须解压到不同目录，不能互相覆盖 `_internal`。
- CUDA 无法加载时可改用 CPU 版。

## 验收摘要

- Python 3.10 CPU、Python 3.11 CPU、Python 3.11 CUDA：均为
  `395 passed, 0 skipped`。
- 两次正式终版构建预检分别再次执行 395 项测试。
- CPU/CUDA ZIP 均从项目外目录独立解压，在无系统 Python、无源码资源条件下
  完成真实模型、6 张真实图片、格式矩阵、批处理与导出 Smoke。
- 最终 CPU GUI 使用真实图片完成推理、反向模式切换、模型释放与重载。
- 原始模型和 6 张验证图片的 SHA-256 均保持不变；退出后临时文件和残留进程为 0。
- Microsoft Defender（签名 `1.455.490.0`）扫描整个最终 `release` 目录，
  退出码 0，结果为 `found no threats`。

## 模型

发行 ZIP 不包含模型。用户须从官方 `SmilingWolf/wd-vit-tagger-v3` 固定 revision
`7f6b584d0bd3f55c4531f14ba3d4761b2bccdc0f` 准备 `model.onnx` 与
`selected_tags.csv`，放入 `models/wd-vit-tagger-v3/`。软件不会自动下载模型。

## 数据与网络安全

图片、标签和提示词不上传；没有遥测、自动更新、后台网络请求或应用内模型
下载。程序不修改、移动或删除原图。默认不覆盖 Caption，修改已有内容需要明确
确认。第三方许可证正文与元数据位于随包 `LICENSES/`，项目许可证位于发行根
`LICENSE`。

## 升级

关闭旧版后备份其 `data/`，把新版解压到新目录，再按需复制设置。不要覆盖混装
CPU/CUDA 目录。模型可重新放入新版 `models/wd-vit-tagger-v3/`；删除模型目录
不会影响用户图片或 Caption。

## 已知限制

- 不提供安装程序、代码签名、自动更新或应用内模型下载。
- 不支持多 Tagger 模型、自然语言图片描述、自动 LoRA 训练、第三方绘图软件
  联动或文件系统实时监控。
- 模型标签是辅助结果，不保证百分之百语义准确。
