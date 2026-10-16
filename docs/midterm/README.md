# 中期答辩准备材料

技术内容基于 feat/midterm-integration，并已补充 AI harness 工作。材料同时包含本机 eNSP Console 报告、Qwen/百炼只读诊断报告、Replay Benchmark 和代码回归结果。中期答辩以这些可核对材料证明阶段成果，不把现场复测设为答辩前置条件。SSH 端到端集成和多模拟器适配放入下一阶段。

按组长最新要求，已使用 EasySlides 生成 12 页可编辑 PPT（8 页主汇报＋4 页答疑附录），包含逐页讲解备注，并提供 PDF 预览。PPT 与报告引用已归档的 eNSP、AI、Replay 和测试证据，可直接用于中期答辩；现场复测、录像和展示电脑彩排属于后续演示强化工作。成稿及构建文件保存在本机并由 Git 忽略，不随源码自动推送。

## 直接使用

- [可编辑 PPT](NetPath-Doctor_中期答辩_EasySlides.pptx)：文字和流程图可编辑，PowerPoint 备注栏包含讲解提示。
- [PDF 预览](NetPath-Doctor_中期答辩_EasySlides.pdf)：用于快速浏览和核对版式。
- PPT大纲.md：8 页主汇报、4 页答疑附录；每页包含要点、配图建议、素材来源及讲解备注。
- slides.json：大纲源数据；EasySlides 成稿结合此大纲与当前证据制作。重新生成大纲不会自动更新 PPT。
- 讲稿与演示.md 和 .docx：210 秒讲解＋90 秒功能展示，共 5 分钟；约 5 分钟提问。最终以学院通知为准。
- 中期检查报告_技术稿.md 和 .docx：供迁入学院正式模板的技术正文。
- 代码导读与答疑.md：从动作到设备命令、Parser facts、状态机结论的调用链。
- 仅剩现场实验清单.md：中期材料已足够后的后续现场强化、录制和彩排步骤。
- requirements-map.md：老师要求与材料对应。
- evidence.json：离线检查时间、代码版本、测试摘要及历史现场报告哈希。
- interface-check.json：详细接口三态原文检查；若材料中引用，需与原文来源一起说明。

## 已完成的软件准备

修正了接口关闭使路由撤销时的诊断顺序。当前无路由且有本轮故障前出接口记录时，继续检查该接口：物理 DOWN 判为 INTERFACE_DOWN；UP/UP 判为 ROUTE_MISSING；接口回显解析失败或协议单独 DOWN 返回 NEED_MORE_DATA。两类受控实验均提供采集基线，不把故障标签传给 Agent。无基线的离线回放保持 V1 行为。

代码已有构造回归测试、执行器链路验证和接口端点修复。历史 Console 两类各 3/3、当前 AI 只读诊断报告、Replay 20/20 和测试 113 passed 分开记录；历史误判报告保留为问题发现证据，不能伪装成修复后的新结果。

## 再生成

在装有 python-docx 的 Python 中运行 `python tools/build_midterm_materials.py --verify`，刷新离线证据并生成大纲、讲稿、报告 Word 文档。工具不会连接设备，也不会生成最终 PPT。

如继续补充三态原文，可运行 `python tools/check_midterm_interfaces.py --output reports/live/console_interface_capture_check.json`。退出码 0 表示格式和状态检查通过，2 表示缺文件，1 表示文件未通过；该检查属于后续现场材料强化，不影响本次中期材料的主体结论。

## 中期之后再完成的事项

技术强化项：详细接口三态真实回显、当前版本重复实验、SSH 端到端、多模拟器适配和模型策略对照。若继续采集或复测暴露新兼容问题，保留日志后再修正，不把实验预期当成事实。

展示强化项：将后续实验结果与录像回填到 PPT，在实际演示电脑彩排并核对播放时间。模板中的 LOGO 待替换，正式名称、编号、导师、经费待对照立项记录；报告迁入学院模板、教师审核、全员签字及系统提交另行办理。中期答辩当前不依赖现场实验才能成立。

