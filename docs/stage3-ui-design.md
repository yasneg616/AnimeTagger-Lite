# AnimeTagger Lite 阶段 3 UI 设计

本文记录 0.3.0 的 PySide6 桌面架构和边界。阶段 3 只处理用户手动添加到当前
列表的一张或多张图片；没有文件夹递归、CSV 批量导出、完整 LoRA 数据集流程
或 Windows 打包。

## 分层

```text
QWidget / QAbstractItemModel
        │ typed signals and IDs
        ▼
ProjectState + ImageItem        InferenceController + decode coordinator
        │                                  │
        └──────────────┬───────────────────┘
                       ▼
                TaggingService
        ┌──────────────┼───────────────┐
        ▼              ▼               ▼
    WD14Engine    PromptProcessor   ExportService
```

- `app/ui/` 只负责控件、选择、信号和用户交互。
- `app/state/` 保存当前手动图片列表和每张图片的独立状态。
- `app/services/tagging_service.py` 组合阶段 1 的 `WD14Engine`、阶段 2 的
  `PromptProcessor` 与 `ExportService`。
- UI 不执行 CLI 子进程、不解析 CLI 文本，也不复制过滤或提示词算法。
- CLI 继续直接使用同一 `WD14Engine`、`PromptProcessor` 和
  `ExportService` 底层类型，0.2.0 参数和输出行为保持兼容。

跨层传递的是 `QueueEntry`、`AnalysisResult`、`ModelInfo`、`TagResult`、
`PromptBuildResult` 等类型，不使用匿名字典作为任务协议。

## 线程模型

`InferenceController` 在 GUI 线程中创建一个持久 `QThread`，将
`InferenceWorker` 移入该线程。以下操作只在工作线程执行：

- 完整 ONNX 模型加载和结构校验；
- 模型释放；
- 图片预处理和 `session.run()`；
- 当前手动队列的逐张循环。

同一时间只有一个队列或模型操作。Controller 在发送任务信号前设置 busy，
所以连续点击“开始识别”不会排入第二个并行队列。Worker 不导入或操作
`QWidget`，只通过信号返回稳定 `image_id` 和类型化结果。

缩略图和预览使用独立的 `QThreadPool`，最大两个线程。它们永远不持有原始
大图，只返回已限制尺寸的 `QImage`。

## 取消与关闭

同步 ONNX 调用不能安全强制中断。取消按钮直接设置线程安全
`threading.Event`：

1. 如果一张图片正在 `session.run()`，让它自然完成；
2. 完成后检查令牌；
3. 把所有尚未开始的条目标记 `cancelled`；
4. 不再开始下一张。

Controller 在发布新队列信号之前重置取消令牌，Worker 开始处理时不再清空。
因此用户在任务刚排入、Worker 尚未取走任务的极短窗口内点击取消或关闭，也
不会丢失该请求。

关闭窗口时采用同一取消路径，并把 shutdown 投递到 Worker。窗口在工作线程
和图片解码线程池都实际退出前拒绝 close，并通过短间隔非阻塞轮询再次检查。
模型释放即使抛出异常也会在 `finally` 中发出线程退出信号。没有使用
`QThread.terminate()`，也不会丢弃仍运行的线程对象。

## ImageItem 状态

每个 `ImageItem` 有 UUID、源路径、临时标志和以下状态之一：

```text
pending → analyzing → completed
                    ↘ failed
pending ────────────→ cancelled
```

`loading` 保留给需要显式展示加载阶段的任务。列表不依赖文件名关联结果，所以
不同目录中的同名文件不会串图。

关键数据：

- `raw_tags`：最新一次模型输出转换成的不可变元组，作为审计和恢复基线；
- `working_tags`：当前图片独占的可变副本，包含勾选、改名、手动添加和删除；
- `prompt_result`：阶段 2 管线对当前 working tags 的最近构建结果；
- `inference_result`：Provider、输入尺寸、耗时等类型化推理元数据；
- generated/final 正反提示词及两个 edited 标志。

重新识别已编辑图片前显示确认。确认后，新模型结果覆盖该图片的 working tags
和最终提示词；其他图片完全不受影响。

## 标签模型

`TagTableModel` 是 `QAbstractTableModel`，列为启用、标签、类别、提示词分组、
置信度、来源。插入、删除、编辑分别使用 `beginInsertRows`、
`beginRemoveRows` 和 `dataChanged`。

`TagFilterProxyModel` 负责搜索、类别、分组、低置信度显示和排序。删除时先把
所有代理索引映射成源行，再按源行降序删除，避免多选索引漂移。

手动标签内部使用置信度 1.0 参与现有阶段 2 过滤，界面显示“手动”，来源是
`user`。中英文逗号会在单行标签编辑边界被替换为空格，避免破坏提示词逗号
分隔格式。编辑完成后才重建，而不是每输入一个字符重置整表。

## 提示词冲突策略

每个方向分别保存：

- generated prompt：阶段 2 根据当前标签和设置生成；
- final prompt：文本框当前实际内容；
- edited flag：final 是否偏离 generated。

当标签、阈值或 profile 变化时：

- 未手动编辑的方向立即更新；
- 已手动编辑的方向保留 final，设置 stale，并显示“可重新生成”；
- 点击重新生成时再次确认覆盖。

快捷阈值使用当前 `working_tags` 重新过滤和构建，不重新运行模型，也不修改
`raw_tags`。这使行为明确且不会意外丢弃手动标签。`lora_caption` 强制有效
反向模式为 `none`，显示 trigger word，并继续只处理当前单图状态。

## 模型状态

```text
未配置/无效 → 已验证 → 正在加载 → 已加载 → 已释放
                          └──────→ 加载失败
```

目录验证只检查目录、`model.onnx`、`selected_tags.csv`、CSV 结构和可用
Provider，不构造完整 Session。ONNX 可读性、NHWC 输入、输出维度和标签数量
一致性在“加载模型”时由 `WD14Engine` 完整检查。

加载使用候选 Engine；候选完全成功后才替换旧 Engine。因此新路径无效、ONNX
损坏或数量不匹配不会破坏仍可用的旧 Session。界面显示 Session 的实际
Provider 和 CUDA 回退原因。

## 缩略图与预览

- 缩略图最大边 96，使用小型 LRU 缓存，默认最多 128 张。
- 相同规范化路径的同时请求合并为一次解码。
- 当前预览最大边 2048，不缓存原始大图。
- 每次选择递增 preview generation token；过期任务即使较晚完成也不发到
  预览控件。
- EXIF、透明合成、格式与资源限制全部复用阶段 1 的 `load_rgb_image`。
- 关闭时设置取消事件并等待有限线程池自然结束。

## 剪贴板临时文件

剪贴板原始图保存到 `mkdtemp` 创建的本次会话专属目录，文件名使用随机 UUID。
只记录本服务创建的路径。正常关闭且推理线程退出后删除整个专属目录，不删除
用户原文件，也不读取或记录无关剪贴板内容。

## 设置职责

- `config/settings.json`：模型目录、设备、阈值、profile、反向设置、默认/最近
  目录等业务设置；使用临时文件、`fsync` 和 `os.replace` 原子提交。
- `QSettings`：窗口 geometry、主/右分割条、标签表列宽等纯界面状态。

用户 JSON 损坏时现有配置层保留文件并回退默认设置。GUI 日志使用
`RotatingFileHandler`，单文件 3 MiB、3 个备份；不记录图片二进制、完整提示
词或标签全集。

## 导出兼容

GUI 只调用 `TaggingService.export_result()`，最终仍由 `ExportService` 原子
写入。schema 从 1 升为 2，并保留旧字段：

- generated positive/negative；
- final positive/negative；
- `prompt_was_edited`；
- `raw_tags` 保存最新模型原始结果，`working_tags` 保存当前用户编辑副本；
- 兼容字段 `positive_prompt`、`negative_prompt` 表示最终导出文本。

文件默认不覆盖。GUI 只有在用户明确点击“覆盖”后传
`overwrite=True`。

## 手工 Smoke 清单

1. 无模型启动并检查具体缺失文件。
2. 添加 PNG、JPG，切换缩略图和预览。
3. 拖入文件与目录，确认目录不扫描。
4. 粘贴图片，关闭后确认会话临时目录删除。
5. 打开设置，选择无效目录、CPU/CUDA/auto。
6. 使用测试服务显示标签，编辑、添加、删除和恢复。
7. 切换 anime、lora_caption 与反向模式。
8. 手动编辑提示词后改变标签，确认文本不被覆盖。
9. 复制正向、反向和组合文本。
10. 导出三种格式，确认覆盖需要显式选择。
11. 启动多图片测试队列，取消并关闭。
12. 确认 `AnimeTaggerInferenceThread` 不残留。

真实模型不存在时，只能完成无模型和 Mock/测试服务路径；不得把它描述为真实
WD14 验收。

## 阶段 4 接入点

未来批处理可在不改变推理核心的情况下生成更多 `QueueEntry`，并增加批次级
状态与 CSV writer。阶段 3 没有目录枚举、批次数据库、CSV writer、LoRA
文件管理或并行 Session；这些只作为接口方向记录，没有实现。
