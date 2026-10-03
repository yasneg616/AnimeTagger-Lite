# 版本存档

所有已找到的版本均登记在 `versions.json`，完整程序存放在本仓库的 [GitHub Releases](https://github.com/yasneg616/AnimeTagger-Lite/releases)。每版的程序和依赖随 ZIP 保存；模型权重由使用者自行准备，配套词表、模型配置和许可证保留在包内。

普通 `git clone` 拉取源码、索引和校验清单。程序包超过 Git 单文件限制，需要另行从同仓库下载对应 Releases 附件。例如已安装 GitHub CLI 且有仓库访问权限时：

```powershell
gh release download v1.3.0 --repo yasneg616/AnimeTagger-Lite --pattern '*portable-no-models.zip' --pattern '*manifest.json' --pattern '*SHA256SUMS.txt' --dir downloads
```

下载后，将 ZIP 的 SHA256 与同版 `SHA256SUMS.txt` 或 `manifests/` 下的 JSON 对照。Windows 可使用：

```powershell
Get-FileHash .\downloads\AnimeTaggerLite-1.3.0-win64-cuda-portable-no-models.zip -Algorithm SHA256
```

先解压至新目录，再按随包 `MODEL-SETUP.txt` 放入已有模型权重，或在软件设置中选择对应模型目录。程序不自动下载模型。1.0.0 的原有 CPU/CUDA 包已经不包含模型，继续使用其随包模型说明。

`source_status` 为 `portable-only` 的版本只找到原始程序，没有可验证的独立源码快照；其 Git 标签保存存档说明和清单。其余版本的索引指出源码提交与源码核对结果。预览版单独标记为预发布，不替代正式版。

私人图片、剪贴板、日志、个人设置、审阅反馈和临时验收产物不会进入新存档。每个无模型包都有内部 `ARCHIVE-MANIFEST.json` 和外部 JSON 校验清单。

后续从已有便携目录生成同类存档：

```powershell
python scripts/archive_portable.py --package path/to/portable --output path/to/new-archive.zip --version VERSION --tag TAG
```

该命令只读取原目录，并核对写入过程中的文件长度、SHA256 和源文件变化；不上传文件、不下载模型、不修改原便携目录。
