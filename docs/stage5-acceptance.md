# AnimeTagger Lite 0.5.0-rc1 阶段 5 验收

> 本文保留 2026-07-30 阶段 5 的点时证据和当时的 365 项计数。2026-08-03
> 最终发行补充复验已增至三环境 `395 passed, 0 skipped`，见
> `docs/real-model-validation.md` 与 `docs/release-smoke-report.md`。

日期：2026-07-30 至 2026-07-31  
平台：Windows 10/11 x64，NVIDIA GeForce RTX 4080 Laptop GPU  
结论：阶段 5 的真实图片、Python 3.11、CPU、CUDA、批处理和便携发行门槛通过

## 验证图片

- 只检查 `D:/tagger/validation-images/`
- 有效图片：6 张真实 PNG
- 原始尺寸：全部 832×1216
- EXIF Orientation：无
- alpha extrema：254–255，复用既有透明背景预处理
- 未移动、改名、覆盖、重编码或修改元数据
- 6 张原图在全部单图、GUI、批处理和发行 Smoke 前后 SHA-256 不变
- `.gitignore` 排除整个 `validation-images/`

完整哈希见 `docs/real-model-validation.md`。

## Python 3.11

- 来源：python.org 官方 Python 3.11.9 Windows x64 安装程序
- 官方 URL：
  `https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe`
- 安装器大小：26,216,840 bytes
- SHA-256：
  `5ee42c4eee1e6b4464bb23722f90b45303f79442df63083f05322f1785f5fdde`
- 官方 MD5：`e8dcd502e34932eebcaf1be056d5cbcd`
- Authenticode：Valid；签名者 Python Software Foundation
- 解释器：
  `%LOCALAPPDATA%/Programs/Python/Python311-Stage5/python.exe`
- CPU 环境：`D:/tagger/.venv311/`
- CUDA 环境：`D:/tagger/.venv311-cuda/`
- 没有替换 Python 3.10/3.13、系统默认 Python、PATH 或文件关联

CPU 环境使用 `onnxruntime 1.28.0`；CUDA 环境只安装
`onnxruntime-gpu 1.28.0`，没有同时安装 CPU Runtime。PyInstaller 6.21.0
只安装在两个开发构建环境，没有进入正式 requirements。

最终结果：

| 环境 | pytest | skip | pip check | compileall |
|---|---:|---:|---|---|
| Python 3.10.11 CPU | 365 passed | 0 | 通过 | 通过 |
| Python 3.11.9 CPU | 365 passed | 0 | 通过 | 通过 |
| Python 3.11.9 CUDA | 365 passed | 0 | 通过 | 通过 |

## CPU 真实推理与 GUI

- Session Provider：`CPUExecutionProvider`
- 输入：NHWC float32，`batch × 448 × 448 × 3`
- 输出：10,861，全部有限并位于 0–1
- 记录的 3 张推理：346.296、332.510、347.867 ms
- 模型加载记录：738.241 ms
- 安全高置信度示例：`1girl`、`white_hair`、`long_hair`、
  `short_hair`、`solo`、`blue_hair`、`pink_hair`
- General、Character、Rating 的 CSV 索引映射正常，没有整体标签错位
- CLI TXT/JSON 成功，图片哈希不变

真实 MainWindow 使用实际 TaggingService、InferenceController 和图片解码器，
完成单图、三图顺序队列、标签搜索/筛选、编辑、手动标签、四个 profile、三个
反向模式、复制、TXT/JSON、释放、重载与再次识别。没有 Windows“无响应”；
关闭后 Worker、Decoder 与 Python 线程全部退出。

验收中发现 10,861 行表格在 profile/反向切换时重复重建，单次约 2.8 秒。
修复后通常为 5–72 ms；显式显示全部低置信度行仍需约 1.5–1.6 秒，这是用户
主动请求的大表渲染成本。

## CUDA 真实推理与 GUI

- GPU：NVIDIA GeForce RTX 4080 Laptop GPU
- 驱动：610.74
- `onnxruntime-gpu 1.28.0`
- available providers：TensorRT、CUDA、CPU
- 实际 Session：`CUDAExecutionProvider`
- CPU 回退：无
- 冷加载：3,843.137 ms；重载：508.143 ms
- 首张暖机：250.177 ms；后续：13.522、13.528 ms
- 释放/重载后推理：16.107 ms
- 显存：3,098 → 3,800 → 3,810 → 3,272 MiB

CPU/CUDA 的 3 张图 Top 10 顺序完全一致，Top 20 重合均为 20/20；最大绝对
分数差为 0.000945、0.000870、0.000778。

真实 CUDA GUI：加载 709.974 ms，单图 450.815 ms，三图队列
706.899 ms，重载 484.672 ms；UI 心跳最大间隔 529.334 ms，没有无响应；
关闭 88.811 ms，无残留任务。

首次 CUDA 诊断发现 `cublasLt64_13.dll` 缺失，ORT 曾静默创建 CPU Session。
修复包括使用官方 `onnxruntime-gpu[cuda,cudnn]` 运行库、便携包内 DLL 定向
预加载，以及检查 `session.get_providers()` 后报告实际回退。没有安装完整
CUDA Toolkit，也没有修改系统驱动。

PyInstaller 会报告可选 TensorRT 的 `nvinfer_10.dll` 与
`nvonnxparser_10.dll` 未提供；本项目不请求 TensorRT。正式 CUDA 包的真实
Session 与 6 图批处理均明确使用 CUDA Provider。ORT 另输出 12 个 Memcpy
节点的性能警告，不影响正确性或 Provider 结果。

## 真实批处理

- 测试副本：6 张，根目录 3 张、子目录 3 张
- 非递归扫描：3；递归扫描：6
- dry-run：6，未创建输出或 Manifest
- 单任务 Session：1
- 暂停：完成第 1 张后保持 300 ms，没有启动下一张
- 继续：恢复并完成 6/6
- 取消：1 completed + 5 cancelled；没有启动新项
- 取消恢复：5 项重置，最终 6/6
- 受控导出失败：5 completed + 1 failed；重试 1 项后 6/6
- 未完成 Manifest：发现并恢复，最终 6/6
- Caption 策略：skip、overwrite、backup_and_overwrite、
  append_trigger、merge 全部通过
- 输出模式：beside、mirror、flat 全部通过
- LoRA trigger first/last、TXT、逐图 JSON、CSV、摘要 JSON、Manifest 通过
- 测试过程中总计 33 次真实预测，Session 加载 1 次
- 原始图片与副本图片哈希不变
- `.animetagger.tmp`、`.part`、半截输出与残留 Python 线程：0

## 候选与正式发行 Smoke

版本门槛按顺序执行：先以内部版本 0.4.0 构建
`rc1-candidate`，完成完整隔离 Smoke 后才统一修改为 0.5.0-rc1 并重建。

隔离根：`D:/tagger-release-smoke/`。工作目录不是源码目录，PATH 只保留
Windows 系统目录，并清除 PYTHONPATH、PYTHONHOME 与 VIRTUAL_ENV。CPU/CUDA
候选和正式包均完成：

- 无模型 GUI 两次启动/关闭
- CLI `--version`/`--help`
- 外置模型真实 Session
- 中文目录、空格目录、非 ASCII 文件名
- 真实单图 JSON/TXT
- 6 图文件夹批处理
- LoRA Caption、JSON、CSV、Manifest
- `data/config/ui.ini` 写入和重启读取
- 关闭后残留进程 0

正式包最终 Smoke：

| 包 | 单图 Provider | 批处理 | 应用版本 |
|---|---|---:|---|
| CPU | CPUExecutionProvider | 6/6 | 0.5.0-rc1 |
| CUDA | CUDAExecutionProvider | 6/6 | 0.5.0-rc1 |

桌面可视控制桥在本任务中没有暴露可调用工具，因此正式 EXE 使用 Qt offscreen
完成启动/关闭；窗口深度交互证据来自同一最终代码的真实 MainWindow CPU/CUDA
验收，不是 Mock。

## 发行物

| 发行物 | onedir 大小 | ZIP 大小 | SHA-256 |
|---|---:|---:|---|
| `AnimeTaggerLite-0.5.0-rc1-win64-cpu-portable.zip` | 240,090,288 bytes | 93,322,544 bytes | `f63a362823a55f95fb92c49aff6ad3e7112ac8ff65fb94183b52309c28ff58b1` |
| `AnimeTaggerLite-0.5.0-rc1-win64-cuda-portable.zip` | 2,107,573,714 bytes | 1,449,911,891 bytes | `aa0a75c4618a266f0302d67d4f3b43d8885c150cae310fc351bc8b903bd7430b` |

两个 ZIP 均为 PyInstaller onedir，不用 onefile/UPX，不依赖源码或系统 Python。
CPU 包只从 CPU 环境构建，CUDA 包只从 GPU 环境构建。发行 ZIP 不包含模型、
验证图片、tests、pytest、pytest-qt、QtWebEngine、PyTorch、TensorFlow、
Hugging Face Hub、构建缓存、用户配置、日志、测试输出或 Git 元数据。

## 离线和网络边界

- 成品没有自动模型下载、后台联网、更新检查、遥测或首次启动请求
- 下载只存在于用户显式运行的 `scripts/download_wd14_model.py`
- PyInstaller 与下载工具没有进入运行 requirements
- 发行包模型目录只有 `README.txt`
- 删除模型目录不会影响用户图片或 Caption

## 本轮实际修复

1. 优化大标签表在 profile/反向模式切换时的重复规范化和模型重置。
2. 修复标签改名后可能保留旧 prompt group 的缓存一致性。
3. 修复 CUDA DLL 未加载时 ORT 静默 CPU 回退却不显示警告。
4. 增加 frozen/portable 路径层，确保资源只从发行根读取，数据只写
   `data/`，CUDA DLL 只从 `_internal` 定向加载。
5. 增加真实验证图片环境变量解析，不加入机器绝对路径或网络回退。
6. 增加 CPU/CUDA 独立 PyInstaller 构建、内容审计、许可证装配和原子 ZIP。
7. JSON schema 2 增加 `application_version`，与 GUI、CLI 和构建版本统一。

## 当前未实现

- 安装程序
- 自动更新
- 应用内自动模型下载
- 多模型支持
- 自然语言图片描述
- ComfyUI/A1111/Forge 联动
- 自动 LoRA 训练
- 文件系统实时监控
- 代码签名

阶段 5 到此停止，不进入正式 1.0。
