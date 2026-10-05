# agent_workspace —— agent 工作区索引

本目录存放 TAG 数据生产过程中由 agent 生成、维护的内容与中间产物。各子目录用途如下：

| 子目录 | 放什么 | 是否进库 |
|---|---|---|
| `tag_pipeline/` | TAG 判定文件与机读字典：`official_tags/`（官方 TAG 分模块）、`player_tags/`（玩家 TAG 分文件 + `_brief.md` + 合并/荐脚本 + `_reverify/` 复算工作区）、`catalog.json`／`char_ids.json`／`deterministic.json`／`stats.json`／`merged.json`／`final_lists.tsv` 等 | 是（其中 `_reverify/items.jsonl`、`parts/`、`slices/`、`reports/` 为本地中间物，不进库） |
| `_out/` | 临时批次目录：子代理产出（如 `<批名>.json`）、名单文件、抽取脚本与调查记录 | 否（本地） |
| `workdocs/` | 工作稿：《待裁定.md》（待开发者裁定）、《待验证复算.md》（复算复核）；模板在 `docs/templates/` | 否（本地） |
| `handoff/` | 转交状态快照 `state.md`（由 `handoff` 技能读写） | 否（本地） |

约定：

- `tag_pipeline/official_tags/[A-I]-*.md` 与 `tag_pipeline/player_tags/NN-*.md` 是**判定内容的权威源**（GUI 与技能写回的目标），改动后需运行对应合并脚本重新生成 `docs/` 下的名单文档。
- `tag_pipeline/stats.json` 由 `tools/prts_stats.py` 从 PRTS 语料抽取，是面板与档位的唯一取数处；不手改。
- 临时产物一律写 `_out/`；`workdocs/`、`_out/`、`handoff/` 与 `_reverify/` 的批处理中间物均被 `.gitignore` 排除。