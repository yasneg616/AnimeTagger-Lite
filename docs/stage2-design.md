# AnimeTagger Lite 阶段 2 设计

## 阶段边界

阶段 2 只处理单张推理结果的标签、提示词、配置与 TXT/JSON 导出。它不包含
PySide6 UI、文件夹扫描、批处理、CSV、完整 LoRA 数据集流程、Windows 打包
或模型下载。

2026-07-30 的阶段 1 最终验收检查中，
`D:/tagger/models/wd-vit-tagger-v3/` 缺少 `model.onnx` 和
`selected_tags.csv`，工作区也没有真实动漫测试图。因此：

- 真实 ONNX Session：未执行。
- 真实 Provider、输入形状和输出标签数：无法报告。
- 标签错位和真实高置信度标签：无法判断。
- 完整真实动漫图 CLI：未执行。
- 原因不是测试失败，而是验收输入缺失；没有使用 Mock 或占位图冒充。

提供两个模型文件后，`test_real_wd14_onnx_smoke` 会执行真实图计算、形状与
类别检查、Session 释放和重新加载。再设置 `ANIMETAGGER_TEST_IMAGE` 为一张
不提交到仓库的真实动漫图，`test_real_anime_image_cli_smoke` 才执行完整 CLI
验收。

## 数据流

1. `WD14Engine` 产生按 CSV 索引对齐的 `TagPrediction`。
2. `tag_results_from_predictions` 转换为有语义的 `TagResult`。
3. `TagNormalizer` 生成 `normalized_name`，原始 `name` 和置信度不变。
4. `TagFilter` 按配置过滤，返回保留、移除和明确排除项。
5. `TagClassifier` 从 `resources/tag_categories.json` 分配提示词组。
6. `PositivePromptBuilder` 根据 profile 生成正向标签。
7. `NegativePromptBuilder` 只从预设、真实缺陷和用户项生成反向标签。
8. `PromptProcessor` 解决正负冲突并返回统一 `PromptBuildResult`。
9. CLI、`ExportService` 和未来 UI 都消费同一个结果，不重复实现业务规则。

## TagResult

`TagResult` 是冻结 dataclass，包含：

- `name`：原始模型或用户标签。
- `normalized_name`：规范化后的输出名称。
- `confidence`：原始置信度。
- `category`：沿用阶段 1 的 `TagCategory`。为兼容现有接口，内部未知类别仍
  名为 `OTHER`；JSON 对外序列化为 `unknown`。
- `enabled`：为阶段 3 手动启用/停用预留。
- `source`：`model`、`user` 或 `preset`。
- `prompt_group`：16 个排序组之一。
- `model_index`：可选原始输出索引。

构建器只创建替换副本，不原地修改推理结果。

## 标签规范化与过滤顺序

置信度先统一校验，NaN、正负无穷以及超出 `[0, 1]` 的数值会报错。标签名称
随后做规范化预处理：可选下划线转空格、括号反转义、首尾清理和重复空格
折叠。逗号不会被拆分，而是作为无效单标签明确报错；空标签被记录为移除。

过滤顺序固定为：

1. 校验所有置信度。
2. 应用 General、Character、Rating 各自阈值；最低显示阈值作为下限。
3. 根据 `include_rating` 处理 Rating。
4. 应用 `excluded_tags`。
5. 应用 `always_include_tags`。它只重加输入中真实存在、启用且非空的标签，
   并按规定覆盖前面的阈值、Rating 和排除规则。
6. 按规范化名称稳定去重。
7. 对剩余标签应用 `max_tags`。
8. 按“固定标签优先、置信度降序、原输入顺序打破平局”输出。

每个移除项都有原因；`max_tags` 不会提前作用于未过滤数据。

## 正向排序与 profile

排序组依次为 quality、count、subject、character、hair、eyes_face、body、
clothing、accessories、pose_action、expression、composition、background、
lighting、style、other。模型 Character 类别总是优先进入 character 组；组内
按置信度降序，分数相同保持输入顺序。

- `raw`：不加前缀，按置信度稳定排序。
- `anime`：可选可编辑质量前缀，随后按组排序；已有前缀不会重复。
- `pony`：默认前缀为空，由用户编辑 JSON，不固化某套质量词。
- `lora_caption`：不加质量前缀、不生成反向词，只保留人物、外貌、服装、
  动作、表情与场景相关组；支持 trigger word 和固定标签移除。

最终字符串只使用 `", "` 分隔，无空项、重复逗号或尾逗号。

## 反向提示词与冲突

反向模式：

- `none`：空。
- `basic`：只使用选择的 JSON 预设和显式用户项。
- `cleanup_detected`：在 basic 来源之外，仅检查模型实际返回、启用且达到
  独立缺陷阈值的白名单缺陷标签。

低置信度、未出现的标签以及“未识别到的元素”永远不会被取反。每个反向词
记录 `preset`、`detected_defect`、`user` 中的一个或多个来源。

在 `cleanup_detected` 中，真实检测到的缺陷会从最终正向列表移除并记录
`detected_defect_conflict`，但原始 `TagResult` 和过滤快照仍保留。

## PromptBuildResult

统一结果包含 raw、filtered、positive、negative 标签，正反字符串，移除项、
明确排除项、检测缺陷、profile 名称和深拷贝的设置快照。CLI、JSON 导出和
阶段 3 UI 应直接复用该结构。

## 配置加载

- 默认配置：`resources/default_settings.json`
- 用户覆盖：`config/settings.json`
- 正向 profile：`resources/prompt_profiles.json`
- 反向预设：`resources/negative_presets.json`
- 分类规则：`resources/tag_categories.json`

字段使用轻量手工 schema 校验。缺失字段继承默认值，未知字段忽略。用户配置
不存在时直接使用默认值；损坏或字段非法时保留原文件、记录 WARNING，并回退
默认配置。程序启动不会静默重写用户配置。

## 导出安全

TXT 和 JSON 均先以 UTF-8 写入目标目录内的临时文件并 `fsync`。显式覆盖使用
原子替换；默认不覆盖使用同卷硬链接原子提交，文件竞争时失败而不是覆盖。
任何提交失败都会清理临时文件，已有目标保持不变。

JSON 只保存路径、推理元数据、标签和提示词，不保存图片或模型二进制。

## 阶段 3 UI 复用方式

UI 工作线程只负责调用 `WD14Engine`；得到预测后调用 `PromptProcessor`。
标签表格可持有 `TagResult` 副本，通过 dataclass replacement 表达编辑；
预览、复制和导出都读取同一 `PromptBuildResult`。因此 UI 不需要重新实现
阈值、排序、反向缺陷或导出规则。
