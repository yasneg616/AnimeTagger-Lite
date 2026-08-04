# WD14 模型目录

此目录的标准推理文件为：

```text
models/
└── wd-vit-tagger-v3/
    ├── model.onnx
    ├── selected_tags.csv
    └── README.md
```

固定来源为官方模型仓库
[SmilingWolf/wd-vit-tagger-v3](https://huggingface.co/SmilingWolf/wd-vit-tagger-v3)
的 revision
`7f6b584d0bd3f55c4531f14ba3d4761b2bccdc0f`。只允许准备
`model.onnx` 和 `selected_tags.csv`，不要下载训练权重、配置、示例图片、
Git 历史或其他模型。

用户可从项目根目录主动运行：

```powershell
python scripts/download_wd14_model.py
python scripts/download_wd14_model.py --verify-only
```

这是独立准备工具，不会由程序启动、模型加载失败或后台任务自动调用。正式 GUI
与 CLI 仍完全离线。`.gitignore` 已排除模型、CSV 和本目录内的其他本地文件，
避免误提交；发行流程也必须显式排除 `models/`。当前未生成发行 ZIP。
