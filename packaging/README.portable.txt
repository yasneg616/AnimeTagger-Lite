AnimeTagger Lite Windows 便携版
================================

这是完全离线的 onedir 便携发行包。解压后直接运行
AnimeTaggerLite.exe；命令行和批处理入口为 AnimeTaggerLiteCLI.exe。

模型不会包含在发行 ZIP 中，也不会被程序自动下载。请将官方
SmilingWolf/wd-vit-tagger-v3 固定版本的两个文件放到：

models/wd-vit-tagger-v3/model.onnx
models/wd-vit-tagger-v3/selected_tags.csv

程序数据只写入 data/config、data/logs、data/batch-jobs 和 data/temp。
删除 models 目录不会删除或修改用户图片、Caption 或其他导出文件。

CPU 包只包含 onnxruntime；CUDA 包只包含 onnxruntime-gpu 及其官方
CUDA/cuDNN 运行库。CUDA 包仍需要兼容的 NVIDIA 驱动。

AnimeTagger Lite 项目自身采用 MIT License，正文见 LICENSE。随包第三方组件
继续分别遵守 LICENSES 和 THIRD_PARTY_NOTICES.txt 中的上游许可证；模型也
继续独立遵守其上游许可证，不由项目 MIT License 重新授权。

软件不会后台联网，不执行自动更新、遥测或模型下载。
