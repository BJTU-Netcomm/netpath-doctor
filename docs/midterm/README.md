# 中期答辩准备材料

技术内容基于 feat/midterm-integration，并已补充 AI harness 工作。当前现场使用本机 eNSP Console；Qwen/百炼已在 Replay 上完成受控只读工具调用，真实现场 AI 只读链路仍需在有端口的 eNSP 拓扑上复测。SSH 端到端集成和多模拟器适配放入下一阶段。

按组长最新要求，已使用 EasySlides 生成 12 页可编辑 PPT（8 页主汇报＋4 页答疑附录），包含逐页讲解备注，并提供 PDF 预览。当前版本现场复测仍标为待完成；实验结果回填后再用于正式答辩。成稿及构建文件保存在本机并由 Git 忽略，不随源码自动推送。

## 直接使用

- [可编辑 PPT](NetPath-Doctor_中期答辩_EasySlides.pptx)：文字和流程图可编辑，PowerPoint 备注栏包含讲解提示。
- [PDF 预览](NetPath-Doctor_中期答辩_EasySlides.pdf)：用于快速浏览和核对版式。
- PPT大纲.md：8 页主汇报、4 页答疑附录；每页包含要点、配图建议、素材来源及讲解备注。
- slides.json：大纲源数据；EasySlides 成稿结合此大纲与当前证据制作。重新生成大纲不会自动更新 PPT。
- 讲稿与演示.md 和 .docx：210 秒讲解＋90 秒功能展示，共 5 分钟；约 5 分钟提问。最终以学院通知为准。
- 中期检查报告_技术稿.md 和 .docx：供迁入学院正式模板的技术正文。
- 代码导读与答疑.md：从动作到设备命令、Parser facts、状态机结论的调用链。
- 仅剩现场实验清单.md：三态采集、两类复测、录制和结果回填步骤。
- requirements-map.md：老师要求与材料对应。
- evidence.json：离线检查时间、代码版本、测试摘要及历史现场报告哈希。
- interface-check.json：详细接口三态原文检查；当前缺失代表待采集，不代表测试通过。

## 已完成的软件准备

修正了接口关闭使路由撤销时的诊断顺序。当前无路由且有本轮故障前出接口记录时，继续检查该接口：物理 DOWN 判为 INTERFACE_DOWN；UP/UP 判为 ROUTE_MISSING；接口回显解析失败或协议单独 DOWN 返回 NEED_MORE_DATA。两类受控实验均提供采集基线，不把故障标签传给 Agent。无基线的离线回放保持 V1 行为。

这些分支已有构造回归测试和执行器链路验证，仍必须用当前版本进行现场复测。历史两类各 3/3 与新版本验收分开记录。

## 再生成

在装有 python-docx 的 Python 中运行 `python tools/build_midterm_materials.py --verify`，刷新离线证据并生成大纲、讲稿、报告 Word 文档。工具不会连接设备，也不会生成最终 PPT。

三态采集后运行 `python tools/check_midterm_interfaces.py --output reports/live/console_interface_capture_check.json`。退出码 0 表示格式和状态检查通过，2 表示缺文件，1 表示文件未通过。

## 仍由本人完成的事项

技术剩余项：详细接口三态真实回显、当前版本两类各 3 次实验、对应录像及结果回填。若真实回显暴露新兼容问题，保留日志后再修正，不把实验预期当成事实。

展示剩余项：将新实验结果与录像回填到 PPT，在实际演示电脑彩排并核对播放时间。模板中的 LOGO 待替换，正式名称、编号、导师、经费待对照立项记录；报告迁入学院模板、教师审核、全员签字及系统提交另行办理。不能称为所有答辩事项只剩实验。

