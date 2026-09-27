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

本仓库（明日方舟干员 TAG 数据生产线）工作区里叠着**两批未提交的改动**：① 上一批（**特限／通用两线分别计算**、连射「可攻击到 3 格远」门槛、条件取消字数上限、**倍率与面板解耦**、**潜能档一律取**）；② 本批＝开发者对上一份《待裁定.md》6 条回复的全部落地——**「吃拐一轮秒」新增硬门槛「上拐单位数 ≤1」**（移出 电弧／伺夜；机械师／死芒／鸿雪 改记「仅本体」）、**夕「化境」按潜能5 的 18 层折入**、**提丰距离门槛写进条件**、**全库「只写与本 TAG 相关的内容」重扫**（12 个玩家分文件、474 行重排）、新增 `docs/module-hidden-mechanics.md`（模组「※」隐藏机制汇编）。校验六项全绿（数值可疑 0／文本 lint 0／守恒 0／GUI 0 错误／证据层见 §6 遗留）。**工作未提交**。

## 1. 开工必读（按此顺序，别跳）

1. `CLAUDE.md`（会话自动加载，讲仓库结构与铁律）。
2. `docs/agent-primer.md` —— 作业记忆包（解锁关系、**2★及以下无专精**、作业常识、反面清单）。
3. `docs/rulings.md` —— **裁定台账**（本批新增 4 条：条目只写与本 TAG 相关的内容／吃拐一轮秒：上拐单位数 ≤1／提丰：距离增伤的距离门槛／夕：化境（击杀叠攻）的折入与层数）。**判断类问题先查它**。
4. 根目录 `待裁定.md` —— **当前待开发者裁决**：一、新子 TAG「慢热」的判定算法（含 4 个口径点）；二、本轮重扫冒出的**存量**口径项 2.1–2.10（段数计入、取档一致性、与评定标准相抵的行、官方 TAG 内部代号等）。
5. 任务涉及的文件：`player_tags/NN-*.md`、`official_tags/[A-I]-*.md`、`docs/calc-rules.md`、`docs/concept.md`、`docs/ui-render-rules.md`、`docs/output-standard.md`、`docs/module-hidden-mechanics.md`（模组「※」隐藏机制汇编）。

## 2. 三条硬纪律（违反过，代价明确）

1. **未经裁定不得自行改动**：开发者明确要求改的必须动；**你自己发现「可能需要修改」的，只能写进《待裁定.md》问过再动**。
2. **裁定四步缺一不可**：裁定 → 折入正本 → **登记 `docs/rulings.md`** → 才移除/替换《待裁定.md》。
3. **《待裁定.md》必须自包含**：背景＋现状＋候选＋算式与出处；**自创词与模组线当场解释**（开发者明令「不得假设知识对齐」）。

## 3. 现场约定（踩过的坑，直接照办）

- **回填分文件一律用 `_apply_batch.py`**（按表头定位列、以 HEAD 重建整行）：键＝干员名，同名多行写 `干员名（子表名）`（须与该表上方最近的小节标题匹配；`（2技能）` 这类非标题标签不会命中）；`--keep-prefix` 保留 `救急路径：`／`子 TAG：` 前缀——**若代理产出文本已自带该前缀，回填后会重复，须事后去重**（`^(救急路径：…；)(救急路径：…)` 与 `^\*\*…\*\*；` 两种形态都要处理）。
- **子 TAG 列与成员增删不由回填脚本管**；被移除行带走的 `文件:行号` 要登记 `strip_prts_noncombat.ACCEPTED`。
- **`audit_text_migration.ACCEPTED` 同名键必须合并**（令牌取并集、理由相接），批量登记后跑一次去重；**依据列只可加、不可改同一 token**（`文件.md:1,2` 与 `文件.md:1` 是两个 token，改写会报「依据丢失」——要整段保留旧 token 另起一段写新行号）。
- **两线呈现写法**：成绩块情形名＝模式名（`集成战略特限`／`生息演算特限`／`岁的界园志异特限`）或 `通用线`，特限排前；「最低可满足档」排最前；某线无贡献则只写贡献线＋说明。
- **倍率与面板解耦**：写数值前先问「这是倍率还是绝对值」——固定点数／召唤物伤害只进绝对值（总伤／DPS／每秒），倍率只写百分比结构。
- **派 TAG 改写类子代理**：用 `.claude/agents/tag-rewrite` 代理类型；产出写 `_out/*.json`（**顶层包 `{"Pnn": …}`**）；prompt 里点名「纯固定攻击的更高档不取」「两线呈现格式」「倍率解耦」三条，否则会被读反。
- 证据只进「依据」列；产物里不得出现范围代号、`S1/S2/S3`、模组档码、`表 2A`、`路径⑤`、分文件名。
- **回填会不会回退「依据」列**：`_apply_batch.py` 以 **HEAD** 重建整行（只替换条件／备注两格）——工作区若有与 HEAD 不同的「依据／编号／子 TAG」，回填即被回退。动手前后各跑一次 `_out/_cols_snap.py`（对比 `_out/_snap/` 快照，`--fix` 按快照写回）。
- **P05（插拔容错）回填必须加 `--no-head`**：HEAD 的备注前缀是 `**救急路径：…**；`（带粗体），带回来会让 `generate_results` 的前缀正则解析不到、整批丢子 TAG；工作区才是当前态。仍配 `--keep-prefix`。
- **换行坑**：临时脚本写分文件一律 `p.write_bytes("\r\n".join(lines).encode("utf-8"))`——用 `write_text` 会因文本模式把 `\r\n` 再转义成 `\r\r\n`（每行后多一个空行），整张表解析崩掉，表现为 `generate_results --check` 报「荐『X』不是本 TAG 的成员」。发现后按 `b"\r\r\n" → b"\r\n"` 修回。
- **`ACCEPTED` 同名键必须合并**：字典字面量里重复键只有**最后一个**生效——批量登记后必须跑一次去重（`_out/_dedupe_accepted.py`，令牌取并集），否则先登记的令牌被静默丢弃、审计永不收敛。
- **审计默认只打印前 30 条**：登记放行表时用 `AUDIT_ALL=1` 让 `audit_text_migration.py` 全量输出（`_out/_mk_accepted.py` 已内置）。

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

## 5. 状态快照（转交时：2026-09-28 凌晨）

- **产物**：`results/operator-tags.json`（**v6**）400 干员 / 91 TAG / **1702** 条关系；前端已复制（md5 `3b0b15f5256f8d628976573fa308aae5`）。
- **本批成员变动**：吃拐一轮秒移出 **电弧／伺夜**（桑特拉／狼群按自身攻击力结算、须分别上拐）；机械师／死芒／鸿雪 改记「仅本体」（鸿雪 261.95%→**267.75%**）；令 按上拐条**不收**（结论已写进边界记录 I 节）。
- **规则改动**：台账 +4 条；`docs/concept.md`（新增「只写与本 TAG 相关的信息」＋重写「数值可复算」）、`_brief.md`、`docs/agent-primer.md`（反面清单 +1；不取档理由不进产物）、`CLAUDE.md`（And nothing unrelated）、`docs/calc-rules.md`（去掉四处「并在说明写明理由」）、`.claude/agents/tag-rewrite.md`、`docs/term-map.md`、`docs/player-tags-specify.md`（上拐门槛）、`verify_numbers.py`（模式限定模组按名解析 α／β＋14 条 REVIEWED_TIERS）、`audit_text_migration.py`（`AUDIT_ALL`）、新增 `module_notes.py`。
- **登记项**：`verify_numbers.REVIEWED_TIERS` **36 条**（本次触发 24 条）；`audit_text_migration.ACCEPTED` **388 键**（其中约 330 条为本轮重扫的删块放行）；`strip_prts_noncombat.ACCEPTED` 已补 **16 条**（电弧／伺夜 移出行与被重写备注里内联证据带走的引用）。
- **遗留**：`_out/` 保留 16 份批次产出（`P*.json`）与 `重扫改动清单.md`（块级逐行改动，供复核）；其余临时件已清。

## 6. 未完成的目标（接手后的第一件事）

1. **等开发者回复** 根目录 `待裁定.md`：一、**新子 TAG「慢热」的算法与 4 个口径点**（评准定死前不要动成员）；二、重扫冒出的存量口径项 **2.1–2.10**（逐条候选，未圈选者维持现状）。
2. **收尾**：六项校验**已全绿**（数值可疑 0／text lint 0／守恒 0／证据层失效 0／GUI 0 错误／属性层异常 0）；`_out/` 已清（保留批次产出与改动清单）。
3. **本批交付报告**在 `_out/重扫改动清单.md`（块级逐行改动清单，供复核）。
4. **提交**：按仓库惯例不主动 commit——开发者过目后发话，提交前派子代理做一次证伪式复核（`[[independent-review-before-commit]]`）。
