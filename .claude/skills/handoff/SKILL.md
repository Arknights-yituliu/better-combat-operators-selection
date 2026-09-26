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

本仓库（明日方舟干员 TAG 数据生产线）本轮完成了**开发者对上一份《待裁定.md》10 条的折入**＋**四项新需求的实施**：**特限模组与通用模组分别计算、UI 分别展示且特限线优先**（约 190 行改写）、**连射新增「可攻击到 3 格远」门槛**（9 行移出）、**条件取消 50 字上限**、**计算规则只作用于玩家体感 TAG**。校验：`prts_stats`／`verify_numbers`（数值可疑 0／已复核 22 条）／`generate_results --check`（文本 lint 0）／`audit_text_migration`（五类全 0）／`strip --audit`（失效 0）／`recommend_gui --check`（0 错误 0 提醒）**六项全绿**。**工作未提交**，等开发者发话。

## 1. 开工必读（按此顺序，别跳）

1. `CLAUDE.md`（会话自动加载，讲仓库结构与铁律）。
2. `docs/agent-primer.md` —— **作业记忆包**：游戏常识（技能按精英阶段开放、**专精需精英2＋技能 7 级**、**模组解锁需精英2**、**2★及以下无专精**）、仓库作业常识、**反面清单**（含「默认敌人是纯木桩」「取档按绝对贡献」「把防/抗数值减益计入」）。
3. `docs/rulings.md` —— **裁定台账**（含本轮新增：计算规则只作用玩家 TAG、特限／通用分别计算、连射可及距离、同额基线扣除、阵容组合「无用≠无助」、条件不设字数上限）。**判断类问题先查它，别再问第二遍**。
4. 根目录 `待裁定.md` —— **当前待开发者裁决的 7 条**（潜能攻击档是否一律取、鸿雪潜能4 冲突、苦艾 ⌊⌋、霍尔海雅对空读法、连射 3 格口径追认、归溟幽灵鲨特限线、六项小取舍）。
5. 任务涉及的文件：`material_datas/tag_pipeline/player_tags/NN-*.md`、`official_tags/[A-I]-*.md`、`docs/calc-rules.md`、`docs/concept.md`、`docs/ui-render-rules.md`（**模组两条线的展示**规则）、`docs/output-standard.md`。

## 2. 三条硬纪律（违反过，代价明确）

1. **未经裁定不得自行改动**：开发者明确要求改的必须动；**你自己发现「可能需要修改」的，只能写进《待裁定.md》问过再动**。
2. **裁定四步缺一不可**：裁定 → 折入正本 → **登记 `docs/rulings.md`** → 才移除/替换《待裁定.md》。
3. **《待裁定.md》必须自包含**：背景＋现状＋候选＋算式与出处；**自创词与模组线（X／Y、特限／通用线）当场解释**——开发者明令「不得假设知识对齐」。

## 3. 现场约定（踩过的坑，直接照办）

- **回填分文件一律用 `_apply_batch.py`**（按表头定位列、以 HEAD 重建整行）：键＝干员名，同名多行写 `干员名（子表名）`（子表名须与该表上方最近的小节标题匹配；`（2技能）` 这类非标题标签**不会**命中）。`--keep-prefix` 保留 `救急路径：`／`子 TAG：` 前缀（正则同时认加粗与不加粗形态）。
- **子 TAG 列与成员增删不由回填脚本管**：改子 TAG（如「聚爆、连射」→「聚爆」）或增删行要手工做；**被移除行带走的 `文件:行号` 引用要登记 `strip_prts_noncombat.py` 的 `ACCEPTED`**（否则审计报失效）。
- **`audit_text_migration.ACCEPTED` 同名键必须合并**（令牌取并集、理由相接）：重复键会让后一条遮蔽前一条；批量登记后用脚本去重。
- **两线呈现的写法**：成绩块情形名——特限线写模式名（`集成战略特限`／`生息演算特限`／`岁的界园志异特限`）并**排在通用线之前**；通用线写 `通用线`；有「最低可满足档」时它排最前。某线无贡献则只写贡献线＋「说明」交代另一条。细则见 `docs/ui-render-rules.md` §6.3。
- **连射的可及距离**按「**该干员**」判（其可用配置中存在可达 3 格的手段即达标），不按成绩所用技能单独判。
- **派 TAG 改写类子代理**：用 `.claude/agents/tag-rewrite` 代理类型；产出写 `_out/*.json`（**顶层包 `{"Pnn": …}`**，否则回填脚本整份跳过）；prompt 里要点名「纯固定攻击的更高档不取」与「两线呈现格式」两条，否则会被读成「一律取最高档」。
- 证据只进「依据」列；产物里不得出现范围代号、`S1/S2/S3`、模组档码、`表 2A`、`路径⑤`、分文件名。

## 4. 校验套件（改完必跑）

```bash
.venv/Scripts/python.exe -X utf8 prts_stats.py --check          # 属性层覆盖率（异常 0）
.venv/Scripts/python.exe -X utf8 verify_numbers.py              # 数值校准（数值可疑 0；「档位取舍已复核」是已裁定的不取档）
.venv/Scripts/python.exe -X utf8 generate_results.py --check    # 生成 + 文本 lint（0；条件已无字数上限）
.venv/Scripts/python.exe -X utf8 audit_text_migration.py        # 守恒（数字/依据/结构 0；ACCEPTED 每条一次显式裁定）
.venv/Scripts/python.exe -X utf8 strip_prts_noncombat.py --audit # 证据层（失效 0；约 2 分钟，可后台跑）
.venv/Scripts/python.exe -X utf8 recommend_gui.py --check        # GUI 规范（0 错误 0 提醒）
```

改完 `results/operator-tags.json` 后**必须复制到前端**（`D:/development-projects/contribution-projects/ark-yituliu/frontend-v2-plus/src/static/json/combat/operator-tags.json`）并核对 md5。

## 5. 状态快照（转交时：2026-09-27）

- **产物**：`results/operator-tags.json` 400 干员 / 91 TAG / **1704** 条关系（较上轮 −9＝连射移出）；前端已复制（md5 `77fc6fb5…`）。
- **本轮成员变动**：连射移出 9 行（祐天寺若麦、聆音、维娜·维多利亚、百炼嘉维尔、归溟幽灵鲨、龙舌兰、山、瑕光、傀影）＋ 麒麟R夜刀／阿米娅(近卫) 改记「聚爆」；**傀影因此退出「吃拐一轮秒」全部**。
- **规则改动**：`docs/rulings.md`（+7 条、改 3 条）、`docs/calc-rules.md`（适用范围、§4.1 取线、§4.5 同额基线）、`CLAUDE.md`、primer、term-map、concept、`docs/ui-render-rules.md`（两条线展示）、`_brief.md`、`_merge_to_docs.py`、`.claude/agents/tag-rewrite.md`、`_reverify/rules.md`（R19／+R26）、各 TAG 约定（9 文件取线句）、`03` 连射门槛、`12` 纳入、`generate_results.py`（去掉 50 字 lint）。
- **登记项**：`verify_numbers.REVIEWED_TIERS` **22 条**；`audit_text_migration.ACCEPTED` **185 键**；`strip_prts_noncombat.ACCEPTED` 含连射移出行带走的 62 条引用。
- **遗留**：根目录 `待裁定.md` ＝新一轮 7 条；`_out/` 待清空。

## 6. 未完成的目标（接手后的第一件事）

1. **等开发者裁定** `待裁定.md` 的 7 条——最要紧：**一、潜能攻击档是否一律取**（影响面最广）、**二、鸿雪潜能4 与「不得稀释」条款的冲突**、**五、连射 3 格口径追认**（关系傀影的成员归属）。
2. **收尾**：`_out/` 清空（开发者既定答复：加 .gitignore 并清空、留 `_apply_batch.py`）。
3. **冷启动演练结论（本轮已跑）**：`tag-rewrite` 代理可用；两处必须在 prompt 里点名——产出 JSON 要包 `{"Pnn": …}` 顶层键；取档口径「纯固定攻击／木桩下无增量的更高档不取」。
4. **提交**：按仓库惯例不主动 commit——开发者过目后发话，提交前派子代理做一次证伪式复核（`[[independent-review-before-commit]]`）。
