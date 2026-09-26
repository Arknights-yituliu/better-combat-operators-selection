---
name: handoff
description: >-
  会话转交：把当前工作完整交给一个新窗口。用于上下文将满需要承接、或新会话接手本仓库正在进行中的任务。
  内容＝开工必读顺序 ＋ 截至转交时的状态快照 ＋ 未完成的目标与待裁定项 ＋ 现场约定（踩过的坑）。
  触发词：转交、接手、handoff、上下文将满、新窗口继续。
  注意：本 skill 的「状态快照」一节有时效——它记的是转交那一刻的进度；与仓库文件冲突之处，一律以文件为准。
---

# 转交（handoff）

## 0. 一句话现状

本仓库（明日方舟干员 TAG 数据生产线）本轮完成了**开发者对上一份《待裁定.md》10 条回复的折入**（聚爆新增每次攻击倍率门槛、模组取档改绝对贡献口径、默认敌人＝纯木桩、条件性增伤一律折入、特限证章优先、远程消耗去「持续/反复」等）＋**流程修复**（《待裁定.md》撰写标准加「不得假设知识对齐」）。校验：`prts_stats`／`verify_numbers`／`generate_results`／`audit_text_migration`／`strip --audit`／`recommend_gui --check` **五项全绿**，`generate_results --check` 的**文本 lint 13 条**（「条件 50 字上限」与「前提必写进条件」的冲突，见《待裁定.md》三）。**工作全部未提交**，等开发者发话。

## 1. 开工必读（按此顺序，别跳）

1. `CLAUDE.md`（会话自动加载，讲仓库结构与铁律）。
2. `docs/agent-primer.md` —— **作业记忆包**：游戏常识（技能按精英阶段开放、**专精需精英2＋技能 7 级**、**模组解锁需精英2**）、仓库作业常识、**反面清单**（含「默认敌人是纯木桩」「取档按绝对贡献」两条）。
3. `docs/rulings.md` —— **裁定台账**：开发者对判断类问题的裁定（裁定／理由／适用范围／折入位置）。**判断类问题先查它，别再问第二遍**；开头的「零、流程纪律」是硬约束。
4. 根目录 `待裁定.md` —— **当前待开发者裁决的 10 条**（本轮折入过程中新发现的边界项，自包含）。
5. 任务涉及的文件：玩家 TAG 分文件 `material_datas/tag_pipeline/player_tags/NN-*.md`、官方 `official_tags/[A-I]-*.md`、规则正本 `docs/calc-rules.md`、写法规范 `docs/concept.md`、产物规范 `docs/output-standard.md`。

## 2. 三条硬纪律（违反过，代价明确）

1. **未经裁定不得自行改动**：开发者明确要求改的必须动；**你自己发现「可能需要修改」的，只能写进《待裁定.md》问过再动**。
2. **裁定四步缺一不可**：裁定 → 折入正本 → **登记 `docs/rulings.md`** → 才移除/替换《待裁定.md》。
3. **《待裁定.md》必须自包含**：每条给背景、现状、候选、**算式与出处**；文中任何**自创词当场解释**（模组线如 X／Y 模组必须给出完整描述——开发者明令「不得假设知识对齐」）。

## 3. 现场约定（踩过的坑，直接照办）

- **回填分文件一律用 `_apply_batch.py`**（按表头定位列、以 HEAD 重建整行）：各 TAG 成员表列数不同，按固定列号写会把条件写进子 TAG 列。已扩展：① 键支持 `干员名（子表名）` 消歧（同名多行，如次数对策的「多段伤害／间隔伤害」）；② `--keep-prefix` 的正则同时认 `救急路径：…；` 与 `**救急路径：…**；`；③ 行只在工作区存在时（HEAD 无）取工作区行。
- **保留行首机器协议前缀**：插拔容错的 `救急路径：…；`、充电的 `子 TAG：…。` 由生成器解析成 `subTags`——**重写行时若整行不带它，`subTags` 会静默丢失**（本轮修过一次 15 行丢失）。
- **`audit_text_migration.ACCEPTED` 同名键必须合并**（令牌取并集、理由相接）：重复键会让**后一条遮蔽前一条**的令牌，审计随即报「数字丢失」。
- **行内引用 `文件:行号` 的前一个字符不要用「」**：`strip_prts_noncombat` 的引用键正则在 ASCII 引号处断键，改写成「」会让键变长、审计误报「失效」（要么保留 ASCII 引号，要么让引用前有空格）。
- **派 TAG 改写类子代理**：用 `.claude/agents/tag-rewrite` 代理类型（其 system prompt 已含记忆包＋台账＋写法＋自查）；产出写 `_out/*.json`（**顶层要包一层 `{"Pnn": {...}}`**，否则 `_apply_batch` 会整份跳过），由主进程回填。
- **子 TAG 列与成员增删不由回填脚本管**：`_apply_batch` 只替换「条件」「备注」两格——改子 TAG（如傀影 聚爆→连射）或增删行要手工做。
- 证据只进「依据」列；产物里不得出现范围代号、`S1/S2/S3`、模组档码、`表 2A`、`路径⑤`、分文件名。

## 4. 校验套件（改完必跑）

```bash
.venv/Scripts/python.exe -X utf8 prts_stats.py --check          # 属性层覆盖率（异常 0）
.venv/Scripts/python.exe -X utf8 verify_numbers.py              # 数值校准（数值可疑 0；「档位取舍已复核」是已裁定的不取档）
.venv/Scripts/python.exe -X utf8 generate_results.py --check    # 生成 + 文本 lint（当前 13 条＝前提长度冲突，见《待裁定.md》三）
.venv/Scripts/python.exe -X utf8 audit_text_migration.py        # 守恒（数字/依据/结构 0）
.venv/Scripts/python.exe -X utf8 strip_prts_noncombat.py --audit # 证据层（失效 0）
.venv/Scripts/python.exe -X utf8 recommend_gui.py --check        # GUI 规范（0 错误 0 提醒）
```

改完 `results/operator-tags.json` 后**必须复制到前端**（`D:/development-projects/contribution-projects/ark-yituliu/frontend-v2-plus/src/static/json/combat/operator-tags.json`）并核对 md5。

## 5. 状态快照（转交时：2026-09-26 晚）

- **产物**：`results/operator-tags.json` 400 干员 / 91 TAG / 1713 条关系；前端已复制（md5 `7dcf6efe…`）。
- **本轮成员变动**：无增删；**傀影**由聚爆改判连射（走 03 的子 TAG 列）；其余为本轮裁定的数值/措辞重写（约 250 行：01/02/03/04/05/07/08/09/12）。
- **规则改动**：`docs/calc-rules.md`（木桩前提、取档绝对值、条件性增伤折入、C5 修正）、`docs/rulings.md`（+10 条、改 5 条旧条）、`CLAUDE.md`、primer、term-map、concept、`_brief.md`、`_merge_to_docs.py`、`_reverify/rules.md`（R16/R19/R25）、tag-rewrite 代理定义、各 TAG 约定与 03／04 评定标准、`player-tags-specify.md`。
- **登记项**：`verify_numbers.REVIEWED_TIERS` 18 条（理由按绝对贡献标口径重写）；`audit_text_migration.ACCEPTED` 134 键；`strip_prts_noncombat.ACCEPTED` 未动。
- **遗留**：根目录 `待裁定.md` ＝新一轮 10 条；`_out/` 已 gitignore（待清空）；`_merge_accepted.py` 待删。
- **工具改动**：`_apply_batch.py`（消歧键、前缀正则、工作区兜底行）；`.gitignore`（+`_out/`）；`_apply_batch.py` 已登记进 `CLAUDE.md` 工具清单。

## 6. 未完成的目标（接手后的第一件事）

1. **等开发者裁定**根目录 `待裁定.md` 的 10 条——最要紧：**特限优先遇到「特限值更低」**（一）、**鸿雪打字机折算**（二）、**条件 50 字上限 vs 前提必写**（三，唯一让 lint 非 0 的项）。
2. **`_out/` 清空**（按开发者答复：`_out/` 加 .gitignore 并清空、删 `_merge_accepted.py`、留 `_apply_batch.py`）——本轮收尾时执行。
3. **冷启动演练结论**（本轮已跑）：`tag-rewrite` 代理类型可用；代理能自行产出合规文本，但**两点需在派活时点名**：产出 JSON 必须包 `{"Pnn": …}` 顶层键；取档口径「只加固定攻击的更高档不取」要写进 prompt，否则会被读成「一律取最高档」。
4. **提交**：按仓库惯例不主动 commit——开发者过目后发话，提交前派子代理做一次证伪式复核（`[[independent-review-before-commit]]`）。
