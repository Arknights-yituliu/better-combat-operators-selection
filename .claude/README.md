# .claude —— agent 资源索引

本目录是仓库的 agent 资源：作业技能（skills）与子代理定义（agents）。入口文档是仓库根的 `AGENTS.md`。

## 技能（skills/）

| 技能 | 何时触发 |
|---|---|
| `add-new-operator` | 新干员实装：爬取 → 逐 TAG 判定 → 询问未覆盖机制 → 更新名单文档 |
| `update-version` | 版本增量更新：新增干员与／或已有干员新模组，只刷新受影响条目并跑跨干员影响清单 |
| `add-player-tag` | 新增玩家体感 TAG（先与开发者把评定标准说清楚，或显式选择先建 stub） |
| `solidify-criteria` | 评定标准只有例子／模糊表述时：回源枚举样例 → 逐条请开发者裁定 → 提炼可量化标准 → 回归验证 |
| `crawl-prts-operator` | 爬取／重爬干员语料与攻击范围，含爬虫内部与坑位说明 |
| `tag-batch-rewrite` | 批量回填（`_apply_batch.py`）与条件／备注重排的守恒审计 |
| `reverify-numbers` | 「（待验证）」条目的复算与回填，以及 `_rules/` 快照刷新 |
| `handoff` | 会话转交：把当前工作完整交给新窗口（状态快照在 `agent_workspace/handoff/state.md`） |

## 子代理（agents/）

| 代理 | 用途 |
|---|---|
| `tag-rewrite` | 条目改写／复算专用：产出 `agent_workspace/_out/<批名>.json`，不直接改分文件，由主进程统一回填 |

## 典型工作流

1. 开发者提出任务（新干员 / 版本更新 / 新增 TAG / 标准修订 / 条目复算）；
2. 按 `AGENTS.md` 与对应技能执行；大批量改写派 `tag-rewrite` 子代理，产出写 `agent_workspace/_out/`；
3. 用 `tag-batch-rewrite` 回填并做守恒审计；
4. 重跑合并与生成脚本，最后跑 `tools/run_all_checks.py`。

## 兼容性

- `AGENTS.md` 是通用入口（Claude Code、OpenCode、Codex 等均可读取）。
- `.claude/skills/` 下的技能可被 Claude Code 与 OpenCode 等读取；`.claude/agents/` 是 Claude Code 的子代理定义。
- 技能中示例命令以 Windows 写法（`python`）为主，POSIX 环境替换为 `.venv/bin/python`。