---
name: reverify-numbers
description: 「（待验证）」数值条目的复算与回填流程（extract/check/report/apply/verify，fetch-rules 刷新机制页快照）。Use when results/operator-tags.json contains（待验证）entries that need recomputation and review, or when the material_datas/PRTS/_rules/ snapshots must be refreshed. 触发词：（待验证）、复算、复算与回填、reverify。
---

# （待验证）复算流程（reverify-numbers）

## 目录与脚本

- 脚本：`.claude/skills/reverify-numbers/scripts/reverify.py`
- 工作区：`agent_workspace/tag_pipeline/player_tags/_reverify/`（`items.jsonl`／`parts/`／`slices/`／`reports/` 为本地中间物，不进库；`rules.md` 为复算作业规范）
- 复核文件：`agent_workspace/workdocs/待验证复算.md`（本地工作稿；模板见 `docs/templates/待验证复算.md`）
- 数值规则正本：`docs/calc-rules.md`；机制页快照：`material_datas/PRTS/_rules/`

## 子命令

```bash
.venv/Scripts/python.exe -X utf8 .claude/skills/reverify-numbers/scripts/reverify.py extract   # 抽出（待验证）条目 → items.jsonl
.venv/Scripts/python.exe -X utf8 .claude/skills/reverify-numbers/scripts/reverify.py check     # 算术自检与证据校验
.venv/Scripts/python.exe -X utf8 .claude/skills/reverify-numbers/scripts/reverify.py report    # 渲染《待验证复算.md》
.venv/Scripts/python.exe -X utf8 .claude/skills/reverify-numbers/scripts/reverify.py apply --dry-run
.venv/Scripts/python.exe -X utf8 .claude/skills/reverify-numbers/scripts/reverify.py verify    # 重生成后的验收
.venv/Scripts/python.exe -X utf8 .claude/skills/reverify-numbers/scripts/reverify.py fetch-rules  # 刷新 _rules/ 快照
.venv/Scripts/python.exe -X utf8 .claude/skills/reverify-numbers/scripts/reverify.py lint      # S1–S11 巡检
```

## 规则与留痕

- 复算结论与回填行走复核文件；一切需要开发者裁决的问题走 `agent_workspace/workdocs/待裁定.md` 流程（先查 `docs/rulings.md`），裁定后折入正本并在台账登记。
- 分文件在复算期间被手工修订时，用 `_reverify/refresh_lines.py` 只重定位（items.jsonl 的 `loc` 字段＝`b<块序>r<行序>`，见 reverify.iter_part_rows），不重跑 extract。