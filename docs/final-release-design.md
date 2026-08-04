# AnimeTagger Lite 最终发行设计

当前源码版本：`1.0.0`  
目标版本：`1.0.0`  
状态：1.0.0 CPU/CUDA 终版构建、隔离 Smoke、静态审计与 Defender 终扫全部通过

## 范围

最终阶段只收敛 Python 3.11、CPU/CUDA Runtime、便携路径、PyInstaller onedir、
隔离 Smoke、安全/许可证审计、版本与文档。WD14 推理、标签编辑、提示词、批处理、
LoRA Caption、CSV/JSON/Manifest 等既有业务行为不新增分支。

## 单一源码与两种构建

`app.__version__` 是应用版本唯一代码来源。`pyproject.toml` 使用 setuptools
动态属性读取该值；GUI 标题、Qt application version、单图 CLI、批处理 CLI、
JSON `app_version`、构建目录、ZIP 和报告都从同一值取得。旧 JSON
`application_version` 作为 schema 2 兼容别名保留。

CPU/CUDA 使用相同源码和 spec：

```text
app source
    └─ packaging/animetagger-lite.spec
         ├─ .venv311-cpu  -> onnxruntime
         └─ .venv311-cuda -> onnxruntime-gpu + official NVIDIA runtimes
```

构建环境同时出现两个 ORT 分发时立即拒绝。CUDA 是否成功只看实际
`session.get_providers()`，不能用用户选择或 available providers 冒充。

## 路径边界

`app/runtime_paths.py` 统一解析源码与冻结路径，不依赖当前工作目录：

- `resources/`：发行根的只读 JSON 资源；
- `models/wd-vit-tagger-v3/`：外置模型；
- `_internal/`：PyInstaller 和 CUDA/cuDNN 运行库，不写用户数据；
- 存在 `portable.flag` 时，设置、UI 状态、日志、Manifest、剪贴板临时文件只写
  `data/config`、`data/logs`、`data/batch-jobs`、`data/temp`。

启动时会创建并探测这些目录。只读/无权限目录返回面向用户的中文错误，GUI
不得显示 Python traceback。升级时整个旧 `data/` 可独立备份，不应被新版覆盖。

## 发行结构

```text
AnimeTaggerLite-<version>-win64-<cpu|cuda>-portable/
├── AnimeTaggerLite.exe
├── AnimeTaggerLiteCLI.exe
├── _internal/
├── resources/
├── models/wd-vit-tagger-v3/README.txt
├── data/{config,logs,batch-jobs,temp}/
├── README.txt
├── QUICK_START.txt
├── THIRD_PARTY_NOTICES.txt
├── LICENSE
├── LICENSES/
├── BUILD-MANIFEST.json
└── portable.flag
```

模型、`selected_tags.csv`、验证图片、tests、pytest、QtWebEngine、用户配置和日志
不得进入 ZIP。CPU/CUDA 目录必须分别解压，不能互相覆盖 `_internal`。

## 升版门槛

1. Python 3.11 CPU/CUDA 的 `pip check`、compileall、全量 pytest 为零 skip。
2. 官方模型哈希、结构、10,861 标签映射与用户真实图片哈希通过。
3. CPU 与 CUDA 真实 Session、GUI、批处理通过；CUDA 无静默 CPU 回退。
4. 以 `0.5.0-rc1` 构建候选并在项目外完成无模型及外置模型隔离 Smoke。
5. 发行目录无模型/用户数据/源码路径/系统 Python 依赖；Defender 无未处理告警。
6. 项目所有者明确确认项目 `LICENSE` 文本。
7. 两轮自检发现的问题修复并完整复测。
8. 以上全部满足后才把唯一版本源改为 `1.0.0`，重新构建并再次执行同等 Smoke。

任一核心门槛未通过时保留 `0.5.0-rc1`。CPU 全部通过而 CUDA 阻塞时可只发布
CPU 1.0.0，但不得生成或描述为已发布的 CUDA 包。

## 当前门槛状态（2026-08-04）

八项门槛全部完成。三环境全量回归、CPU/CUDA 真实 Session、真实图片、GUI、
批处理、格式矩阵、模型释放/重载、权限保护与残留进程均已复验。项目采用标准
MIT License，版权行为 `Copyright (c) 2026 yasneg`；第三方组件和 WD ViT
Tagger v3 模型继续遵守各自许可证，不由项目 MIT 重新授权。

RC1 CPU/CUDA 正式候选先通过构建、项目外隔离 Smoke 与 Defender，随后唯一版本
源升为 `1.0.0`。终版使用两个锁定 Python 3.11 环境从零重建，并重新执行 395 项
预检、真实 Provider 推理、项目外 ZIP 隔离 Smoke、静态边界审计和 Defender
终扫。最终 ZIP 哈希记录在 `release/SHA256SUMS.txt`；历史候选与构建中间目录已
清理，不用于替代或冒充终版证据。
