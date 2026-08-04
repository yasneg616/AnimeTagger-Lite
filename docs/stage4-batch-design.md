# AnimeTagger Lite 阶段 4 批处理设计

本文对应 0.4.0。阶段 4 在不改变 WD14 单图推理语义的前提下，增加文件夹
批处理、LoRA Caption、CSV/JSON 报告和轻量恢复。阶段 5 的 Windows 打包不在
本文范围内。

## 设计目标

- GUI 与 CLI 复用同一个 `BatchService`。
- 继续复用阶段 3 的单一持久推理线程和 `TaggingService`/`WD14Engine` Session。
- 扫描不解码图片；默认不递归、不跟随链接、不包含隐藏项。
- 默认不覆盖已有 Caption。
- 图片始终只读，输出使用临时文件和原子替换。
- 单图失败不阻塞后续条目；暂停、取消只在当前同步 ONNX 调用结束后生效。
- Manifest 可以识别未完成任务，但绝不自动开始恢复推理。

## 组件与职责

```text
CLI parser ─┐
            ├─ BatchService ─ Scanner / OutputPlanner / Writer / ManifestStore
BatchPanel ─┘       │
                    └─ TaggingService ─ WD14Engine (一个持久 Session)
```

- `app/batch/models.py`：可序列化枚举、扫描选项、不可变批处理配置、Job/Item。
- `app/batch/scanner.py`：有界、多根目录、可取消文件发现；复用图片加载器扩展名表。
- `app/batch/paths.py`：镜像/扁平/同目录规划、重名哈希和 containment 校验。
- `app/batch/exporter.py`：Caption 策略、逐图 JSON、CSV 和摘要 JSON。
- `app/batch/manifest.py`：原子 Manifest、损坏拒绝、未完成任务发现和恢复准备。
- `app/batch/service.py`：串行状态机、推理/导出隔离、暂停/取消、失败重试。
- `app/batch_cli.py`：`anime-tagger batch` 参数和退出码；不复制业务逻辑。
- `app/ui/batch_panel.py`：独立批处理页；不从 Worker 弹窗。
- `app/ui/workers/inference_worker.py`：单图队列、扫描和批处理共享同一个 QThread。

`BatchService` 不导入 Qt。Worker 不导入 QWidget。GUI 不启动 CLI 子进程，也不
解析 CLI 输出。

## 数据模型

`BatchJob` 保存 UUID、时间、扫描选项、输出配置、深拷贝的 `AppSettings`、
条目、统计、警告、Manifest/报告路径和任务状态。任务状态包括：

`created`、`scanning`、`ready`、`running`、`pausing`、`paused`、
`cancelling`、`cancelled`、`completed`、`completed_with_errors`、`failed`。

`BatchItem` 使用源绝对路径生成稳定 UUID5，不以文件名作为唯一键。它保存：

- 源根目录、相对路径、格式和文件大小；
- 是否选中、Caption/JSON/备份路径；
- `pending`、`analyzing`、`exporting`、`completed`、`skipped`、`failed`、
  `cancelled`、`missing` 等状态；
- 尝试/重试次数、错误类型和简短错误信息；
- 模型名、实际 Provider、推理/总耗时、开始/完成时间；
- 最终正反提示词和轻量标签摘要。

Manifest 不保存图片、模型或完整置信度数组。运行期若导出失败，
`BatchService` 最多缓存最近 8 条待重试 `AnalysisResult`；成功导出会立即
释放缓存。缓存命中时重试不需要再次推理，较早条目被逐出或进程重启后则
安全地重新推理。

## 扫描

默认值为：

- `recursive=false`
- `include_hidden=false`
- `follow_symlinks=false`
- `max_files=100000`
- `max_depth=64`

扫描使用 `os.scandir` 返回的路径包装为 `pathlib.Path`，只检查扩展名和文件
元数据，不调用 Pillow。支持格式直接引用
`app.image.image_loader.SUPPORTED_IMAGE_EXTENSIONS`。

路径去重同时使用大小写规范化后的 resolved path 和可用时的
`(st_dev, st_ino)`，覆盖重叠根、链接和硬链接。跟随目录链接时记录目录
identity，避免 junction/symlink 循环。单目录权限错误、路径错误会汇总为警告，
不会中止其他根。输出根目录被显式排除，避免把输出中的图片重新扫描。

GUI 将扫描请求排入现有持久 QThread，所以主线程保持响应。取消标志是
`threading.Event`，可以在 Worker 正忙时从 GUI 线程安全设置。

## 输出路径

三种模式：

1. `beside`：`image.png` 对应同目录 `image.txt`/`image.json`。
2. `mirror`：将安全相对路径拼到 `output_root`；多根目录增加唯一根标签。
3. `flat`：输出到一个目录；同 stem 冲突时加稳定 SHA-256 短哈希。

相对路径不得为空、绝对、含 drive 或 `..`。镜像/扁平目标在 resolve 后用
`os.path.commonpath` 再次验证始终位于 `output_root`。Windows 非法字符和
`CON`、`AUX`、`COM1` 等保留名会被稳定替换。任何 TXT/JSON 目标若与源图片
resolve 到同一路径，任务在写入前即被拒绝。

## Caption 策略

- `skip`：默认。任一启用的逐图输出已存在时跳过，不推理、不写入。
- `overwrite`：原子替换；CLI 需要 `--yes`，GUI 显示受影响数并二次确认。
- `backup_and_overwrite`：先原子写出 `.bak`、`.bak.1`……，备份失败则旧
  Caption 保持不变。
- `append_trigger`：只在已有 Caption 前插入触发词；规范化去重，保留其余文本。
- `merge`：触发词、已有逗号标签、新识别标签按稳定顺序合并；空白/下划线规范
  后去重，不做语义改写。

`append_trigger` 和 `merge` 只适用于普通逗号 TXT，不适用于正负 Prompt TXT。
空正向 Caption 会被拒绝，不创建 0 字节或空白 Caption。

## LoRA Caption

`--lora` 或 GUI LoRA 开关使用 `lora_caption` profile：

- 不加入 `masterpiece`、`best quality` 等质量前缀；
- 强制有效反向模式为 `none`；
- Rating 默认关闭；
- Character 可单独关闭；
- trigger word 支持 `first`/`last`，作为单个 token 规范化和去重；
- 含逗号的 trigger word 被拒绝，避免意外拆成多个标签；
- `remove_tags`、`excluded_tags`、`always_include_tags` 彼此独立；
- 每张图片只使用自己的模型结果。

## 串行状态机、暂停与取消

批处理固定 `batch_size=1`。每张图片依次经历：

```text
pending -> analyzing -> exporting -> completed
                    └──────────────> failed
```

用户请求暂停后，当前 ONNX `run()` 自然返回并完成其原子导出，随后任务进入
`paused`；继续时从下一个 pending 条目开始。取消也等待当前同步调用结束，保留
已完成结果，并将尚未开始的已选条目标记 `cancelled`。扫描取消使用同一控制
对象。代码不调用 `QThread.terminate()`、`os._exit()` 或杀进程。

控制器的 busy 状态保证单图队列、模型加载、扫描、批处理和失败重置互斥。
它们共享一个 `TaggingService`，因此不会并行创建第二个 ONNX Session。

## 失败与重试

错误区分源缺失、格式/解码/图片限制、模型/推理、路径、权限、已有输出、
Caption/JSON/Manifest 写入、取消和未知错误。单条失败后继续下一条。

默认最大重试一次。只重置 `failed`、`missing`、`cancelled`，成功和跳过项不
重复运行。重试次数写入 Manifest/CSV。当前进程内导出失败会复用内存推理结果；
恢复后的任务没有隐式大对象缓存，会重新验证源文件并按需重新推理。

## Manifest 与恢复

默认 Manifest 位于：

- 有独立输出根时：`output_root/.animetagger/`
- 同目录模式：第一个源根的 `.animetagger/`
- 或显式 `metadata_dir`

文件名为 `batch-<uuid>.manifest.json`，schema version 为 1。Manifest 在任务
开始、每 N 项、暂停、取消/结束和关闭取消流程中原子保存。加载时拒绝半写、
非对象、未知 schema 或字段错误。

恢复时：

- `analyzing`、`exporting`、`cancelled` 回到 `pending`；
- 源图不存在标记 `missing`；
- 已完成项的必要输出仍存在则保留完成；
- 输出消失则回到 `pending`；
- 当前模型/Profile/阈值与快照不同时显示警告，但任务仍使用原快照；
- 只显示/打开任务，不自动开始推理。

## CSV 与 JSON

CSV 使用标准库 `csv`，默认 UTF-8，可选 UTF-8 BOM。每图一行，至少包括：

`source_path`、`relative_path`、`status`、`error_type`、`error_message`、
`model_name`、`execution_provider`、`inference_time_ms`、`profile`、
`positive_prompt`、`negative_prompt`、`tag_count`、`character_tags`、
`rating_tags`、`output_txt`、`output_json`、`completed_at`。

可导出全部项或仅成功项。报告默认不覆盖；显式确认后才原子替换。逐图 JSON
继续使用阶段 3 schema 2，并新增 `batch` 元数据。可选汇总 JSON 只保存轻量
条目摘要，不复制完整模型输出。

## CLI

```powershell
# 只预览：不加载模型、不推理、不写任何文件
python -m app.main batch D:\dataset --recursive --lora `
  --trigger-word style_token --dry-run

# 同目录 LoRA Caption + CSV，默认跳过已有 TXT
python -m app.main batch D:\dataset `
  --model-dir D:\tagger\models\wd-vit-tagger-v3 `
  --lora --trigger-word style_token --export txt --export csv

# 镜像输出和逐图 JSON
python -m app.main batch D:\dataset --recursive `
  --model-dir D:\tagger\models\wd-vit-tagger-v3 `
  --output-mode mirror --output-root D:\tagger-output `
  --export txt --export json --export csv

# 危险覆盖必须显式确认
python -m app.main batch D:\dataset `
  --model-dir D:\tagger\models\wd-vit-tagger-v3 `
  --existing-caption backup_and_overwrite --yes

# 恢复并重试失败项
python -m app.main batch --resume D:\output\.animetagger\batch-ID.manifest.json `
  --retry-failed --model-dir D:\tagger\models\wd-vit-tagger-v3
```

退出码：0 成功/dry-run，1 部分失败，2 配置/Manifest，3 模型/Provider，
4 取消，5 未预期内部错误。

## 大任务内存策略

- 扫描条目只保存路径和小型元数据，不保存图片像素。
- 表格按 item id 增量发射 `dataChanged`，不在每张完成时 `modelReset`。
- 推理严格串行，图片和 ONNX 输入数组在单条完成后释放。
- Manifest/摘要不复制完整置信度数组。
- 只有导出失败且可能重试的 `AnalysisResult` 会暂存，按最近 8 条硬上限
  淘汰；成功项不保留分析缓存。

## 验证边界

阶段 4 的文件系统、Mock 推理、队列、CLI 和 GUI 自动测试与可见 smoke 可以在
无模型环境执行。Mock 仅用于明确标注的自动测试，不代表真实模型验收。

阶段 4 完成时，工作区缺少 `model.onnx`、`selected_tags.csv` 和真实动漫
图片，因此当时没有执行真实验收。后续阶段 5 的一次性准备已经从官方固定
revision 下载并校验模型，真实 CPU Session 与结构 Smoke 已通过；真实动漫图
语义验收仍因 `validation-images/` 缺失而未执行。当前证据见
`docs/real-model-validation.md`。成品仍不会自动下载模型。

## 可见手动 Smoke 清单

1. 启动 GUI。
2. 打开“批处理”页。
3. 选择测试文件夹。
4. 非递归扫描。
5. 递归扫描。
6. 查看预览数量。
7. 切换输出模式。
8. 测试 dry-run。
9. 测试已有 Caption skip。
10. 验证 overwrite 确认。
11. 测试 backup_and_overwrite。
12. 设置 trigger word。
13. 预览 LoRA Caption。
14. 使用明确标注的 Fake/Mock 服务启动批处理。
15. 暂停。
16. 继续。
17. 取消。
18. 重试失败项。
19. 查看 CSV。
20. 查看 Manifest。
21. 恢复未完成任务但不自动运行。
22. 关闭窗口。
23. 确认没有残留 QThread 或 `.animetagger.tmp`。
