# 可切换 Tagger 后端

应用默认后端为 `wd_2026_canary`。不联网推理，不自动下载模型，不执行远程模型代码。
现有 WD v3 ONNX 文件仍可使用，包括项目原来的 **WD ViT v3**；不能把这份权重的实测结果称为 EVA02 v3 的结果。

| 后端 | 本地目录约定 | 路线 | General | Character | Rating | Top K |
|---|---|---|---:|---:|---:|---:|
| `wd_v3` | `models/wd-vit-tagger-v3` | 原 WD ONNX Runtime | 0.35 | 0.75 | 0.50 | 不额外限制 |
| `wd_2026_canary` | `models/wd-eva02-tagger-2026-canary` | PyTorch / timm | 0.35 | 0.75 | 0.50 | 不额外限制 |
| `pixai_v0_9` | `models/pixai-tagger-v0.9` | deepghs ONNX 转换版 | 0.30 | 0.75 | 不提供 rating 预测 | 128 |

WD 阈值延续项目经验值；Canary 作者给出的验证集 P=R 点是 0.6094，不等同于当前应用的高召回设置。PixAI Character=0.75 按本次需求设置；转换仓库建议值为 0.85。这些是初始操作阈值，不是准确率承诺。

`top_k` 是**分组阈值、黑名单、去重等过滤之后**的额外上限，与原来的 `max_tags` 取较小值。`max_tags` 默认仍为 80，因此 PixAI 默认也不会把 128 个标签全部塞进 prompt。完整 raw 分数保留，不受此上限裁剪。原有人工保留、清理、负向和 profile 逻辑继续使用。

## 模型文件及来源

**WD v3**：`model.onnx` + `selected_tags.csv`。兼容原来的 NHWC、BGR、0–255 float32 WD ONNX 模型。

**Canary**：从 [ashen-sensored 官方模型仓库](https://huggingface.co/ashen-sensored/wd-eva02-tagger-2026-canary)取得 `model.safetensors`、`selected_tags.csv`、`config.json`，放在同一个目录。当前官方仓库没有 ONNX 权重。使用固定的 `eva02_large_patch14_448` 架构、`pretrained=False`、本地 safetensors 严格加载，避免自动下载基座。图像补成方形，bicubic 到 448，BGR NCHW，归一化至 [-1,1]，最后 sigmoid。预处理依据作者引用的 [wdv3-timm 实现](https://github.com/neggles/wdv3-timm/blob/main/wdv3_timm.py)。

只使用 Canary 时需要额外安装：

```powershell
python -m pip install -r requirements-tagger-torch.txt
```

按自己的平台安装对应 CPU/CUDA PyTorch。Canary 的 `auto` 根据 PyTorch 的 CUDA 可用性选择设备；显式 CUDA 不可用时给出 CPU 回退提示。实际 CUDA 初始化或显存错误会明确报错。原 ONNX 的 CUDA/CPU 选择与回退机制继续保留。两种 runtime 的设备可用性互相独立。

**PixAI**：使用 [deepghs/pixai-tagger-v0.9-onnx](https://huggingface.co/deepghs/pixai-tagger-v0.9-onnx) 中配套的 `model.onnx` 与 `selected_tags.csv`。`preprocess.json` 可一起保存供溯源；适配器按该转换版固定预处理执行：RGB，直接 bilinear resize 到 448，不补方形，NCHW [-1,1]。仅读取已 sigmoid 的 `prediction` 输出，忽略 embedding/logits，避免二次 sigmoid。

[PixAI 原始仓库](https://huggingface.co/pixai-labs/pixai-tagger-v0.9) 的原生文件在此次环境访问返回 HTTP 401。本实现不直接加载 `model_v0.9.pth` / `tags_v0.9_13k.json`；公开 ONNX 转换版是明确的替代路线，不是原生 PyTorch 权重的透明替换。不要将两种格式混放后期待自动转换。

PixAI general/character 来自 CSV category；copyright 从 CSV 的原生 `ips` 映射派生，同名作品取最高支持角色分数，使用 Character 阈值。**作品分数是推导分数，不是独立分类器概率**。没有映射时 copyright 为空并提示；映射损坏会报错。PixAI 不凭空生成 rating。

三种后端统一返回现有 `InferenceResult` / `TagPrediction` / `TagMetadata`。`result.grouped` 提供 `general / character / rating / copyright / raw / other`，不支持的组为空。后端内规范化空白及 Danbooru 下划线格式、校验分数、按组和名字去重取最高分、按分数排序。原始模型 index 保留，作品映射项是新增派生项。PixAI CSV 的第 8968 号输出没有名称：保留该行参与输出对齐，仅在得到分数后从标准标签结果中忽略，绝不提前删除 CSV 行。JSON 导出追加 `backend` 字段。

## 配置兼容与 GUI

配置仍为现有 JSON，新增 `backend`、`top_k`、`backend_options`，不更改 schema/version。旧配置缺少 `backend` 时采用 Canary；旧 `model_dir` 和显式阈值保持原值。**若旧路径指向 ONNX，请在 GUI 选择 WD v3 后配置/加载原目录，或选择 Canary 的新路径。**不把旧 ONNX 冒充 Canary。

现有 `general_threshold`、`character_threshold`、`rating_threshold`、`max_tags` 等字段保持名称与含义。配置、清单读取使用 `AppSettings.from_mapping()` 应用后端默认值；程序内切换使用 `select_backend()`。显式用户阈值优先于默认值。

设置窗口新增模型后端选择器和 Top K（0 表示不额外限制），切换时恢复该后端的路径和阈值，保存进 `backend_options`。新后端使用自己的默认目录及阈值。模型仍需点击“加载模型”完成切换；候选加载失败保留旧模型，选择与已加载后端不一致时明确阻止误用。

```json
{
  "backend": "pixai_v0_9",
  "model_dir": "models/pixai-tagger-v0.9",
  "general_threshold": 0.30,
  "character_threshold": 0.75,
  "rating_threshold": 0.50,
  "top_k": 128,
  "max_tags": 80,
  "backend_options": {
    "wd_2026_canary": {
      "model_dir": "models/wd-eva02-tagger-2026-canary",
      "general_threshold": 0.35,
      "character_threshold": 0.75,
      "rating_threshold": 0.50,
      "top_k": null
    }
  }
}
```

## CLI

```powershell
python -m app image.png --tagger-backend wd_2026_canary --profile anime
python -m app image.png --tagger-backend pixai_v0_9 --threshold-general 0.30 --threshold-character 0.75 --threshold-rating 0.5 --top-k 128
python -m app image.png --tagger-backend wd_v3 --model-dir models/wd-vit-tagger-v3
python -m app batch images --tagger-backend pixai_v0_9 --top-k 128 --dry-run
```

新阈值参数是旧 `--general-threshold / --character-threshold / --rating-threshold` 的别名。旧参数继续有效。省略 `--model-dir` 使用配置路径；提供时覆盖本次执行路径。CLI 不自动保存设置。

旧命令在未指定后端、当前配置为默认 Canary、且显式 `--model-dir` 已含 `model.onnx` 时，以 WD v3 兼容执行并打印提示；选择 PixAI 等新模型时建议始终显式使用 `--tagger-backend`。已配置 PixAI 的命令不会被此兼容规则覆盖。

## 可重复验证

```powershell
$env:ANIMETAGGER_VALIDATION_DIR = 'D:\tagger\validation-images' # 换成自己的图片目录
python -m pytest -q
python scripts/smoke_tagger_backends.py --images validation-images --output logs/backend-smoke-final.json --device cpu
```

smoke 脚本只读取本地图片和模型，记录每图阈值后数量、角色结果、general 前 20 项、五种 prompt 模式标签数量和耗时。WD v3 会与原 `WD14Engine` 对同图逐项比较五种 prompt 的正向文本，差异使脚本失败。任何模型缺失/失败都会写入报告并返回非零退出码。

样本来源：用户已有 7 张本地图片；[PixAI 转换仓库 sample.webp](https://huggingface.co/deepghs/pixai-tagger-v0.9-onnx/blob/main/sample.webp)（胡桃角色样本）；[MountainLandscape.jpg](https://commons.wikimedia.org/wiki/File:MountainLandscape.jpg)，作者 Aless0Mu，CC BY 1.0；[长离头像](https://github.com/ryanbenson/wuthering-waves-assets/blob/master/images/Changli.png)为社区收集的鸣潮游戏素材，原作品属 Kuro Games，仅用于本地模型验收。样本没有上传到任何推理服务，也没有作为项目源代码提交。

本次没有改动 LICENSE、版本号或打包系统；已有便携 EXE 不会自动包含源码变更及可选 PyTorch 依赖，需要另行授权的打包任务。
