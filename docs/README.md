# docs 文档索引

本目录是判定规范、规则正本与文档的集合。**权威源**文件是改动的目标；**生成物**由脚本重生成，不要手改。

## 撰写语言

本仓库一切**手写文档**的正文用**中文**；代码块、命令、路径、JSON 键、字段名与游戏专名（`PRTS`／`TAG`／`条件`／`备注`／`评定标准`／模组代号）保留原文。生成物（`*-members.md`、`module-hidden-mechanics.md`、`temp.txt` 等）不在此列。

`tools/doc_consistency.py`（`tools/run_all_checks.py` 的第 10 项）逐行校验：手写文档里出现英文散文行（≥4 个英文词且英文词数 > 中文字数 × 2）、`AGENTS.md` 超出纯路线图预算或重新长出代码块、文档间计数与节级锚点漂移——都会报错。

## 架构与作业（怎么开工、怎么跑命令）

| 文档 | 内容 |
|---|---|
| `architecture.md` | 项目是什么、数据流、目录职责、**文件权属表**（手写权威源 vs 生成物） |
| `commands.md` | **全部命令**与参数（爬取、审计、回填、属性层、产物链、排序、荐、GUI、校验） |
| `classification-conventions.md` | 分类约定（证据制、条件 vs 备注、取数、不丢能力…）与**评定标准写法规则** |
| `crawling-and-strip.md` | 爬虫内部与踩过的坑、语料剥离规则、证据层审计纪律 |
| `history-notes.md` | 历史记录（仅背景、不作依据） |
| `agent-primer.md` | 作业记忆包：游戏常识、仓库作业常识、反面清单（TAG 改写／复算类开工必读） |
| `version-update-quickstart.md` | **版本更新快线**：非结构性更新的唯一开工件——**§1 阅读预算**（必读 4 处／按需／禁读三张清单＋止损线）、七步流程、预核验清单、验证最低集与审核规则 |
| `scan-protocol.md` | 全表扫描流程：名单文件、逐人决断、独立复核 |

## 规范与规则（权威源）

| 文档 | 内容 |
|---|---|
| `concept.md` | 项目意图，以及「条件／备注／结果 JSON」的写作规则（条件分条、备注分块等，全项目唯一出处） |
| `output-standard.md` | 结果 JSON 的产物规范（版本／日期、干员卡、PRTS 深链、荐） |
| `player-tags-specify.md` | 玩家体感 TAG 的定义（开发者手改） |
| `calc-rules.md` | 计算规则正本：结算层位与总式、游戏文本→因素映射、演算流程、未定项索引 |
| `rulings.md` | 裁定台账：开发者对判断类问题的裁定逐条留痕（先查它，再提问） |
| `term-map.md` | 代称映射表：自创代称／缩写／自编号的含义与查阅位置 |
| `glossary.md` | 游戏术语表（前 5 节手写，后 6 节由 `crawlers/crawl_special_mechanics.py --apply` 追加） |
| `player-tags-criteria.md` | 玩家 TAG 评定标准（严谨版）源文件：通俗说明＋精确条件＋计算式＋对照例子（前端悬浮说明＋评定标准抽屉文案；生成 `results/player-tags-criteria.json`；撰写要求见其文件头） |
| `operators.txt` | 干员与 PRTS 页面链接清单（爬虫的输入） |

## 判定依据（写条目时查）

| 文档 | 内容 |
|---|---|
| `mechanism-understanding.md` | 机制常识正典——判别原则以它为准 |
| `verification-complaints.md` | 历史判断陷阱记录（计数与举例以现行文件为准） |
| `abnormal-effects.md` | PRTS《异常效果》落库：异常效果／组合／硬软控对照 |
| `ui-render-rules.md` | 消费端（前端项目）渲染规则记录，改 JSON 结构时对照 |

## 生成物（勿手改，改源文件后重生成）

| 文档 | 生成链路 |
|---|---|
| `official-tags-members.md` | `agent_workspace/tag_pipeline/official_tags/_merge_official_to_docs.py` |
| `player-tags-members.md` | `agent_workspace/tag_pipeline/player_tags/_merge_to_docs.py` |
| `untagged-operators.md` | `tools/generate_results.py` |
| `module-hidden-mechanics.md` | `tools/module_notes.py --emit` |

## 本地与模板

| 条目 | 说明 |
|---|---|
| `temp.txt` | PRTS《模组》页表格快照（本地快照，不进库；`module_notes.py` 的输入） |
| `templates/` | 工作稿模板：《待裁定.md》《待验证复算.md》；实际工作稿写入 `agent_workspace/workdocs/` |

TAG 判定文件（权威源）在 `agent_workspace/tag_pipeline/`：官方 TAG 分模块 `official_tags/[A-I]-*.json`，玩家 TAG 分文件 `player_tags/NN-*.json`；机读字典与 `stats.json` 同目录。工作区索引见 `agent_workspace/README.md`。