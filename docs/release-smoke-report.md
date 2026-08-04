# AnimeTagger Lite 1.0.0 最终发行验收报告

复验日期：2026-08-04  
版本：`1.0.0`  
结论：**CPU/CUDA 正式发行候选全部通过**

## 自动与真实运行基线

- Python 3.10 CPU：`395 passed, 0 skipped`
- Python 3.11 CPU：`395 passed, 0 skipped`
- Python 3.11 CUDA：`395 passed, 0 skipped`
- 两个终版构建环境又分别执行一次 395 项预检，结果均通过
- CPU 实际 Session：`CPUExecutionProvider`
- CUDA 实际 Session：`CUDAExecutionProvider`，没有静默回退
- 模型输入：448×448 NHWC；模型输出与 CSV 映射均为 10,861
- 官方模型：378,536,310 bytes，SHA-256
  `35f23693620b668f4d53fd3c62bf65e40af739bc52c7eb0fbc49258b58d065b6`
- `selected_tags.csv`：308,468 bytes，SHA-256
  `298633d94d0031d2081c0893f29c82eab7f0df00b08483ba8f29d1e979441217`
- 真实图片：`validation-images/` 中 6 张 PNG，验收前后 SHA-256 不变
- 真实批处理：CPU/CUDA 各 25 次预测；机器可读证据位于
  `release/real-acceptance-cpu.json` 和 `release/real-acceptance-cuda.json`

## 正式 1.0.0 构建

| 变体 | 便携目录大小 / 文件数 | ZIP 大小 | ZIP SHA-256 |
|---|---:|---:|---|
| CPU | 203,064,710 bytes / 217 | 78,922,383 bytes | `efc21ba19da6205eeb2a166e89a1cc83ec9d742e53d9db37f962fff9296c2e7c` |
| CUDA | 2,069,673,318 bytes / 252 | 1,435,178,834 bytes | `83d5b6a56feab1d4dade2c74d7def3cabaf7df65b67f270a4ab66a5e5bd11ec8` |

CPU 预检推理为 306.463 ms；CUDA 预检推理为 194.489 ms。两个包的 GUI、单图
CLI 和批处理 CLI 均报告 `1.0.0`。构建报告和最终哈希清单位于：

- `release/BUILD-REPORT-cpu.json`
- `release/BUILD-REPORT-cuda.json`
- `release/BUILD_REPORT.md`
- `release/SHA256SUMS.txt`

## 项目外 ZIP 隔离 Smoke

CPU 与 CUDA ZIP 均解压到 `D:/tagger` 之外的一次性目录，工作目录不是源码目录，
并清除 `PYTHONHOME`、`PYTHONPATH`、`VIRTUAL_ENV`；成品不依赖系统 Python、
源码资源或构建环境。以下项目均实际通过：

- 无模型 GUI 启动和模型缺失提示；
- 外置官方模型验证、真实 Session、真实图片推理和实际 Provider；
- PNG、JPEG、WebP、透明 PNG、HEIC、HEIF、AVIF；
- 正向/反向 TXT、JSON、CSV、Manifest 与设置持久化；
- 6 张真实图片的递归 LoRA Caption 批处理；
- dry-run、暂停/继续、取消/恢复、失败重试且不重复推理、Caption 冲突策略；
- 中文、空格和非 ASCII 路径；
- 原图哈希不变、临时文件为 0、退出后残留进程为 0。

机器可读结果为 `release/ISOLATED-SMOKE-cpu.json` 与
`release/ISOLATED-SMOKE-cuda.json`，两者 `status` 均为 `passed`。

## 最终 GUI 与权限保护

最终 CPU 便携包在项目外以标题 `AnimeTagger Lite 1.0.0` 启动。实际加载官方
ONNX 后显示 448×448、10,861 标签和当前 `CPUExecutionProvider`。一张真实动漫
图片完成推理，生成 48 个正向标签；默认反向模式 `none` 为 0，切换到 `basic`
后从现有 `working_tags` 立即生成 7 个反向标签，没有重新推理。模型随后成功释放
并重载；源图 SHA-256 不变，退出后无残留进程或临时文件。

终版隔离副本的 `data/config` 被临时添加当前用户写入拒绝规则：写入探针得到
`Access denied`，程序没有进入主窗口。当前窗口自动化接口未重新暴露该独立模态
错误框；在版本升位前的同一启动代码路径上，已可见确认中文“无法启动”、实际
目标路径与 `WinError 5`，且没有 Python traceback。测试后已终止唯一隔离进程、
删除拒绝规则并通过写入探针，残留匹配 ACL 规则为 0。

## 许可证与静态边界审计

- 项目根及两个便携包的标准 MIT `LICENSE` SHA-256 均为
  `595a64eca85bd1111b25e664e18274ac1025632fe2f5ce00b3e3fb5e1c3f03b4`；
  版权行为 `Copyright (c) 2026 yasneg`。
- CPU 包 `LICENSES/` 记录 10 个组件、41 个许可证/元数据文件；CUDA 包记录
  17 个组件、55 个文件。项目 MIT 不替代、覆盖或重新授权这些上游条款。
- WD ViT Tagger v3 模型不进入发行 ZIP，并继续独立遵守其上游许可证。
- 两个便携目录与 ZIP 均不包含模型、`selected_tags.csv`、测试、用户图片、
  `.part/.tmp`、QtWebEngine 或 TensorRT Provider。
- CPU 包 CUDA/NVIDIA 运行库匹配为 0；CUDA 包所需运行库匹配为 19。
- 发行审计器对 CPU/CUDA 终版目录均通过；ZIP 条目级禁止项命中为 0。
- GUI、默认 CLI、模型缺失处理、后台任务、首次启动和更新路径均未接入下载脚本。
  `huggingface_hub` 只出现在 PyInstaller 排除清单中，不是项目或发行包依赖。
- 唯一下载逻辑仍是用户主动运行的 `scripts/download_wd14_model.py`。

## Microsoft Defender 最终扫描

- Defender Antivirus：启用
- 实时防护：启用
- 平台：`4.18.26060.3008-0`
- 病毒库：`1.455.490.0`（2026-08-03 18:20:16）
- 扫描目标：整个 `D:/tagger/release`，包含两个便携目录、EXE、ZIP 与报告
- 参数：自定义扫描、`-DisableRemediation`、`-ReturnHR`
- 退出码：0
- 结果：`found no threats`

## 清理与结论

最终审计后删除了 `release/_build`、`release/_pyinstaller`、整个历史
`release-candidate` 和两个项目外一次性验收副本，共 13,022,229,748 bytes。
这些都是可重建中间产物或临时副本；正式 CPU/CUDA ZIP、便携目录、哈希清单和
验收报告均保留。原始模型与 6 张验证图片未删除、未修改。

RC1 门槛、版本统一、终版从零重建、项目外隔离 Smoke、静态边界审计、许可证
隔离和 Defender 终扫均已完成。AnimeTagger Lite 1.0.0 CPU/CUDA 可作为正式
发行候选交付；项目仍未提供代码签名或安装程序。
