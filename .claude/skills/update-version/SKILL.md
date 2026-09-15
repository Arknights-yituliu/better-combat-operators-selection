---
name: update-version
description: Incrementally fold a game-version update into the TAG system — the developer provides a new operator's info and/or modules newly added to existing operators; refresh only the changed operators, fold new modules into the affected rows (模组档位), then run the cross-operator impact checklist (new faction members, new enablers, new ally-facing hooks). Use when the developer announces a version/patch update, new modules on existing operators, or asks to update affected entries without re-scanning the whole corpus. Never a full-table rescan.
---

# Apply a version update (版本增量更新)

Fixed pipeline: **refresh what changed → judge the new operator → fold new modules into affected rows → run the cross-operator impact checklist → merge docs only.**

## 0. Inputs

- The developer provides one or both of: **new operator(s)** (PRTS link(s) or a manual description, judged as in `add-new-operator`), and **new modules on existing operators** (a list such as `干员名 — X模组2/3级，效果…`, or a link to the module).
- Efficiency rule: this skill exists because a full-table rescan is expensive. Touch **only** the operators involved and the existing entries the update can affect (§4). Do not re-judge unrelated operators or TAGs.
- Batch all developer questions into **one** AskUserQuestion round at the end (same as `add-new-operator`).

## 1. Refresh only what changed

1. New operator → follow `add-new-operator` §1: `docs/operators.txt` → `.venv/Scripts/python.exe -X utf8 crawl_prts.py --only "干员名"` → `crawl_ranges.py --only "干员名"` → add 上线时间 to `player_tags/_launch_dates.json` → verify per `crawl-prts-operator/SKILL.md` → "Verify after crawling".
2. New module on an existing operator → the PRTS page changed, so **re-crawl that operator with `--force`**: `.venv/Scripts/python.exe -X utf8 crawl_prts.py --only "干员名" --force`; re-run `crawl_ranges.py --only "干员名"` if the module touches ranges/grids (`攻击范围.md`). Verify the same way.

## 2. Judge the new operator

Follow `add-new-operator` §2–§3 (机制词表粗筛 → 官方设定 TAG → 玩家体感 TAG → ask about mechanics no TAG covers). Apply `docs/player-tags-members.md` §0: **多项特性只要各自符合评定标准都要写**; **模组档位**（条件写模组名+等级、备注取该档位数值）; 「（待验证）」范围.

## 3. Fold new modules into the affected rows

For each new module on an existing operator:

1. Locate **every** row of that operator across `player_tags/NN-*.md` (12 files) and `official_tags/[A-I]-*.md`.
2. Judge per row whether the module **enhances the capability that row judges**:
   - Yes → 条件 adds the module name + level, 备注 switches to that tier's values (recompute derived numbers; keep the「（待验证）」rule for 攻速/间隔换算与倍率相乘类推算值), 依据 gains the module's `文件:行号`.
   - Several modules → each TAG row picks the module serving **its own** capability (worked precedent: 温蒂 — 10-大力推拉 uses PUS-Y 推力档, 07-充电 uses PUS-X 技力档; 空弦 — 02 uses MAR-X, 05 uses MAR-Y, 07 uses X2/X3 + ISW-α, 08 uses ISW-α). Two modules enhancing the same capability → list both routes (precedent: 迷迭香「X模组1级 或 ISW-α模组1级」).
   - Irrelevant modules stay unmentioned; vague phrasing like「X模组更佳／可选」must be replaced by explicit tiers + values (or dropped if irrelevant).
3. Official rows follow the official rules (只记原文；**模式限定模组不计**；条件写模组名+等级、备注引原文档位).

## 4. Cross-operator impact checklist

A new operator / module can change **existing** entries of **other** operators. Screen the update's capabilities against these dimensions and act on the ones it actually carries. ✅ = precedent verified in this repo; 🔶 = possible, judge from evidence:

1. ✅ **为他人提供初始技力/部署时技力** → `05-插拔容错` 路径④ (风笛 precedent: 夜半/嵯峨 rows carry「需编入风笛」; 风笛「军事传统」+6), `06-初动增加`.
2. ✅ **部署支援**（待部署区费用/排序/投送/回场/零冷却重部署）→ 05 路径⑥, 04 (凛御银灰【协同攻击】/风雪之眼, 凯尔希·思衡托 返回待部署区, 新约能天使 投送).
3. ✅ **借用位置/射程挂点**（把打击/伤害投送到友方所在处）→ `04-远程消耗` 表 1 行的条件 (结城理「需场上有其他【S.E.E.S.】干员」、佩佩「需场上有其他【近卫】干员」、新约能天使「需场上有携带弹药类技能的友方」、隐德来希「全场最后部署地面友方」…).
4. ✅ **使友方进入特定状态**（起飞/弹药被消耗/被击倒/受击/被阻挡）→ 04/08/09 以此为条件的行 (予愿安洁莉娜「仅对处于『起飞』状态的友方」、新约能天使 弹药消耗、归溟幽灵鲨 ISW-α3「其他干员被击倒」).
5. ✅ **同阵营/小队成员** → `12-阵容组合`: 各组合的「可用受益干员」bullet（受益名单是否含新成员）、计数池（岁 7/莱欧斯小队 4/S.E.E.S. 4/格拉斯哥帮 5）、满编门槛（「编队中有 N 名【X】干员」）、组合整体机制文本、可能成立的新组合；`04` 的 S.E.E.S./拉特兰/谢拉格 条件行。名单推导＝各干员 md `## 属性` 的「所属势力 ∪ 隐藏势力」（见 12 的检索记录写法）。
6. ✅ **为他人改变费用/费用下限** → `12` 交叉引用（凛冬/德克萨斯/野鬃/松桐…）、official C-4.
7. ✅ **为他人缩减再部署** → `05` 路径①/⑥ (贾维→支援机械、银灰→可部署单位、砾→卡西米尔).
8. ✅ **为他人加攻/攻速且带成员门槛** → `08-拐杖` 带条件的行（桑葚「另有至少 1 名【医疗】」、黑「另一名【狙击】」、迷迭香「场上术师」——新干员若供给这些门槛状态需复核）.
9. ✅ **为他人回复技力/补弹/弹药上限** → `07-充电`（「同类取最高」类备注会被新值/新档位影响）、`06`.
10. ✅ **对友方的保护类**（屏障/迷彩/闪避/免死/承伤）→ `09-保人` 带他人条件的行（帕拉斯「身前一格部署我方干员」、余「场上干员数≥4」、凯尔希·思衡托「其他友方进入攻击范围」）.
11. ✅ **按职业/阵营计数门槛**（≥N 名同类在场/编队）→ `12`（黍 3 同/3 异职业 + 4 岁）、official D/I 类.
12. ✅ **提供起飞/浮空/失重** → `08` 的起飞条件池、`04`；🔶 失重/浮空对既有条目.
13. ✅ **为友方提高阻挡数** → `11-阻挡数5` 排除表（年 3 技能/海蒂/可露希尔「援军」…）、`12` 备注（帕拉斯 阻挡数+1）.
14. 🔶 **脆弱/易伤** → 现状 **不**计入 01/02/03 的达线倍率（只计自身/必定生效加成）；若该规则改变，大批行需重判——先问开发者.
15. ✅ **攻速下限覆写/抗削弱/抵抗净化** → 官方「抗削弱」（I 类「全场光环」按条目内评定标准例外执行）.
16. ⚠️ **召唤物/装置（假性耦合）**：计入持有者本身（`_brief` 铁律 3），**不算跨干员依赖**；但如果新效果作用于**其他干员的装置/被引用状态**（如「持有装置屏障的干员」），则复核引用该状态的行（凯瑟琳行等）.

When a dimension hits: re-verify each affected row against the PRTS text (`文件:行号`), update 条件/备注/依据; check 边界与排除记录 whose rationale no longer holds (a near-miss may now qualify, or an exclusion may need re-wording). 评定标准 are developer-owned — if the update makes a rule ambiguous, route to AskUserQuestion instead of rewriting criteria.

## 5. Finish

1. Run `.venv/Scripts/python.exe -X utf8 material_datas/tag_pipeline/player_tags/_merge_to_docs.py` and `.../official_tags/_merge_official_to_docs.py`; confirm 总览 row counts changed as expected (`git diff --stat` = only the touched files + the two merged docs + `_launch_dates.json`).
2. `recommend.py check` — if a 荐-bearing entry moved/vanished, the dangling 荐 surfaces here; report it to the developer (荐 由开发者维护).
3. `generate_results.py` only when the developer asks; never commit unless asked.
4. Known drift: the dictionary layer (`material_datas/tag_pipeline/{merged.json,final_lists.tsv}`) is **not** maintained entry-by-entry, yet some part files cite its counts as cross-anchors (08/09/12) — if the update invalidates an anchor, report it instead of silently editing the anchor text.

## Do not

- Do not rescan or re-judge operators the update doesn't touch.
- Do not classify from model memory — every judgment cites `文件:行号`; unknown items are `[待考]` → that file's `## 待开发者确认`.
- Do not create TAGs unilaterally; do not edit `docs/player-tags-specify.md` (developer-owned).
- Do not write dates, round labels or edit traces; do not commit unless asked.
