# AnimeTagger Lite 数据安全约束

本文件描述 0.4.0 至 1.0.0 单图和批处理输出必须遵守的不变量。若实现与本文冲突，应先
停止写入并修复，不得以“尽量完成任务”为理由放宽原图安全。

## 原图不变量

应用对源图片只执行存在性检查、元数据读取和解码。任何正常、失败、暂停、恢复
或取消路径都不得：

- 删除源图片；
- 覆盖源图片；
- 重命名或移动源图片；
- 写回图片元数据；
- 用 TXT/JSON 临时文件复用图片路径；
- 因清理任务或 Manifest 而删除图片目录。

输出规划器强制使用 `.txt`/`.json`，并在写入前比较 resolved source/target。
GUI 的“清除任务”只丢弃内存表格；不会删除源或已生成文件。

## 默认策略

- 默认 Caption 策略为 `skip`。
- 默认扫描不递归、不包含隐藏项、不跟随符号链接。
- 默认报告不覆盖。
- GUI 开始前显示已有 Caption 和预计跳过数量。
- CLI 修改已有 Caption 必须显式 `--yes`。
- GUI 修改已有 Caption 必须在显示受影响数量后再次确认。
- dry-run 不加载模型、不推理、不创建目录、Manifest、Caption、JSON 或 CSV。

## 路径与扫描防护

- 扫描范围只来自用户显式选择的根，不扫描磁盘根。
- 文件格式表复用图片加载器，不接受任意扩展名。
- `output_root` 始终从扫描中排除，避免输出回流。
- 默认不跟随 symlink/junction；启用时用目录 identity 阻止循环。
- resolved path 大小写规范化并结合 inode/file identity 去重。
- 镜像/扁平相对路径禁止绝对路径、drive、空片段和 `..`。
- 最终目标必须通过 `commonpath` containment，保证位于 `output_root`。
- 扁平同名使用稳定短哈希，不靠覆盖“解决”冲突。
- Windows 非法字符、尾随点/空格和设备保留名被安全替换。

## 原子写入

所有可替换输出遵循：

1. 在目标同目录创建唯一 `.animetagger.tmp`。
2. 写入完整 bytes/UTF-8 文本。
3. `flush()` 和 `fsync()`。
4. 使用 `os.replace()` 原子提交。
5. 任意异常都清理临时文件。

由于临时文件与目标同卷，提交不依赖跨卷 copy。写入失败时旧目标仍存在。CSV、
JSON、Caption、备份和 Manifest 使用同一原语。

## 已有 Caption

- `skip`：不打开模型、不写目标。
- `overwrite`：只有显式确认后原子替换。
- `backup_and_overwrite`：先将旧 bytes 完整原子写入尚不存在的 `.bak.N`；备份
  失败时不进入覆盖步骤。
- `append_trigger`：读取 UTF-8/UTF-8 BOM，稳定去重后原子替换；不改其余手工
  标签。
- `merge`：现有标签优先，不做可能破坏含义的语义重写。
- 生成结果为空时不创建或覆盖 Caption。

逐图 JSON 已存在时，默认 `skip` 同样阻止覆盖。报告路径已存在时默认拒绝，
只有显式报告覆盖许可才原子替换。

## 暂停、取消、崩溃与恢复

ONNX Runtime 同步推理不会被强杀。暂停/取消标志只阻止下一项开始；当前项完成
后其输出要么完整提交，要么保持旧文件。代码不使用 `Thread.terminate()`、
`QThread.terminate()`、`os._exit()` 或进程杀死。

Manifest 自身原子更新。半写、截断、未知 schema 和无效字段不会被当作任务。
恢复只准备状态，不自动推理：

- 已完成且必要输出存在：保持完成；
- 输出缺失：回到 pending；
- 源缺失：标记 missing；
- 正在分析/导出时中断：回到 pending；
- 配置变化：告警并保留原不可变设置快照。

Manifest/清单只包含路径、设置和轻量结果，不包含图片 bytes 或模型 bytes。

## 隐私与日志

- 不含网络请求、自动下载、遥测、账户或云同步。
- 图片和 Caption 均保留在本机。
- INFO/DEBUG 日志记录状态和简短错误，不记录完整 Caption、图片 bytes 或完整
  模型置信度数组。
- CSV/JSON/Manifest 是用户选择的本地输出，可能包含本地绝对路径和提示词；
  分享前应由用户自行检查。

## 发布前安全检查

```powershell
rg -n "requests|httpx|urllib.request|QThread\\.terminate|os\\._exit" app
rg -n "model\\.onnx|selected_tags\\.csv" . -g "!models/README.md"
Get-ChildItem -Recurse -Filter "*.animetagger.tmp"
```

还应运行：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q app tests
python -m pip check
```

真实模型缺失时，真实 ONNX/动漫图测试必须明确跳过；Fake/Mock 测试不能改名或
包装成“真实模型已验证”。
