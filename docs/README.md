# docs 文档索引

本目录是判定规范、规则正本与文档的集合。**权威源**文件是改动的目标；**生成物**由脚本重生成，不要手改。

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
| `player-tags-explain.md` | 玩家 TAG 的通俗说明源文件（生成 `results/player-tags-explain.json`） |
| `operators.txt` | 干员与 PRTS 页面链接清单（爬虫的输入） |

## 判定作业（agent 与维护者）

| 文档 | 内容 |
|---|---|
| `agent-primer.md` | 作业记忆包：游戏常识、仓库作业常识、反面清单（新会话与子代理开工必读） |
| `version-update-quickstart.md` | **版本更新快线**：非结构性更新（新干员/新模组）的唯一开工必读——七步流程、预核验清单、验证最低集与审核规则 |
| `scan-protocol.md` | 全表扫描流程：名单文件、逐人决断、独立复核 |
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