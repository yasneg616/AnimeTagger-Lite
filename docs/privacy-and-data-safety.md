# 隐私与数据安全

## 离线边界

AnimeTagger Lite 的 GUI、单图 CLI、批处理 CLI、模型加载失败、首次启动和后台
Worker 都不发起网络请求。成品没有账户、API Key、遥测、崩溃上传、更新检查、
广告或云同步。

模型下载只存在于用户/开发者主动执行的 `scripts/download_wd14_model.py`，且
固定到官方 `SmilingWolf/wd-vit-tagger-v3` revision。该脚本不在程序启动时
调用，也不把 `huggingface_hub` 加入运行依赖。

## 图片与输出

- 只扫描用户在 GUI/CLI 明确选择的图片或目录；不搜索其他磁盘位置。
- 原图只做存在性、元数据读取和解码；不删除、移动、重命名、覆盖或写回元数据。
- 默认 Caption 策略为 `skip`；覆盖需要明确确认。
- Caption、JSON、CSV 和 Manifest 使用同目录临时文件、flush/fsync 与原子提交。
- 暂停/取消只阻止下一项，当前同步推理完成后才落下完整输出。
- 剪贴板只读取用户本次粘贴的图片/本地路径；会话临时副本在安全关闭后清理。

完整批处理不变量见 `docs/data-safety.md`。

## 便携数据

正式包存在 `portable.flag`，只在发行根的 `data/` 下保存：

| 路径 | 内容 |
|---|---|
| `data/config/settings.json` | 业务设置与最近目录 |
| `data/config/ui.ini` | 窗口和表格状态 |
| `data/logs/` | 轮转运行日志 |
| `data/batch-jobs/` | 便携批任务 Manifest/报告 |
| `data/temp/` | 当前会话剪贴板临时图片 |

程序不向 `_internal`、`resources` 或 Python 运行库写用户数据。目录不可写时显示
清晰错误并停止，不用 traceback 掩盖权限问题。

## 日志最小化

日志可记录时间、组件、状态、Provider 和简短错误；不记录图片 bytes、完整正反
提示词、完整 Tag/置信度数组、剪贴板其他内容、访问令牌或 API Key。用户主动
导出的 JSON/CSV/Manifest 可能含本地绝对路径和提示词，分享前应自行检查。

## 发行审计

正式构建拒绝：模型权重、`selected_tags.csv`、验证图片、tests、pytest、用户
配置/日志、临时文件、绝对开发路径、用户名、Smoke 路径、QtWebEngine、
PyTorch、TensorFlow、Hugging Face Hub 和 CPU/CUDA 混装。

Defender 只做本机自定义扫描；不会关闭防护、添加排除项、修改策略或上传文件到
第三方扫描网站。任何告警必须记录检测名并先检查打包模式、UPX、异常脚本或临时
执行行为，不能建议用户关闭杀毒软件。
