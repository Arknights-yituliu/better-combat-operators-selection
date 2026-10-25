# AGENTS.md

> **本文只讲「接到任务怎么开工」。** 项目介绍、数据流、命令手册、分类约定都是专文，按 §三 索引按需查阅——**开工时不要读它们**。
> 人类开发者入口见 `README.md`；文档总目录见 `docs/README.md`；agent 资源索引见 `.claude/README.md`。

## 一、任务类型 → 开工件（看上表第一行命中即停，不要叠加、不要为了「确定读哪个」而把几个开工件都读一遍）

| 任务类型 | 唯一开工件 | 要点 |
|---|---|---|
| **版本更新**（新干员 ＋／或 既有干员新模组） | `docs/version-update-quickstart.md` | 其 §1「阅读预算」已写死必读 4 处、按需与禁读清单、三条止损线；**不再另读 primer／本表以外任何开工件** |
| 新干员实装（单独，无既有干员模组变动） | `.claude/skills/add-new-operator/SKILL.md` | 只更新成员文档，**绝不生成** `results/operator-tags.json`。**先查 `docs/operators.txt` 与 `_manifest.json`**：已在册即跳过爬取、直接验收 |
| TAG 改写／复算／数据修复（改既有条目） | `docs/agent-primer.md` | 派子代理一律用 `.claude/agents/tag-rewrite`，别手写 brief |
| 全表扫描／评定标准修订 | `docs/scan-protocol.md` ＋ `.claude/skills/solidify-criteria/SKILL.md` | 扫描类先出名单、逐人决断，再另起复核。**单干员单 TAG 复核不算扫描**：不出名单、直接在「检索记录」留痕 |
| 新增 TAG | `.claude/skills/add-player-tag/SKILL.md` | 先把评定标准说清，除非明确选 stub 方案 |
| 数值复算／「（待验证）」条目 | `.claude/skills/reverify-numbers/SKILL.md` | |
| 批次回填／守恒审计 | `.claude/skills/tag-batch-rewrite/SKILL.md` | 先 `--dry-run` |
| 会话转交 | `.claude/skills/handoff/SKILL.md` | 状态快照在 `agent_workspace/handoff/state.md`（本地） |
| 判断类问题（取哪个档／算不算计入…） | `docs/rulings.md` | **先读顶部节级目录、只读命中节**；查不到才提问 |

> 结构性更改（改评定标准、全库重扫、增删 TAG、改计算规则正本）**不走版本更新快线**。

## 二、AI 协作铁律（五条，违反过，代价明确）

1. **自创代称必须登记**：文档与交付文本中的任何代称、缩写、自编号（规则号、历史冲突号、TAG 代号、模组线名、公式符号等）一律登记在 `docs/term-map.md`（含义／用法／查阅位置）。**新建即同步**；未登记的代称不得用于交付文本，且首次出现必须当场解释该怎么理解。

2. **裁定必须留痕、所见即所得**：所有待裁项集中在单一工作文件 `agent_workspace/workdocs/待裁定.md`，每条自包含（背景／现状／候选／**算式与来源**），开发者只读该文件即可裁定；涉及模组线、专有机制、道具、自编号时**给出完整描述**，不得假设开发者与自己知识对齐。**先查台账再提问**——同一个问题问第二遍即流程失败。裁定后四步缺一不可：① 折入源文件；② `docs/rulings.md` 登记（裁定／理由／适用范围／折入位置）；③ 脚本侧放行表（`ACCEPTED`／`REVIEWED_TIERS`）写明理由并指向台账；④ 整体移除 `待裁定.md`。

3. **改动的授权边界**：开发者明确要求修改的，必须动；**AI 自行发现「可能需要修改」的，一律先写进《待裁定.md》问过再改**——不得自行改动、不得顺带修。自行放大工具权限（如放宽代理的 `allowed-tools`）同属越界。

4. **语言统一中文**：本仓库一切手写文档的正文用中文；代码块、命令、路径、JSON 键与游戏专名（PRTS／TAG／术语代号）保留原文。规则与判定标准见 `docs/README.md`「撰写语言」，机器校验见 `tools/doc_consistency.py`。

5. **不得用 `git checkout -- <path>` / `git restore` 撤销工作区改动**：本仓库常有并行代理在同一工作区作业，这类命令会把别人未提交的产出整块打回 HEAD（模拟验证中真实发生过：一份已通过校验的产出被另一代理还原）。要撤自己的实验性编辑，就用与写入时相同的方式**精确反向编辑**（改回那几行），并把遇到的「不是我改的」文件列出来上报，不要处置它们。交付时只报自己改过的路径。

## 三、索引（需要时再读，不要开工时读）

| 想了解 | 读 |
|---|---|
| 项目是什么、数据流、目录职责、**文件权属**（改谁／信谁） | `docs/architecture.md` |
| **全部命令**与参数 | `docs/commands.md` |
| 分类约定、**评定标准写法规则** | `docs/classification-conventions.md` |
| 爬虫内部、语料剥离规则、证据层审计纪律 | `docs/crawling-and-strip.md` |
| 计算规则正本／产物规范／消费端渲染规则 | `docs/calc-rules.md`、`docs/output-standard.md`、`docs/ui-render-rules.md` |
| 机制常识正典／术语／历史判断陷阱 | `docs/mechanism-understanding.md`、`docs/glossary.md`、`docs/verification-complaints.md` |
| 条件与备注的写法（分条／分块） | `docs/concept.md` |
| 历史记录（仅背景、不作依据） | `docs/history-notes.md` |
| 文档总目录 | `docs/README.md` |
| 维护面板用法 | `gui/README.md` |
| 人类开发者入门／贡献 | `README.md`、`CONTRIBUTING.md` |

## 四、本仓库的边界

- 这是**数据生产线，不是应用**；产品 UI 在另一个项目，本仓库不消费自己的产物。
- 没有构建／测试工具链；校验靠 `tools/run_all_checks.py`（十项，清单以脚本 `CHECKS` 为准）。
- Windows 控制台是 GBK：Python 一律加 `-X utf8`，否则中文直出是乱码。
