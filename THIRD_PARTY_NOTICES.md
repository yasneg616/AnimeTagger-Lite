# 第三方依赖与许可证

AnimeTagger Lite 便携包实际包含以下运行时或嵌入组件：

| 组件 | 用途 | 上游许可证 |
|---|---|---|
| NumPy | 图像张量 | BSD-3-Clause |
| Pillow | PNG/JPEG/WebP 等图片解码 | HPND |
| pillow-heif | HEIC/HEIF/AVIF 解码插件 | BSD-3-Clause |
| ONNX Runtime / ONNX Runtime GPU | 本地 ONNX 推理 | MIT |
| NVIDIA CUDA/cuDNN Python 运行库（仅 CUDA 包） | CUDA Provider 所需 DLL | NVIDIA 软件许可证 |
| PySide6 / Qt for Python | Windows 桌面界面 | 本发行选择 LGPL-3.0-only；上游另提供 GPL/commercial 选项 |
| CPython（便携包内嵌运行时） | Python 3.11 运行时 | PSF License |
| PyInstaller | Windows onedir 构建及 EXE 内嵌 bootloader | GPL-2.0-or-later with bootloader exception |
| SmilingWolf/wd-vit-tagger-v3（用户自行准备） | 动漫图片标签模型 | Apache-2.0 |

`LICENSES/` 由构建器按实际锁定环境生成，保留各 wheel 的许可证、NOTICE 或
METADATA。PySide6 6.11.1 wheel 元数据声明
`LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`；本发行采用 LGPL-3.0-only，
并附带锁定 SHA-256 的 LGPL-3.0 与其纳入的 GPL-3.0 标准正文。wheel 自带的
`LicenseRef-Qt-Commercial.txt` 也按原样保留，但本项目不主张 Qt 商业许可证。

AnimeTagger Lite 项目自身按根目录 `LICENSE` 中的 MIT License 授权。该 MIT
License 不会替代、覆盖或重新授权本表中的第三方组件。模型不随本项目源代码或
发行包分发；WD ViT Tagger v3 及模型文件继续独立遵守其上游许可证。

上游链接：

- https://github.com/numpy/numpy
- https://github.com/python-pillow/Pillow
- https://github.com/bigcat88/pillow_heif
- https://github.com/microsoft/onnxruntime
- https://docs.nvidia.com/deeplearning/cudnn/latest/reference/eula.html
- https://doc.qt.io/qtforpython-6/
- https://www.python.org/psf/license/
- https://pyinstaller.org/
- https://huggingface.co/SmilingWolf/wd-vit-tagger-v3
