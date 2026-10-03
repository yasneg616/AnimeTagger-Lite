AnimeTagger Lite 1.3.0 · 标签图示与中文释义

1.3.0：标签图示与中文释义
单图标签表、随机 Prompt 标签列表显示彩色简笔图；鼠标悬停查看放大示意和简体中文释义。
在“单图 → 筛选与显示”中切换“图示辅助”，两处列表共用此选择并自动保存。
角色名称保留文字，未知标签标记待补。图示不改变英文 Prompt、复制和导出内容。
高频前 1,000 个标签的含义图示覆盖率为 95.1%；全量一般标签仍有 8,675 个待补。
resources/tag_visuals/README.md、coverage.json 和 coverage.tsv 提供说明、统计与逐项原因。
本次正式包包含审阅后重制的 77 项图示。
双击“打开图示审阅网站.cmd”启动本机图示审阅网站，无需另装 Python。
图示下的“需要重做”勾选和备注保存在本包 data/tag-visual-review/，只供本机使用。
该文件夹属于个人数据，不随正式发布包复制；已有项目里的审阅记录继续保留。
网站默认使用本机端口 8766；端口被占用时自动选择后续空闲端口。

1.2.1：手动注入正向标签
在正向提示词下方输入模型没有的角色或其他标签（英文/中文逗号分隔），点击“注入正向”或按回车。
默认停用模型识别的发型、发色、瞳色、眉毛、睫毛、胡须等外观标签，保留表情、视线、服装和背景。
手动标签受保护；取消“清理已识别的发型 / 发色 / 面部特征”勾选可只追加标签。
注入标签不受模型词表、Profile 标签数量上限或排除词限制；切换 Profile / 重新生成后仍保留。
“撤销注入”恢复上一次注入前的结果；后续编辑或重新识别后撤销失效，以免覆盖新修改。
原始识别标签保留，JSON 与文本导出使用当前结果。重新识别同一图片会重置本次注入。


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
