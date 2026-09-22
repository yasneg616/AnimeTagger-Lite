# AnimeTagger Lite

AnimeTagger Lite 是面向 Windows 的轻量、本地、离线动漫图片标签识别和提示词
整理工具。当前版本 **1.2.0**：三栏现代界面、五种预设主题和自定义调色盘，
支持 Canary 2026、PixAI v0.9、WD v3，以及批处理、随机 Prompt 和多个提示词 Profile。

顶部“调色盘”支持强调色、背景色、面板色实时预览；保存后持久化，取消恢复原色。
单 EXE 版整合 Python、Qt 和推理运行库；模型与 resources 等配套文件保留在程序旁，
复制时请移动整个发行目录。运行 `AnimeTaggerLite.exe`；命令行用 `AnimeTaggerLite.exe --cli`。
构建方式和三后端说明见 [packaging/README.md](packaging/README.md) 与
[docs/tagger-backends.md](docs/tagger-backends.md)。下方阶段记录为早期版本历史。

当前仍没有网络 API、遥测、自动模型下载、自动更新或 Windows 安装程序。

## 隐私与适用范围

- 图片、标签、提示词和路径只在本机处理，不会上传。
- 程序不调用 OpenAI、Claude、Gemini 或其他在线 API。
- 不包含遥测、账户、云同步或后台服务。
- 模型需要用户自行准备，程序不会联网下载。
- 工具主要面向动漫、二次元插画和游戏 CG。
- 标签识别不等于百分之百准确。
- 程序只读取图片，不修改原图。

## 当前功能

### 阶段 1：本地推理

- 单张图片 CLI。
- `model.onnx` 与 `selected_tags.csv` 懒加载。
- 单个 `WD14Engine` 复用 ONNX Session，并可释放后重新加载。
- CUDA 优先；不可用或初始化失败时回退 CPU。
- 自动读取输入尺寸和输出标签数。
- Rating、General、Character 和未知类别映射。
- EXIF 修正、透明背景合成、正方形填充、BGR/NHWC/float32 预处理。
- PNG、JPG/JPEG、WebP、BMP、GIF、TIFF、HEIC、HEIF、AVIF。
- 文件大小、像素数和帧数限制。

### 阶段 2：提示词与导出

- General、Character、Rating 独立阈值。
- Rating 默认不进入提示词。
- 排除、固定保留、规范化后去重、过滤后 `max_tags`。
- 原始名称与规范化名称同时保留。
- JSON 驱动的 16 组标签分类排序。
- `raw`、`anime`、`pony`、`krea2`、
  `cyberillustrious_semireal`、`lora_caption` 正向 profile。
- `none`、`basic`、`cleanup_detected` 反向模式。
- 缺陷冲突从最终正向提示词移除，但不删除原始模型结果。
- 正向 TXT、正负 TXT 和结构化 JSON。
- 默认不覆盖；`--overwrite` 才允许原子替换。
- 默认 INFO 日志，`--verbose` 开启 DEBUG。

### 阶段 3：PySide6 桌面界面

- 单选、多选、拖放和剪贴板添加图片；拖入目录不会扫描。
- 每张图片使用稳定 UUID 和独立 `raw_tags`、`working_tags`、提示词状态。
- 受限线程池异步生成缩略图和当前预览，旧预览 token 不会覆盖新选择。
- 单一持久工作线程管理模型加载、释放和逐张推理队列。
- 取消会等待当前 ONNX 调用自然结束，然后阻止后续图片开始。
- 关闭窗口会等待推理线程与图片解码池实际退出，不强制终止后台任务。
- 标签表格支持搜索、类别/分组筛选、排序、勾选、编辑、添加、删除和恢复。
- 正反提示词可自动生成或手动编辑；标签变化不会静默覆盖手动文本。
- 当前图片可复制或导出正向 TXT、正负 TXT、JSON。
- JSON schema 2 区分模型 `raw_tags` 与用户 `working_tags`，并同时保留生成
  文本、最终文本和编辑标志。
- JSON 保存业务设置；`QSettings` 只保存窗口、分割条和表格列宽。
- GUI 日志写入滚动文件 `logs/animetagger-lite.log`，不记录完整提示词。

### 阶段 4：文件夹批处理与 LoRA 工作流

- 一个或多个源根；默认不递归，可选隐藏项、链接、文件数和深度上限。
- 扫描在现有持久 Worker 线程执行，只读扩展名/元数据，不批量解码图片。
- 同目录、镜像保留结构、扁平稳定哈希三种输出模式。
- `skip`、`overwrite`、`backup_and_overwrite`、`append_trigger`、`merge`
  五种已有 Caption 策略；默认 `skip`。
- 完整 `lora_caption`：无质量前缀、无反向词、Rating 默认关闭，Character
  可切换，trigger 可置首/置尾。
- 单一 ONNX Session 串行推理；当前项后暂停/取消，单项失败继续，默认最多
  重试一次。
- 逐图 TXT、正负 TXT、阶段 3 schema 2 JSON、CSV 和可选轻量摘要 JSON。
- 原子 Manifest，支持未完成任务发现、源缺失/输出缺失校验和显式恢复。
- GUI 独立“批处理”页和 `python -m app.main batch` CLI 共用
  `BatchService`。
- 图片永不删除、移动、重命名、覆盖或修改元数据；dry-run 完全不落盘。

数据处理边界见 [隐私与数据安全](docs/privacy-and-data-safety.md)。

## 阶段 5 历史模型准备与 1.0.0 真实验收

2026-07-30，Codex 曾按用户明确授权运行独立下载脚本，从官方
`SmilingWolf/wd-vit-tagger-v3` 的固定 revision
`7f6b584d0bd3f55c4531f14ba3d4761b2bccdc0f` 下载并验证：

```text
D:\tagger\models\wd-vit-tagger-v3\
├── model.onnx
└── selected_tags.csv
```

上面是当时的准备路径。清理旧文件后，当前本机已验证模型位于
`D:\AnimeTaggerLite-1.1.0-win64-cuda-portable\models\wd-vit-tagger-v3`；
本次源码开发只读取该位置，没有复制模型。

`model.onnx` SHA-256 与官方记录一致；真实
`CPUExecutionProvider` Session、448×448 NHWC 输入、10,861 个输出和
10,861 行 CSV 映射均已验证。`validation-images/` 中 6 张真实 PNG 的
CPU/CUDA 单图、GUI、多图队列和批处理验收均已通过；原图哈希保持不变。

Python 3.10 CPU、Python 3.11 CPU 与 Python 3.11 CUDA 三个隔离环境的完整自动
测试均为 395 passed、0 skipped。CPU 与 CUDA 的正式 1.0.0 ZIP 已在非源码工作
目录、清理后的 PATH、外置模型、中文/空格路径中完成真实隔离 Smoke；整个最终
`release` 目录已通过 Microsoft Defender 终扫。最终 1.0.0 发行证据见
[docs/real-model-validation.md](docs/real-model-validation.md) 和
[docs/release-smoke-report.md](docs/release-smoke-report.md)；阶段 5 的历史证据见
[tests/test_real_onnx_smoke.py](tests/test_real_onnx_smoke.py)。

## 环境

- Windows 10/11
- 目标环境 Python 3.11
- 当前代码同时兼容 Python 3.10
- 阶段 5 验收环境：Python 3.11.9（独立 CPU/CUDA 虚拟环境）
- CPU：`onnxruntime`
- 可选 NVIDIA GPU：`onnxruntime-gpu[cuda,cudnn]` 与兼容 NVIDIA 驱动

不需要 PyTorch、TensorFlow、完整 CUDA Toolkit、Node.js、Electron、Docker、
数据库或 Web 服务。

## 安装

### CPU 版

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt` 包含 PySide6，但不包含 QtWebEngine。UI 测试使用的
`pytest-qt` 只在 `requirements-dev.txt` 中。

### 可选 NVIDIA GPU 版

`onnxruntime` 与 `onnxruntime-gpu` 不应同时安装：

```powershell
python -m pip uninstall -y onnxruntime
python -m pip install -r requirements-gpu.txt
```

CUDA Provider 不可用时程序会提示并回退 CPU。

## Windows 便携版 1.0.0

阶段 5 使用 PyInstaller 6.21.0 的 `onedir` 模式分别构建 CPU 与 CUDA 包；
不使用 onefile 或 UPX。发行根目录包含 `AnimeTaggerLite.exe`、
`AnimeTaggerLiteCLI.exe`、`_internal/`、`resources/`、`models/README.txt`、
`LICENSES/`、`portable.flag` 和四个 `data/` 子目录。

正式发行根目录包含项目所有者确认的标准 MIT `LICENSE`，版权行为
`Copyright (c) 2026 yasneg`。第三方许可证清单与模型上游许可证保持独立，
不会被项目 MIT License 替代或重新授权。

模型和验证图片不会进入 ZIP。解压后可运行：

```powershell
.\AnimeTaggerLite.exe
.\AnimeTaggerLiteCLI.exe --version
.\AnimeTaggerLiteCLI.exe --help
```

正式 ZIP 与 SHA-256：

| 变体 | 文件 | SHA-256 |
|---|---|---|
| CPU | `AnimeTaggerLite-1.0.0-win64-cpu-portable.zip` | `efc21ba19da6205eeb2a166e89a1cc83ec9d742e53d9db37f962fff9296c2e7c` |
| CUDA | `AnimeTaggerLite-1.0.0-win64-cuda-portable.zip` | `83d5b6a56feab1d4dade2c74d7def3cabaf7df65b67f270a4ab66a5e5bd11ec8` |

机器可读构建信息与最终清单位于 `release/BUILD-REPORT-*.json` 和
`release/SHA256SUMS.txt`。

用户配置、日志、批任务元数据和剪贴板临时文件分别写入：

```text
data/config/
data/logs/
data/batch-jobs/
data/temp/
```

软件不会在启动、模型缺失、首次使用或后台任务中下载模型。普通用户可显式运行
下文的模型准备脚本；Codex 在本次阶段 5 验收中也实际运行了同一脚本。模型
不会进入发行 ZIP，删除 `models/` 不会影响用户图片、Caption 或导出结果。

开发者可在两个隔离环境中重复构建：

```powershell
.\.venv311-cpu\Scripts\python.exe scripts\build_portable.py --variant cpu --clean --archive
.\.venv311-cuda\Scripts\python.exe scripts\build_portable.py --variant cuda --clean --archive
```

PyInstaller 只属于构建环境，不是正式运行依赖，也不会加入
`requirements.txt` 或 `requirements-gpu.txt`。

## GUI

启动：

```powershell
python -m app.ui
```

查看入口参数或执行自动关闭的无模型启动检查：

```powershell
python -m app.ui --help
python -m app.ui --smoke-test
```

启动 UI 不会自动加载模型、联网或扫描磁盘。默认模型目录是
`models/wd-vit-tagger-v3`；缺少文件时窗口仍会打开，并明确显示缺少
`model.onnx` 与 `selected_tags.csv`。

### 基本使用

1. 用“添加图片”、拖放或“粘贴图片”加入一张或多张图片。
2. 打开“设置”，选择模型目录和 `auto`、`cpu` 或 `cuda`。
3. 先“验证模型”，再“加载模型”。基础验证不打开完整 ONNX；加载时会检查
   ONNX 可读性、输入形状和 CSV/输出数量。
4. 在左侧用 Ctrl/Shift 选择多张图片，点击“开始识别”。队列始终逐张执行。
5. 在标签表中搜索、筛选、勾选或编辑；修改只更新当前图片，不重新推理。
6. 切换 `raw`、`anime`、`pony`、`krea2`、`lora_caption` 或反向模式。快捷阈值使用
   当前 `working_tags` 立即重建，不更改 `raw_tags`。
7. 可手动编辑提示词。后续标签/设置变化只标记“可重新生成”，不会静默覆盖。
8. 复制提示词，或用“导出当前”选择正向 TXT、正负 TXT、JSON。

重新识别含手动编辑的图片会先确认；确认后以新模型结果覆盖该图片的
`working_tags` 和最终提示词。导出默认拒绝覆盖，只有在文件已存在的确认框中
明确选择“覆盖”才传递 `overwrite=True`。

### 批处理页

1. 切换到“批处理”，添加一个或多个文件夹。
2. 选择是否递归、输出模式、Profile/LoRA、trigger、阈值和导出格式。
3. 点击“扫描 / Dry-run 预览”。这一步不加载模型、不推理、不创建任何输出。
4. 在预览表搜索或按状态/已有 Caption 筛选；可以全选、全不选、反选或移除
   任务项。设置变化后必须重新扫描，避免预览与执行语义不一致。
5. 预览区明确显示总数、已有 Caption、预计跳过和输出路径。修改已有 Caption
   的策略会在开始前显示受影响数量并二次确认。
6. 回到单图页加载模型，再在批处理页开始。单图队列和批处理共用一个 Worker
   与 Session，不能并行启动。
7. 暂停/取消会等待当前同步 ONNX 调用自然结束。完成或取消后可重试失败项、
   导出报告、查看 Manifest，或只清除内存任务。

输出模式：

- `beside`：`001.png` → 同目录 `001.txt`，适合 LoRA 数据集。
- `mirror`：在独立输出根下保留安全相对目录。
- `flat`：所有输出在一个目录，同名使用稳定短哈希。

Caption 策略：

- `skip`：默认；已有输出直接跳过且不推理。
- `overwrite`：确认后原子替换。
- `backup_and_overwrite`：先成功写出 `.bak`/`.bak.N` 再覆盖。
- `append_trigger`：只向已有 Caption 开头插入未重复的 trigger。
- `merge`：已有逗号标签优先，与新识别标签稳定去重。

应用启动时只会提示在已知最近目录发现的未完成 Manifest，不会自动开始恢复。
也可使用“打开 Manifest”手动查看和恢复。

### 模型与设备状态

目录选择后的“验证”只检查目录、两个必要文件、CSV 和可用 Provider；不会占用
完整模型内存。“加载模型”在后台线程完成 ONNX 图、输入输出和标签数量校验。
候选模型加载失败时，已加载的旧 Session 不会被破坏。

界面显示的是 ONNX Runtime 的实际 Provider。选择 CUDA 但不可用或初始化失败
时，会显示回退原因和实际的 `CPUExecutionProvider`，不会只显示用户期望值。

## 主动准备 WD14 模型

项目提供标准库脚本，只从官方仓库固定 revision 下载：

1. `model.onnx`
2. `selected_tags.csv`

普通用户可主动运行：

```powershell
python scripts/download_wd14_model.py
python scripts/download_wd14_model.py --verify-only
python scripts/download_wd14_model.py --output-dir "D:\models\wd14"
```

`--force` 会明确重新下载两个文件；现有有效文件在新文件完成校验前保持不变。
脚本使用 `.part`、断点续传/重试、SHA-256、CSV 结构和真实 ONNX Session
校验。无效旧文件会保留为 `.invalid`，不会直接删除。

此脚本不会自动运行。软件启动、后台任务、模型加载失败和更新检查均不会联网，
项目也没有加入 `huggingface_hub` 或其他永久网络运行时依赖。模型文件不会进入
发行 ZIP。删除标准模型目录不会影响位于数据集目录中的用户图片与 Caption；
只会使下次模型加载显示缺少文件。

## CLI

查看参数：

```powershell
python -m app.main --help
```

### 默认 raw 提示词

```powershell
python -m app.main "D:\images\sample.png" `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3"
```

默认只显示模型、Provider、推理耗时和最终正向提示词；不倾倒全部原始标签，
不写文件，反向模式为 `none`。

### Anime profile

```powershell
python -m app.main "D:\images\sample.png" `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3" `
  --profile anime `
  --underscore-to-space
```

默认可添加：

```text
masterpiece, best quality, amazing quality
```

使用 `--no-profile-prefix` 可以关闭。

### Pony profile

```powershell
python -m app.main "D:\images\sample.png" `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3" `
  --profile pony
```

Pony 默认前缀为空，不假定某套质量词永远正确。可在
`resources/prompt_profiles.json` 中编辑。

### Krea 2 自然语言提示词

`krea2` profile 不输出传统的逗号标签流，也不添加 `masterpiece`、
`best quality` 等质量套话。它将检测到的标签按以下顺序重组为英文自然语言段落：

```text
主体 → 外貌/服装 → 动作/表情 → 构图 → 环境 → 光线 → 色彩 → 风格/材质/景深
```

生成器只在内容描述中陈述实际保留的 WD14 标签；结尾会增加适合 Krea 2 的
光影、色彩关系、笔触、边缘控制、材质和焦点层级指导。它不是视觉语言模型，
不会凭空补写模型未检测到的具体道具或场景关系，生成后仍可在界面中手动编辑。

```powershell
python -m app.main "D:\images\sample.png" `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3" `
  --profile krea2 `
  --underscore-to-space
```

Krea 2 通常可以先不使用反向提示词。前端确实需要时，可选择项目提供的短预设：

```powershell
python -m app.main "D:\images\sample.png" `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3" `
  --profile krea2 `
  --negative-mode basic `
  --negative-preset krea2_short
```

该短预设仅包含 `extra limbs`、`malformed hands`、`duplicated subjects`、
`text` 和 `watermark`，不会自动塞入冗长的传统 SD 反向词表。

### CyberIllustrious Semi-Realistic 标签提示词

cyberillustrious_semireal 仍使用同一 WD ViT Tagger v3 的 General、
Character 与 Rating 识别结果，不重新识图。它将保留的标签按主体、角色、
外貌、表情、服饰、动作、构图、环境的顺序重排，按置信度消解冲突的取景标签，
过滤模型自动产生的 Pony 评分词和质量词，并在末尾根据实际识别内容加入少量
半写实材质、光照与镜头词。用户手动输入的评分标签不会被自动删除。

~~~powershell
python -m app.main "D:\images\sample.png" --model-dir "D:\AnimeTaggerLite-1.1.0-win64-cuda-portable\models\wd-vit-tagger-v3" --profile cyberillustrious_semireal --underscore-to-space
~~~

基本人物示例（各视觉词均来自识别标签）：

~~~text
1girl, solo, black hair, long hair, brown eyes, smile, white shirt, standing, upper body, indoors, semi-realistic, natural skin texture, detailed eyes, detailed hair, detailed fabric texture, cinematic lighting, depth of field
~~~

无人风景不会增加皮肤、眼睛、头发或服装材质词；可信的平面动漫风格标签会
保留，且不会同时堆积冲突的摄影风格与镜头词。明显硬光或夜景不会被强行改成
柔光。此阶段固定使用适中的半写实增强强度，没有新增 Low/High 控件。

反向提示词继续遵循原来的 none、basic 和 cleanup_detected：none 完全不输出；
选择 basic 且预设仍为默认 basic 时，Cyber profile 自动使用
cyberillustrious_short 短预设；cleanup_detected 再按原有缺陷白名单和阈值
追加真实检测到的问题。显式选择其他反向预设仍会受到尊重，低置信度标签不会
被取反。

~~~powershell
python -m app.main "D:\images\sample.png" --model-dir "D:\AnimeTaggerLite-1.1.0-win64-cuda-portable\models\wd-vit-tagger-v3" --profile cyberillustrious_semireal --negative-mode basic
~~~

GUI 的单图页与设置对话框可选“CyberIllustrious 半写实”；批处理页需先关闭
“LoRA Caption 模式”再选择该 profile。切换单图 profile 会使用已有
working_tags 重建提示词，不会重新运行 ONNX。软件仍完全离线，模型与
用户图片不会被复制到源码或发行 ZIP。

### 单图 LoRA caption

```powershell
python -m app.main "D:\images\sample.png" `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3" `
  --profile lora_caption `
  --trigger-word "my_character" `
  --remove-tag solo `
  --remove-tag "simple background" `
  --underscore-to-space
```

`lora_caption` 不添加质量词，也强制不生成反向提示词。单图命令保持原有
兼容；阶段 4 的文件夹命令如下。

### 文件夹 batch 与 dry-run

查看参数：

```powershell
python -m app.main batch --help
```

先预览。默认不递归、不覆盖，且 dry-run 不加载模型、不推理、不创建目录或
文件：

```powershell
python -m app.main batch "D:\dataset" `
  --recursive `
  --lora `
  --trigger-word "style_token" `
  --dry-run
```

生成同名 LoRA Caption 和 CSV：

```powershell
python -m app.main batch "D:\dataset" `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3" `
  --lora `
  --trigger-word "style_token" `
  --remove-tag solo `
  --existing-caption skip `
  --export txt `
  --export csv
```

镜像输出并同时生成逐图 JSON：

```powershell
python -m app.main batch "D:\dataset" `
  --recursive `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3" `
  --output-mode mirror `
  --output-root "D:\tagger-output" `
  --export txt `
  --export json `
  --export csv
```

修改已有 Caption 必须显式确认：

```powershell
python -m app.main batch "D:\dataset" `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3" `
  --existing-caption backup_and_overwrite `
  --yes
```

恢复不会自动开始；指定 Manifest 后才运行：

```powershell
python -m app.main batch `
  --resume "D:\tagger-output\.animetagger\batch-ID.manifest.json" `
  --retry-failed `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3"
```

退出码：0 成功/dry-run，1 部分失败，2 配置/Manifest，3 模型/Provider，
4 取消，5 未预期内部错误。

### 阈值、排除和诊断

```powershell
python -m app.main "D:\images\sample.png" `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3" `
  --general-threshold 0.35 `
  --character-threshold 0.75 `
  --rating-threshold 0.50 `
  --no-include-rating `
  --max-tags 80 `
  --exclude-tag watermark `
  --show-confidence `
  --show-category `
  --show-raw-tags
```

`--show-raw-tags` 保留阶段 1 的 Rating/General/Character 分组诊断视图。

## 正向提示词 profile

- `raw`：只使用过滤、规范化和去重后的标签，按置信度稳定排序。
- `anime`：可选质量前缀，然后按 16 个标签组排序。
- `pony`：可编辑前缀，默认空。
- `krea2`：把检测标签重组为分段自然语言，并补充构图、光影、色彩、笔触、
  材质、焦点层级和景深方向；不添加传统质量套话。
- `cyberillustrious_semireal`：重排识别标签、消解相互矛盾的取景和
  风格词，按人物/场景内容增加克制的半写实材质、光照和镜头描述。
- `lora_caption`：不加质量词；保留人物、外貌、服装、动作、表情和场景相关
  标签；支持 trigger word 和固定标签删除。

除 `krea2` 外的 profile 以英文逗号加空格分隔，不产生空标签、重复逗号或
尾逗号。`krea2` 输出可直接编辑和导出的英文自然语言段落。

## 反向提示词原则

### none

不生成反向提示词。

### basic

只读取用户选择的 JSON 预设：

```powershell
python -m app.main "D:\images\sample.png" `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3" `
  --negative-mode basic `
  --negative-preset basic
```

### cleanup_detected

在基础预设之外，只加入模型**实际返回且达到缺陷阈值**的缺陷白名单标签：

```powershell
python -m app.main "D:\images\sample.png" `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3" `
  --negative-mode cleanup_detected `
  --negative-preset quality_only
```

低置信度标签不能取反，因为低分只表示模型没有足够证据确认该标签，并不表示
图片中一定不存在对应元素。未出现标签、低分标签和大量 `bad hands` 套话都
不会被自动加入。

真实检测到的缺陷会从最终正向提示词移除并记录冲突，但原始 `TagResult`
保持不变。

## 导出

### 仅正向 TXT

```powershell
python -m app.main "D:\images\sample.png" `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3" `
  --output-format txt `
  --output "D:\outputs\sample.txt"
```

内容：

```text
1girl, solo, long hair
```

### 正负 TXT

```powershell
python -m app.main "D:\images\sample.png" `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3" `
  --negative-mode basic `
  --output-format prompt-txt `
  --output "D:\outputs\sample-prompts.txt"
```

格式：

```text
Positive:
1girl, solo, long hair

Negative:
low quality, worst quality, blurry
```

### JSON

```powershell
python -m app.main "D:\images\sample.png" `
  --model-dir "D:\tagger\models\wd-vit-tagger-v3" `
  --profile anime `
  --negative-mode cleanup_detected `
  --output-format json `
  --output "D:\outputs\sample.json"
```

JSON 包含 schema 版本、源路径、模型路径、Provider、推理耗时、生成时间、
阈值、profile、raw/filtered/removed 标签、缺陷和最终正反提示词，不含图片
或模型二进制。

schema 2 新增：

- `generated_positive_prompt` / `generated_negative_prompt`
- `final_positive_prompt` / `final_negative_prompt`
- `prompt_was_edited`

兼容字段 `positive_prompt` / `negative_prompt` 仍保留，并表示实际导出的最终
文本。

默认不覆盖已有文件。确认覆盖时显式增加：

```text
--overwrite
```

写入使用同目录临时文件和原子提交；失败不会破坏已有文件。

## 配置和自定义预设

| 文件 | 用途 |
|---|---|
| `resources/default_settings.json` | 程序默认配置 |
| `config/settings.json` | 业务设置与最近目录 |
| `resources/prompt_profiles.json` | raw/anime/pony/krea2/CyberIllustrious/lora_caption |
| `resources/negative_presets.json` | 反向预设与缺陷白名单 |
| `resources/tag_categories.json` | 16 组轻量分类规则 |

JSON 使用 UTF-8。缺少配置字段时继承默认值，未知字段忽略。用户配置损坏或
字段类型错误时，程序保留原文件、记录 WARNING 并使用默认值。

窗口尺寸、位置、分割条和标签表列宽由 Qt 的 `QSettings` 保存，不写入业务
JSON。业务 JSON 使用同目录临时文件和 `os.replace` 原子提交。

分类规则 JSON 损坏时回退到很小的内置规则，不会把庞大的分类数据库硬编码
到 UI 或 CLI。

## 日志

- 默认控制台级别：INFO。
- `--verbose`：DEBUG。
- GUI：`logs/animetagger-lite.log`，单文件上限 3 MiB，保留 3 个历史文件。
- 配置回退和导出错误会记录。
- 日志不默认记录完整正向/反向提示词，不记录图片内容，不上传。

## 测试

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app tests scripts
python -m pip check
```

无显示器的 GUI 测试可以设置：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
```

2026-08-03 的最终发行补充回归在 Python 3.10 CPU、Python 3.11 CPU 和
Python 3.11 CUDA 三个隔离环境中均为 `395 passed, 0 skipped`。测试环境显式
配置本地模型和
`validation-images/`，因此真实 WD14 结构与真实动漫图片 Smoke 均实际执行，
没有使用 Mock 代替。

### Python 3.11 验证命令

阶段 5 使用 python.org 官方 Python 3.11.9 x64 安装程序建立
`.venv311-cpu/` 与 `.venv311-cuda/`，没有替换 Python 3.10/3.13 或全局 PATH。
可按下列命令重复验证：

```powershell
py -3.11 -m venv .venv311-cpu
.\.venv311-cpu\Scripts\python.exe -m pip install --upgrade pip
.\.venv311-cpu\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv311-cpu\Scripts\python.exe -m pip check
.\.venv311-cpu\Scripts\python.exe -m compileall -q app tests scripts
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv311-cpu\Scripts\python.exe -m pytest -q
.\.venv311-cpu\Scripts\python.exe -m app.main --help
.\.venv311-cpu\Scripts\python.exe -m app.ui --help
.\.venv311-cpu\Scripts\python.exe -m app.ui --smoke-test
```

### 真实 ONNX 图 smoke

模型位于默认目录时：

```powershell
python -m pytest -m smoke -v
```

其他模型目录：

```powershell
$env:ANIMETAGGER_MODEL_DIR = "D:\models\wd-vit-tagger-v3"
python -m pytest -m smoke -v
```

### 最终真实动漫图 CLI 验收

测试图片不提交仓库：

```powershell
$env:ANIMETAGGER_MODEL_DIR = "D:\models\wd-vit-tagger-v3"
$env:ANIMETAGGER_VALIDATION_IMAGE = "D:\tagger\validation-images\anime-test.png"
python -m pytest -m smoke -v -s
```

也可以让测试按文件名顺序选取验证目录中的第一张受支持图片：

```powershell
$env:ANIMETAGGER_MODEL_DIR = "D:\models\wd-vit-tagger-v3"
$env:ANIMETAGGER_VALIDATION_DIR = "D:\tagger\validation-images"
python -m pytest -m smoke -v -s
```

`ANIMETAGGER_VALIDATION_IMAGE` 优先于
`ANIMETAGGER_VALIDATION_DIR`；旧变量 `ANIMETAGGER_TEST_IMAGE`
仍兼容。配置的文件或目录不存在时测试会失败，以避免误验其他图片；未配置真实
图片时语义测试会明确跳过。测试不会扫描其他目录、联网下载或修改验证图片，也
不会用 Mock 冒充。

## 主要结构

```text
app/
├── portable_entry.py
├── runtime_paths.py
├── main.py
├── batch_cli.py
├── export_service.py
├── batch/
│   ├── models.py
│   ├── scanner.py
│   ├── paths.py
│   ├── atomic.py
│   ├── exporter.py
│   ├── manifest.py
│   └── service.py
├── services/
│   ├── tagging_service.py
│   └── clipboard_service.py
├── state/
│   ├── image_item.py
│   └── project_state.py
├── ui/
│   ├── application.py
│   ├── main_window.py
│   ├── batch_panel.py
│   ├── batch_table_model.py
│   ├── batch_filter_proxy.py
│   ├── settings_dialog.py
│   ├── tag_table_model.py
│   ├── tag_filter_proxy.py
│   └── workers/
├── config/
│   ├── settings.py
│   └── presets.py
├── image/
│   └── image_loader.py
├── inference/
│   ├── model_loader.py
│   ├── providers.py
│   └── wd14_engine.py
└── prompts/
    ├── models.py
    ├── normalizer.py
    ├── filtering.py
    ├── tag_classifier.py
    ├── positive_builder.py
    ├── negative_builder.py
    └── pipeline.py
resources/
config/
scripts/
├── download_wd14_model.py
└── build_portable.py
packaging/
├── animetagger-lite.spec
├── build_common.ps1
├── build_cpu.ps1
├── build_cuda.ps1
├── clean.ps1
├── README.portable.txt
├── MODEL_README.txt
├── LICENSES_README.txt
├── requirements-cpu.lock.txt
└── requirements-cuda.lock.txt
tests/
docs/privacy-and-data-safety.md
docs/tagger-backends.md
```

## 常见错误

### 缺少模型文件

确认 `--model-dir` 指向包含同版本 `model.onnx` 与 `selected_tags.csv` 的目录。

### 标签数量和模型输出数量不一致

模型和 CSV 来自不同版本。重新从同一官方修订准备两个文件。

### CUDAExecutionProvider 不可用

确认没有同时安装 CPU/GPU 两个 Runtime：

```powershell
python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

也可使用 `--device cpu`。

### 导出文件已存在

默认拒绝覆盖。确认目标无误后使用 `--overwrite`。

批处理默认 `--existing-caption skip`。修改已有 Caption 应先运行
`--dry-run` 查看数量，再使用目标策略和 `--yes`。CSV/汇总报告也默认不覆盖。

### batch 输出目录无效

`mirror` 和 `flat` 必须提供 `--output-root`。输出相对路径不能包含 `..`；
程序还会在 resolve 后校验目标始终位于输出根内。输出根若位于源目录中，会从
扫描中排除，避免重新处理输出。

### Manifest 无法恢复

截断 JSON、未知 schema 或缺少必要字段会被拒绝，不会猜测执行。源图被删除会
标记 `missing`；已完成输出消失会回到 `pending`。恢复从不自动开始推理。

### JSON 配置回退

查看 WARNING 中的具体字段或 JSON 解析错误。原用户配置不会被静默重写。

### 标签中包含逗号

逗号是提示词分隔符。GUI 的单行标签编辑会将中英文逗号安全替换为空格，避免
一行意外注入多个提示词 token；CLI 和阶段 2 管线仍执行原有严格规范化。

### 取消不是立即中断当前图片

ONNX Runtime 的同步 `run()` 不能安全强制终止。点击取消后界面显示“正在完成
当前图片后取消”，当前调用自然返回后不会再启动下一张。程序不调用
`QThread.terminate()`。

## 当前未实现

- 安装程序。
- 自动更新。
- 成品自动模型下载（独立的用户主动准备脚本不等同于自动下载）。
- 多模型支持。
- 自然语言图片描述。
- ComfyUI、A1111、Forge 等第三方绘图软件联动。
- 自动 LoRA 训练。
- 文件系统实时监控。
- 代码签名。

第三方依赖与许可证见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 许可证

AnimeTagger Lite 项目自身采用 MIT License：
`Copyright (c) 2026 yasneg`。完整、未经修改的许可条款见 [LICENSE](LICENSE)。
随包第三方依赖继续分别遵守 `LICENSES/` 和
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 中记录的上游许可证；本项目
MIT License 不会替代、覆盖或重新授权这些组件。WD ViT Tagger v3 模型不进入
发行 ZIP，并继续独立遵守其上游许可证。


### 可切换模型后端

源码已增加默认 WD EVA02 2026 Canary、可选 PixAI v0.9 和旧 WD v3 后端。模型文件、可选依赖、配置兼容、GUI/CLI 使用与验证方法见 [多后端说明](docs/tagger-backends.md)。已有便携包不随源码自动更新。
