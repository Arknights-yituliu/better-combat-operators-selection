---
name: update-version
description: Incrementally fold a game-version update into the TAG system — the developer provides a new operator's info and/or modules newly added to existing operators; refresh only the changed operators, fold new modules into the affected rows (模组档位), then run the cross-operator impact checklist (new faction members, new enablers, new ally-facing hooks). Use when the developer announces a version/patch update, new modules on existing operators, or asks to update affected entries without re-scanning the whole corpus. Never a full-table rescan.
---

# Apply a version update（版本增量更新）

> **常规版本更新走「快线」**：新会话唯一开工必读＝`docs/version-update-quickstart.md`（七步流程、预核验清单、验证最低集、审核规则）。本文件是快线的**管线细则**——折模组规则（§3）与跨干员影响清单全文（§4）在此。
> **结构性更改**（改评定标准／全库重扫／增删 TAG／改计算规则正本）不走快线，按各自流程（扫描类先读 `docs/scan-protocol.md`）。

Fixed pipeline: **refresh what changed → judge the new operator → fold new modules into affected rows → run the cross-operator impact checklist → 裁定门 → merge & generate → checks.**

## 0. Inputs and efficiency rules

- The developer provides one or both of: **new operator(s)** (PRTS link(s) or a manual description, judged as in `add-new-operator`), and **new modules on existing operators** (a list such as `干员名 — X模组2/3级，效果…`, or a link to the module).
- 效率铁律：只碰更新涉及的干员与本清单命中的既有条目；**不开前置调研／方案代理**（快线文档就是路线图）；**不通读长文档**（rulings 走节级目录、评标只读目标 TAG、glossary 按词查）；**不手写一次性回填脚本**（插行/改依据/正文行/新子表走 `.claude/skills/tag-batch-rewrite/scripts/apply_ops.py`）。
- Batch **all** developer questions into **one** AskUserQuestion round at the end（审核规则：**有你认为的待裁定项 → 先裁定、裁定折入前不生成结果文件；没有 → 产物后审核**）。

## 1. Refresh only what changed

1. New operator → follow `add-new-operator` §1（含 `docs/operators.txt` 顶部插入、`crawl_prts.py --only`、`crawl_ranges.py --only`、`_launch_dates.json` 与 `char_ids.json` 登记——charId 取法见快线第 1 步、`tools/prts_stats.py` 重建）。
2. New module on an existing operator → the PRTS page changed, so **re-crawl that operator with `--force`**: `.venv/Scripts/python.exe -X utf8 crawlers/crawl_prts.py --only "干员名" --force`; re-run `crawlers/crawl_ranges.py --only "干员名"` if the module touches ranges/grids (`攻击范围.md`).
3. 两者都按 `crawl-prts-operator/SKILL.md` → "Verify after crawling" 验收；**重爬既有干员另做 `git diff` 白名单核验与行号平移预案**（PRTS 会在天赋表插入模组档位行、令其后行号平移；人工重锚＋`strip_prts_noncombat.ACCEPTED` 登记，**不跑 `--fix-stale`**——详见快线第 1 步）。

## 2. Judge the new operator

Follow `add-new-operator` §2–§3（机制词表粗筛 → 官方设定 TAG → 玩家体感 TAG → 就问无 TAG 覆盖的机制）。Apply `docs/player-tags-members.md` §0：**多项特性只要各自符合评定标准都要写**；**模组档位**（条件写模组名+等级、备注取该档位数值）；推算值按既定规则直接给出。判前先过快线的**预核验清单**（每单随发到子代理）。

## 3. Fold new modules into the affected rows

For each new module on an existing operator:

1. Locate **every** row of that operator across `player_tags/NN-*.json` (11 files) and `official_tags/[A-I]-*.json`.
2. Judge per row whether the module **enhances the capability that row judges**:
   - Yes → 条件 adds the module name + level, 备注 switches to that tier's values (recompute derived numbers), 依据 gains the module's `文件:行号`（依据列**只可整段追加**、不可改同一引用串——守恒审计按完整引用串比对）. The module's `※` hidden-mechanic lines are collected in `docs/module-hidden-mechanics.md` — **涉模组档位时按需查**（thresholds like 距离增伤的门槛格数 live only there）。
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

When a dimension hits: re-verify each affected row against the PRTS text (`文件:行号`), update 条件/备注/依据; check 边界与排除记录 whose rationale no longer holds (a near-miss may now qualify, or an exclusion may need re-wording). 评定标准 are developer-owned — if the update makes a rule ambiguous, route to the AskUserQuestion round instead of rewriting criteria.

## 5. Finish

1. 回填：既有行条件/备注 → `.claude/skills/tag-batch-rewrite/scripts/_apply_batch.py`；插行/改依据/正文行替换与插入/新建子表 → `scripts/apply_ops.py`（先 `--dry-run`）。
2. 合并：`player_tags/_merge_to_docs.py` 与 `official_tags/_merge_official_to_docs.py`；`git diff --stat` 只应含被改分文件＋两份合并文档＋登记簿（`_launch_dates.json`/`char_ids.json` 等）。
3. **审核规则与结果文件**：存在待裁定项 → 先一轮 AskUserQuestion、**裁定折入前不生成结果文件**；无 → 直接产物链、**产物后审核**。生成时成员变化须递增 `tools/generate_results.py` 的 `VERSION`（同步 `docs/untagged-operators.md`）。
4. 校验最低集：`tools/run_all_checks.py`；按改动触发——改依据/行号 → `crawlers/strip_prts_noncombat.py --audit`；改条件/备注 → `audit_text_migration.py`（预期数字/依据变化先登记 `ACCEPTED`）；档位取舍 → `REVIEWED_TIERS`。`tools/recommend.py check` 报告悬空荐（荐由开发者维护，只报告）。
5. Known drift: the dictionary layer (`agent_workspace/tag_pipeline/{merged.json,final_lists.tsv}`) is **not** maintained entry-by-entry, yet some part files cite its counts as cross-anchors (08/09/12) — if the update invalidates an anchor, report it instead of silently editing the anchor text.
6. 不提交（除开发者另行要求）。

## Do not

- Do not rescan or re-judge operators the update doesn't touch.
- Do not classify from model memory — every judgment cites `文件:行号`; unknown items are `[待考]` → that file's `## 待开发者确认`.
- Do not open exploration/plan agents for a routine update, do not read long docs whole (rulings 走目录、评标只读目标 TAG), do not hand-write one-off apply scripts (用 `apply_ops.py`).
- Do not create TAGs unilaterally; do not edit `docs/player-tags-specify.md` (developer-owned).
- Do not write dates, round labels or edit traces; do not commit unless asked.
