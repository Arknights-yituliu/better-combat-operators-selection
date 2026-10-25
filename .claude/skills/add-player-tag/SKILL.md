---
name: add-player-tag
description: 给本项目新增一个玩家体感 TAG。当开发者说想 新增/添加 一个 TAG、创建一个新的玩家体感 TAG、或扩展 TAG 体系时使用（触发词：新增tag、新增TAG、添加TAG、新TAG、add player tag）。第一件事永远是把评定标准问清楚——除非开发者选择「先创建此 TAG、评定标准后续更新」的 stub。
---

# 新增一个 TAG

## 第 0 条 —— 动任何成员之前，评定标准必须没有歧义

一个 TAG 的评定标准决定此后的每一次判定：成员扫描、证据、UI 筛选。含糊的定义（「像 XX 那样的干员」）不是评定标准。**没问清之前绝不猜、也绝不开扫成员**——问开发者，直到下面每一点都有答案：

1. **纳入标准** —— 哪些机制／行为算；若有多条路径，逐条点名。
2. **排除边界** —— 开发者**不要**纳入的近失情形（请他点出 2–3 名边界干员）。
3. **条件 vs 备注** —— 哪些算硬性要求（精英化／技能／专精／模组与等级／模式限定／目标限制），哪些算加工后的信息（数值、时长、隐藏机制、战术用法）。
4. **方向与对象** —— 对友方／对自身／对敌方；单体还是群体；有没有来源限制。
5. **子 TAG** —— 该 TAG 是否需要「实现方式／类型／范围」这类子 TAG。
6. **时间无关性** —— 确认标准是机制层的（不写强度榜／当期环境结论）。

问题有选项形态时用 AskUserQuestion，否则用普通文字。**最少问一轮**；答案仍然含糊时，明确指出哪一部分不清楚并再问。

如果开发者只给了几个例子或含糊表述，先走 `.claude/skills/solidify-criteria/SKILL.md`（回源枚举样例 → 逐条裁定 → 提炼可量化标准 → 样例回归验证），再回到下面的成员工作。

## 提供 stub 选项

每次评定标准还没说清时，都把这一项作为明确选项提出来：

> **先创建此TAG，评定标准后续更新** —— 现在先建 TAG，评定标准之后再补。

开发者选了它的话：

- 建 `agent_workspace/tag_pipeline/player_tags/NN-<TAG名>.json`（tag-part/1；NN＝下一个可用编号）——最小骨架：`{"format":"tag-part/1","kind":"player","num":"NN","name":"<TAG名>","title":"# <TAG名>","body":[{"t":"heading","level":2,"text":"## 评定标准"},{"t":"p","lines":["（[待考] 原始定义）"]},{"t":"heading","level":2,"text":"## 成员表（按实装时间倒序）"},{"t":"table","columns":["干员","编号","条件","备注","依据"],"rows":[]},{"t":"heading","level":2,"text":"## 待开发者确认"},{"t":"p","lines":["- …"]}],"trailing_newlines":1}`，写完用 `partdoc.load()` 自检，并**同时登记** `_merge_to_docs.py` 的 `TAGS` 与 `partdoc.PLAYER_ORDER`。
- 登记该 TAG：加进 `player_tags/_merge_to_docs.py` 的 `TAGS` 列表，并在新分文件里写出它的评定标准小节。
- `docs/player-tags-specify.md` 由开发者手改——请他自己加定义句，不要代改。
- 跑合并脚本，让 stub 出现在 `docs/player-tags-members.md` 里。

## 评定标准说清之后

1. **定编号与文件名**：`NN-<TAG名>.json`（现有分文件为 `01-…`–`09-…`、`13-…`、`12-…`，共 11 个）。
2. **登记**：`_merge_to_docs.py` 的 `TAGS` 与 `partdoc.PLAYER_ORDER`（两处都改）；`docs/player-tags-specify.md` 由开发者更新。
3. **写 `## 评定标准`**，遵循 `docs/classification-conventions.md` 的评定标准写法规则：统一用「评定标准」这个词（绝不用 口径 或 裁决）、不写日期、不留编辑痕迹；有多条路径时编号；写明边界与否决项。
4. **成员扫描**：由评定标准里的关键词驱动全库检索（`material_datas/PRTS/` 下的 PRTS 页面 ＋ `deterministic.json`）；每条纳入与排除都引 `文件:行号`；召唤物／装置算持有者的能力；模式限定模组（ISW-α／RA-α／SO-α…）计入，并把模式写进条件。
5. **边界记录**：纳入存疑／明确排除，各写理由＋证据；未决项进 `## 待开发者确认`。
6. **跨 TAG 检查**：与其它每个 TAG 的主表比对，更新两侧的「多 TAG 并存」记录。
7. **合并与核对**：跑 `.venv/Scripts/python.exe -X utf8 agent_workspace/tag_pipeline/player_tags/_merge_to_docs.py`，核对总览行数与 diff。

## 禁止

- 不得自行发明评定标准，也不得静默收窄／放宽它；不得凭模型记忆判定。
- 不得往评定标准小节写日期、轮次标记（「本轮新增」）或「覆盖上一轮…」这类措辞。
- 不得自行编辑 `docs/player-tags-specify.md`——它属于开发者。
