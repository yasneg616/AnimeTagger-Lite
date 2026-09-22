AnimeTagger Lite 1.2.0 · 现代界面与调色盘

双击 AnimeTaggerLite.exe 启动。右上角“调色盘”提供暮紫、海蓝、青松、暖砂、晴昼主题，
也可自定义强调色、背景色、面板色。颜色实时预览，保存后自动记住，取消会恢复原配色。
顶部选择模型后可加载；“模型管理”中仍可验证和释放模型。
反向提示词、筛选和高级设置可展开，批处理与随机 Prompt 保留。

本次 single-EXE 版把 Python、Qt、推理运行库合并为一个程序，无需另装 Python。
models、resources、LICENSES 和 portable.flag 请保留在 EXE 旁边，整个目录一起移动。
模型已附带，无需重新下载。Canary 使用 CPU；WD v3 / PixAI 支持 CUDA。
单 EXE 每次启动会解压运行库到临时目录，启动可能需要等待十几秒至数十秒。
命令行使用 AnimeTaggerLite.exe --cli（替代单独的 AnimeTaggerLiteCLI.exe）。
单文件发行版以 BUILD-MANIFEST.json 中 program_layout=onefile 为准。

具体操作见 QUICK_START.txt。

发行类型由 BUILD-MANIFEST.json 标记：program_layout=onefile 为单 EXE 运行库，
onedir 为传统 _internal 目录与独立 CLI 程序。model_included=true 才表示随包附带模型。
CUDA 包还需要兼容的 NVIDIA 驱动；可在设置中选 CPU。

项目自身采用 MIT License，正文见 LICENSE。第三方组件分别遵守 LICENSES 和
THIRD_PARTY_NOTICES.txt 中的许可证；模型独立遵守各自上游许可。
软件离线运行，不执行后台自动更新、遥测或模型下载，不修改原图。
