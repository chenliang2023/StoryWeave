---
epic: ../epics/short-story-comic.md
phase: executing
approved_revision: E89CAFC159207AA8E594F22B98D048E75A6D121907E5EA29B615E314379C65CF
current_item: ITEM-1
next_action: ITEM-1 已通过主人审核并 commit（未推送）；下一步进 ITEM-2（确认关卡）
blocked_by: 无
item_progression: per-item
milestone_commit: manual
remote_publish: manual
---
## 子项进度
- [x] ITEM-1
- [ ] ITEM-2
- [ ] ITEM-3
- [ ] ITEM-4
## 临时决策与证据
- design review 三轮已用完。第三轮后主人裁决：改身份则全部服装状态退回未确认；未支持的年龄切换、伪装或变身在改掉或明确跳过前该人物不能出页；页剧本不复制外貌。该裁决已写入永久文档，未再送审。
- 主人确认契约但本轮不开工。推进为 per-item：每项先停下审核。commit 与推送都是 manual，因为审核必须发生在提交之前；each-milestone 不能搭配 manual commit。审核通过后，再按该项显式 commit 并推送 origin。
- ITEM-1 实现待确认。storyweave 只把注入的模型输出整理成草稿。pytest 14 passed。缺口：未支持原因不从原文识别。未 commit。
- 2026-10-15 契约变更：主人七项选择写入永久文档，新增参考图术语与 DEC-6，人物身份字段加厚，ITEM-1/2/4 验收与约束更新。原批准指纹失效，ITEM-1 已实现的字段结构需要重做。旧指纹 2ff4220b6261a451296b0dfadb434a1d8001a402e756dc914d2c394f47605c2b。
- 契约评审第一轮：1 blocking + 4 important，全部修复。
- 契约评审第二轮：上轮 5 条全部 resolved；新增 2 条 important，全部修复。
- 契约评审第三轮：上轮 2 条全部 resolved；新增 1 条 important（下一章复用与可选参考图不一致），已修复但未再送审，因为本阶段三轮已用完。交主人裁决。
- 主人接受契约变更并确认。批准指纹替换为 B48D77C70997A5A50BAE16A3D657272ABB40A30DD02A1AAFAC901A83EB7B9C23。第三轮那条 important 的修复未再送审，由主人直接接受。
- 主人裁定 ITEM-1 重做范围：两件一起做——人物身份字段加厚为脸型、发型与发色、眼（眼型与瞳色）、显著特征、年龄、体态；同时补上从正文识别变身、伪装成他人、年龄阶段切换，不再只认模型输出。
- 2026-10-16 ITEM-1 重做完成（子会话 deepseek-v4.1-flash-cache，会话 9bc05935）。我自审：51 passed，7 条验收 6 条达标，第 7 条有两处实质缺口。评审写在 .codestable/work/feat-item1-评审.md。未 commit。
- 2026-10-16 主人三项选择：抽取改由 AI 一并做；正则规则表降级成给 AI 的提示；先走契约变更再连 P1 一起做。据此改永久文档：新增「抽取」与「未支持判定」术语、DEC-7，ITEM-1 改为文本模型通读抽取，人物卡补入「名称」，身份条目补「未支持状态下不承载该状态样貌」，验收标准与整体验收补四条，非目标与遗留风险各补两条。旧指纹 B48D77C70997A5A50BAE16A3D657272ABB40A30DD02A1AAFAC901A83EB7B9C23 失效。
- 2026-10-16 契约变更评审（新阶段，每轮 fresh reviewer，grok）：第 1 轮 0 blocking + 4 important；第 2 轮 0 blocking + 4 important + 2 minor；第 3 轮 1 blocking + 2 important + 2 minor。三轮共 11 条全部修复。第 3 轮是末轮，其 5 条修复未再送审，交主人直接接受（沿用上一阶段做法）。两次上游故障不计轮次：gpt-6.1-sol 连续 502；gpt-6-luna 对委派组不可用（model_not_found）。
- 2026-10-16 主人再次确认：人物与场景识别保持由 AI 通读抽取，正则只作提示，DEC-7 不变。
- 待确认指纹（Epic 文件 SHA256，157 行，27556 字节）：E89CAFC159207AA8E594F22B98D048E75A6D121907E5EA29B615E314379C65CF。中间态 8A67EB849DF0706053B15B7CDB52A7DE8EE55720F4B35D801FD69B2E52CD0A9E 与 C8F8610661EDE6F14CD877E00BA7C2B3143C74C7C591BA456B5F654B7FA16859 均未批准，已失效。
- 2026-10-16 主人确认契约变更。批准指纹替换为 E89CAFC159207AA8E594F22B98D048E75A6D121907E5EA29B615E314379C65CF。第 3 轮那 5 条修复未再送审，由主人直接接受。current_item 置为 ITEM-1。
- 2026-10-16 ITEM-1 重做完成（子会话 af637653，模型 deepseek-v4.1-flash-cache）。抽取改为「构建提示 → 调用注入的模型 → 解析 → 校验」，提示拼入原文全文；正则规则表降级为提示；旧顶层键 未支持命中 删除。P1-1（无主线索拦整篇出页）与 P1-2（身份不承载变后样貌）已修。
- 2026-10-16 ITEM-1 独立评审（fresh code-reviewer，delegation 980d772a）：有条件可合，0 blocking / 3 important。三条已修：①出页粒度分离并删掉会分叉的 可出页 快照键（顶层与人物卡各一份），整篇只按未处理无主线索算、人物按未跳过的未支持现算；②未支持条目补 已跳过 位，与无主线索各成一条互不覆盖；③新增正式入口 抽取短篇草稿 先验篇幅，评测节选仍走 抽取草稿。
- 2026-10-16 我复验：59 passed（命令 `$env:PYTHONUTF8=1; uvx --from pytest pytest tests --tb=short -q`）。顶层键正好五个契约键、人物卡无 可出页、两种出页粒度确实分离、正式入口对 11 字节选抛 篇幅不符。无网络引用、无新 commit、`.codestable/` 未被实现方触碰、契约指纹仍是 E89CAFC1。评审写在 work/feat-item1-评审-2.md（旧记录 feat-item1-评审.md 保留作历史）。未 commit。
- 2026-10-16 主人裁定：ITEM-1 通过，只 commit 不推送；另要求写文本模型供应商适配层但不联网真调。据此新增 storyweave/model_client.py（供应商配置 / 从环境变量读配置 / 构建调用模型 / 请求 / 响应 / 默认发送 / 模型调用失败，只用标准库）与 tests/test_item1_model_client.py（27 用例，全离线）。供应商选择仍是开口：默认走 [OI] 兼容 chat completions，未定具体厂商、未给 key，真跑前需补。
- 2026-10-16 我复验适配层：86 passed。我另做封网复跑（禁 socket.create_connection / getaddrinfo / connect / connect_ex / urlopen）仍 86 passed，证明测试零真实 HTTP。公开 API 冒烟：URL 无双斜杠、提示含原文全文、顶层正好五个契约键、无主线索拦住整篇、api_key 不从错误因果链泄漏。
