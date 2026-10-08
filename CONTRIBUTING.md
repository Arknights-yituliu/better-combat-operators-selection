# 贡献指南

## 改动 TAG 数据

1. **先读规范**：条目写法见 `docs/concept.md`（条件分条／备注分块），产物结构见 `docs/output-standard.md`；判定依据先查 `docs/rulings.md` 裁定台账。
2. **一切判定以证据为准**：引用 `material_datas/PRTS/` 下语料的「文件:行号」，不要凭印象或记忆判断。
3. 选择路径：
   - 少量改动：用维护面板（`start_gui.bat` / `./start_gui.sh`），或直接编辑 `agent_workspace/tag_pipeline/` 下的分文件；
   - 批量／复杂改动：按 `.claude/skills/` 中对应技能的流程由 agent 执行（作业指南见 `AGENTS.md`）。
4. 改完分文件后按需重跑合并与生成脚本（命令见 `AGENTS.md` 的「Commands」）。

## 提交前

```bash
python -X utf8 tools/run_all_checks.py
```

全量校验通过后再提交。以下本地文件不要提交（已在 `.gitignore`）：`agent_workspace/_out/`、`agent_workspace/workdocs/`、`agent_workspace/handoff/`、`agent_workspace/tag_pipeline/player_tags/_reverify/` 的批处理中间物、`local.json`、`docs/temp.txt`、`material_datas/videos/` 等。

## 新增干员／版本更新

走对应技能：`.claude/skills/add-new-operator/SKILL.md`、`.claude/skills/update-version/SKILL.md`；新增 TAG 走 `.claude/skills/add-player-tag/SKILL.md`。

## 文档与产物

- `docs/` 下标注为「生成物」的文件由脚本重生成，不要手改；改其源文件后重跑生成。
- 交付 JSON（`results/`）由 `tools/generate_results.py` 生成；需要同步到消费端时，用 `local.json` 配置路径并运行 `tools/sync_results.py`。