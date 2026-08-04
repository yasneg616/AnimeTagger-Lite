# AnimeTagger Lite 真实模型验收

日期：2026-08-03  
项目版本：0.5.0-rc1  
用途：阶段 5 与最终发行补充的官方模型、真实图片、CPU/CUDA Session、输出映射及批处理验收

## 来源与下载边界

- 官方仓库：`SmilingWolf/wd-vit-tagger-v3`
- 固定 revision：`7f6b584d0bd3f55c4531f14ba3d4761b2bccdc0f`
- 下载文件仅有 `model.onnx` 与 `selected_tags.csv`
- 使用脚本：`scripts/download_wd14_model.py`
- 没有 Git clone、仓库快照、配置、示例图片、训练数据或第三方镜像
- 公共仓库不需要 Token；脚本不读取、不要求也不记录 Token

第一次在受限网络环境访问同一官方 URL 时进行了 3 次重试，均以 Windows
`WinError 10051` 失败，不完整 `.part` 已清理。获得本次明确网络权限后重新
运行，成功下载本身没有发生内容重试，全程没有改用第三方来源。

## 文件完整性

| 文件 | 大小 | SHA-256 |
|---|---:|---|
| `model.onnx` | 378,536,310 bytes | `35f23693620b668f4d53fd3c62bf65e40af739bc52c7eb0fbc49258b58d065b6` |
| `selected_tags.csv` | 308,468 bytes | `298633d94d0031d2081c0893f29c82eab7f0df00b08483ba8f29d1e979441217` |

两个文件均不是 HTML、JSON 错误响应、Git LFS 指针或 Xet 指针。CSV 以
UTF-8 正常读取，字段为 `tag_id,name,category,count`，共有 10,861 行：
Rating 4、General 8,106、Character 2,751；不存在空标签、非法 category 或
明显截断。

## 模型图与 Session 契约

| 项目 | 实测值 |
|---|---|
| 输入名 | `input` |
| 输入形状 | `('batch_size', 448, 448, 3)` |
| 输入类型 | `tensor(float)` |
| 输出名 | `output` |
| 输出形状 | `('batch_size', 10861)` |
| 输出类型 | `tensor(float)` |
| CSV 标签数 | 10,861 |

输出数量与 CSV 映射数量严格相等，没有裁剪、忽略或 Mock 适配。Session 的
创建、读取输入输出、真实执行、释放和重新加载均通过。

## 真实验证图片

`D:/tagger/validation-images/` 中有 6 张真实 PNG，均为 832×1216。只使用该
目录，没有扫描用户其他目录或下载图片。全部原图在任何验收前后哈希不变：

| 文件 | SHA-256 |
|---|---|
| `image (1).png` | `464794b4e257264ad6791c5451fa6bd6ef835c8e38019a2eef81392f61fde948` |
| `image (2).png` | `b02e4685dce05950b78b3677ef6c7cf7800987301fcf3c47884c36f55326a1df` |
| `image (3).png` | `3ca42f8240086f1f1e21fbf647af85912959b724295baf7c598ea059813eabab` |
| `image (4).png` | `54f0139685cb5526ad988973148d574fcd5a0da5172e580acfe3056762f66f9a` |
| `image (5).png` | `c2f92dd3871621a54cc695d12e7aded92f0b06b0a298f8d5ce1af45fc11bfb9f` |
| `image.png` | `89f6bf3cb24ae481f0e6524cff535bab35564b8de1031f7e5c7cb7871b473b38` |

PNG alpha extrema为 254–255；透明/近透明通道按项目既有白色背景合成路径处理。
图片没有 EXIF 方向标记。没有移动、重命名、覆盖、重编码或修改元数据。

## CPU 真实推理

- Python 3.11 环境：`onnxruntime 1.28.0`
- Session Provider：`CPUExecutionProvider`
- 3 张记录图片推理：346.296、332.510、347.867 ms
- 6 张图片均输出 10,861 个有限、0–1 范围的分数
- 安全语义示例：`1girl`、`white_hair`、`long_hair`、`short_hair`、
  `solo`、`blue_hair`、`pink_hair`
- 3 张图的 General(≥0.35) 分别为 48、45、52；Rating 始终映射为 4
- Character 高阈值结果可为空，类别边界与 CSV 索引一致
- 没有发现整体标签错位

真实 CLI 的 TXT/JSON 导出、正向 profile 和反向模式均通过。反向
`cleanup_detected` 只处理达到缺陷阈值的检测结果，不会把全部低置信度标签取反。

真实 MainWindow 使用实际 `TaggingService` 与 Worker，完成单图、三图队列、
搜索/筛选、编辑、手动标签、四个 profile、三个反向模式、复制、TXT/JSON、
释放、重载和再次推理。没有 Windows“无响应”；关闭后 Controller、Decoder
和 Python 线程均退出。

## CUDA 真实推理

- GPU：NVIDIA GeForce RTX 4080 Laptop GPU
- 驱动：610.74
- `onnxruntime-gpu 1.28.0`
- available providers：TensorRT、CUDA、CPU
- 实际 Session：`CUDAExecutionProvider`
- 没有静默回退 CPU
- 冷加载记录：3,843.137 ms；后续重载 508.143 ms
- 首张暖机推理：250.177 ms；后续两张：13.522、13.528 ms
- 释放/重载后的推理：16.107 ms
- 显存总量记录：加载前 3,098 MiB、加载后 3,800 MiB、推理后
  3,810 MiB、释放后 3,272 MiB

相同 3 张图片的 CPU/CUDA Top 10 顺序完全一致，Top 20 重合均为 20/20；
最大绝对分数差分别为 0.000945、0.000870、0.000778，未见异常漂移。

真实 CUDA GUI 完成三图队列、标签绑定、编辑、profile 切换、释放/重载：
加载 709.974 ms，单图总计 450.815 ms，三图队列 706.899 ms，重载
484.672 ms。心跳最大间隔 529.334 ms，未出现无响应；关闭 88.811 ms，
无残留 Worker 或解码任务。

## 自动 Smoke

在 CPU 与 CUDA 的 Python 3.11 隔离环境中显式设置：

```powershell
$env:ANIMETAGGER_MODEL_DIR = "D:\tagger\models\wd-vit-tagger-v3"
$env:ANIMETAGGER_VALIDATION_DIR = "D:\tagger\validation-images"
```

Python 3.10 CPU、Python 3.11 CPU 与 Python 3.11 CUDA 三套环境最终均为
`395 passed, 0 skipped`。真实模型和真实图片 Smoke 均实际执行，不再因模型或
图片缺失跳过。测试不联网、不下载、不修改图片，也不把 Mock 或纯色图冒充
视觉语义验收。

## 2026-08-03 最终发行补充复验

正式构建预检在两个 Python 3.11 锁定环境中均通过 `pip check`、compileall、
395 项 pytest、CLI/批处理 CLI help 与 offscreen GUI。CPU Session 的单次预检
推理为 347.885 ms；CUDA Session 的单次预检推理为 227.386 ms，实际 Provider
为 `CUDAExecutionProvider`，没有静默回退。CUDA 日志中的 12 个 Memcpy 节点是
ONNX Runtime 图优化告警；实际 Session 与冻结包验收均确认仍使用 CUDA。

真实文件夹批处理各执行 25 次预测，并覆盖 dry-run、暂停/继续、取消/恢复、失败
重试且不重复推理、Caption 冲突策略、TXT/JSON/CSV/Manifest 与多种输出模式：

| 项目 | CPU | CUDA |
|---|---:|---:|
| 模型加载 | 635.347 ms | 780.576 ms |
| 显式重载 | 491.229 ms | 451.582 ms |
| 首次推理 | 360.452 ms | 218.443 ms |
| 后续平均推理 | 322.725 ms | 33.315 ms |
| 批处理期间 Session 数 | 1 | 1 |
| 显式重载后累计 Session 数 | 2 | 2 |
| 进程工作集峰值 | 670.613 MiB | 856.086 MiB |

CPU 进程工作集在释放模型后回落到 82.855 MiB。CUDA 系统显存占用记录为加载前
3,749 MiB、加载后 4,453 MiB、批处理后 4,964 MiB、释放后 3,914 MiB；WDDM
没有提供可靠的进程级显存数字，因此报告中该字段明确为 `null`，没有用系统值
冒充进程值。机器可读证据位于 `release/real-acceptance-cpu.json` 和
`release/real-acceptance-cuda.json`。

冻结 CPU GUI 还在项目外的中文/空格路径中使用真实图片完成了识别、模型释放与
重载。默认反向模式 `none` 得到 0 个反向标签；切换到 `basic` 后从既有
`working_tags` 立即生成 7 个反向标签，没有再次执行 ONNX 推理。临时数据目录被
拒绝写入时，GUI 显示含实际路径和 `WinError 5` 的中文启动错误且没有 traceback。
验收后进程、临时目录和 `.part` 文件均为 0，6 张原图 SHA-256 再次保持不变。

## 离线成品边界

下载脚本只能由开发者或用户主动运行，不会从 GUI/CLI 默认入口、模型加载失败、
首次启动、后台任务、定时任务或更新检查调用。运行依赖和发行包中没有
`huggingface_hub` 或其他永久网络依赖。

静态搜索确认网络 URL 和标准库下载调用只存在于显式的
`scripts/download_wd14_model.py`。删除模型目录只会让下次模型加载报告缺失，
不会删除、移动或修改用户图片、Caption 或导出文件。

## 2026-08-04 正式 1.0.0 终版确认

在 RC1 全部门槛通过后，唯一版本源升为 `1.0.0`，CPU/CUDA 使用锁定的 Python
3.11.9 环境从零重建。两个构建预检分别再次通过 395 项测试；CPU 真实 Provider
为 `CPUExecutionProvider`，CUDA 真实 Provider 为 `CUDAExecutionProvider`。
终版 CPU/CUDA ZIP 又分别在项目外完成外置官方模型、6 张真实图片、格式矩阵、
正反提示词、批处理、Caption、CSV/JSON/Manifest、设置持久化和残留进程检查。

最终 CPU GUI 以 `AnimeTagger Lite 1.0.0` 标题启动，读取 448×448 输入与 10,861
输出，真实图片推理得到 48 个正向标签；默认 `none` 为 0 个反向标签，切换
`basic` 后立即得到 7 个反向标签。模型释放和重载均成功，源图哈希保持不变。
Microsoft Defender 使用病毒库 `1.455.490.0` 扫描整个最终 `release` 目录，
结果为 `found no threats`、退出码 0。最终 ZIP 哈希及完整证据见
`release/SHA256SUMS.txt` 与 `docs/release-smoke-report.md`。
