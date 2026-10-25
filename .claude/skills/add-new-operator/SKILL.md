---
name: add-new-operator
description: 对新实装干员逐 TAG 评定（官方设定 TAG ＋ 玩家体感 TAG）并更新成员表。当开发者给出新干员的 PRTS 链接（或手写描述）、说某干员已上线需要归类，或要求把新抓的 PRTS 数据折进 TAG 体系时使用（触发词：新干员、新干员实装、评定新干员、add new operator）。流程：爬进 material_datas/PRTS → 逐 TAG 判定 → 就问没有 TAG 覆盖的特殊机制 → 只更新成员文档（绝不生成 results/operator-tags.json）。
---

# 新干员评定流程

固定管线：**爬取 → 逐 TAG 判定 → 就问没有 TAG 覆盖的机制 → 只更新成员名单。**

## 0. 输入

- 开发者给一个或多个 PRTS 链接（`https://prts.wiki/w/白铁`）。PRTS 尚无页面时（已公布未实装）接受手写描述——只判描述里写明的，其余标 `[待考]`。
- **版本更新**（新干员 **加上** 既有干员的新模组，增量处理）走 `.claude/skills/update-version/SKILL.md`；本技能管的是新干员的首次完整判定。
- 全新页面可能不完整（模组／数值行还在补）。判已存在的；缺口 → `[待考]` → `## 待开发者确认`。
- 多名干员：逐人跑步骤 1–4，所有待问开发者的项**合并成一轮** AskUserQuestion。

## 1. 爬取（逐人）

1. 缺行就按现有格式往 `docs/operators.txt` 追加：`干员名 https://prts.wiki/w/干员名`（用 PRTS 页面名，如 `阿米娅(近卫)`）。
2. `.venv/Scripts/python.exe -X utf8 crawlers/crawl_prts.py --only "干员名"` —— 召唤物会自动抓在主文件旁；可断点续爬。
3. `.venv/Scripts/python.exe -X utf8 crawlers/crawl_ranges.py --only "干员名"` —— 各精英化阶段／技能／召唤物的攻击范围网格。
4. 把干员的上线时间加进 `agent_workspace/tag_pipeline/player_tags/_launch_dates.json`（格式 `"干员名": "YYYY-MM-DD"`，取自爬到的 `## 获得方式`）——合并脚本据此填「实装时间」列。
5. 按 `.claude/skills/crawl-prts-operator/SKILL.md` 的「爬后验收」核对：目录 ＋ `<干员名>.md` ＋ 每只召唤物一个文件 ＋ `## 特性/天赋/技能/模组` ＋ `攻击范围.md`；**属性表（稀有度／职业／所属势力／攻击间隔）必须在**——判定要用它。需要范围格数的判定，读 `攻击范围.md`。

## 2. 逐 TAG 判定（单遍）

先通读新干员的 md（含召唤物），再筛全部 TAG。高效顺序：

1. **机制词表粗筛** —— 用大白话列出该干员的机制（控制／位移／召唤／伤害类型／资源回复／生存／部署／攻击行为…），再只打开可能的 TAG 条目。
2. **官方设定 TAG** —— `docs/official-tags-members.md`：套用 §1 判定铁律（免疫≠持有、名称≠机制、数值减益不设 TAG…）与 §4 各条目的定义＋备注。召唤物／装置算持有者的能力；**模式限定模组对官方 TAG 不计**（只对玩家 TAG 计——见 `docs/classification-conventions.md`）。收集「成员」行要加上该干员的 TAG。
3. **玩家体感 TAG** —— `agent_workspace/tag_pipeline/player_tags/NN-*.json`（11 个 tag-part/1 分文件）：判定前**先读该文件的 `## 评定标准` 与「边界与排除记录」**。成员行按该表 columns 的列序准备：
   - 表列形如 干员｜编号｜[子 TAG]｜条件｜备注｜依据 —— 编号＝charId（取自 `char_ids.json`）；条件＝硬性要求（精英化／技能／专精／模组与等级／模式限定／目标限制；精英0·1 即具备写 `无`）；备注＝加工后的信息（数值、时长、隐藏机制、战术用法）；依据＝`文件:行号`（模组 `※` 隐藏机制见 `docs/module-hidden-mechanics.md`）。行是 JSON 里的单元格数组（或经维护面板写入）。
   - 子 TAG 也要判：拐杖的「子 TAG」列／次数对策的两张子表／吃拐一轮秒的聚爆·连射／保人的七个分部 等。
   - 遵循 `docs/player-tags-members.md` §0 的通用评定标准：**多项特性只要各自符合评定标准都要写**（不因重叠／幅度小而省略）；**模组档位**——判定能力受模组增强时，「条件」写模组名与等级、「备注」取该档位数值，多个模组按**本 TAG** 选型（不同 TAG 各行可分别取不同模组）；**「（待验证）」只标攻速／间隔换算与倍率相乘类推算值**。玩家表格按实装时间倒序（阵容组合按组合分组）。
   - 阵容组合以**组合**为单位：新干员作为某组合的「提供者」入该组合子表，或新建组合子表——每个组合表前固定三条 bullet（`触发条件`／`组合整体机制`／`可用受益干员`），结果 JSON 据此生成组合条目（`docs/output-standard.md` §4.2）。
   - 近失项写进该文件的「边界与排除记录」（理由＋证据），不进成员表。
4. **多 TAG** —— 多数新干员会同时落多个 TAG；TAG 之间不互斥（写明关系的除外，如吃拐一轮秒与决战歼灭不互斥）。顺手在两端「多 TAG 并存」记录里互链。
5. **批量 ≥3 人**：按 TAG 族切给只读并行代理（官方 81 偏机械／关键词驱动；玩家 12 偏判断驱动），其结论**回到 PRTS 原文核对后**才落笔。

## 3. 没有 TAG 覆盖的特殊机制 → 问开发者

判定完之后，列出每一个**值得在意的机制**——没有现成 TAG 覆盖的新异常／状态关键词、新结算方式、新资源机制、超出既有阈值的设计。为每项准备证据（`文件:行号` ＋ 原文），用 AskUserQuestion 一次问完（合并所有项）：

1. **创建新 TAG** → 走 `.claude/skills/add-player-tag/SKILL.md`（先把评定标准说清；可提议「先创建此 TAG，评定标准后续更新」的 stub）。
2. **归入现有 TAG** 的备注／边界（指明哪个 TAG、哪一类）。
3. **仅记录不建 TAG**（写进该干员的边界记录或 `_brief.md`）。

绝不凭自己的判断建 TAG；绝不静默丢掉显著机制。纯数值差异（数值筛选维度）与泛在机制（普通治疗、普攻伤害）既不需要 TAG 也不需要提问。

## 3.5 写计算过程详情

凡新干员命中的玩家 TAG 条目**有计算内容**（成绩项里的总伤／DPS／段数／倍率／门槛判定），就建
`agent_workspace/tag_pipeline/calc_process/<干员>.json`（一干员一文件，跨 TAG 合并），规范见 `docs/calc-process-spec.md`：

1. 每条命中条目一个 `members[]`：`tag`（`P01`…）＋ `match`（条件前缀，用于定位成员行）＋ `metric`；
2. 写 `scenarios.<情形>.steps`（分节 ① 面板 ② 倍率 ③ 次数 ④ 分流 ⑤ 合计）；
3. **只有该干员在 ArkDPS 有帧模型时**才写 `timelines`（在 `agent_workspace/_out/` 的 `_arkdps_*_raw_main-*.js` 里能匹配到代号）；否则只写 steps 并给 `scenarioNames`；
4. 图例用短名（≤12 字）＋ `groupDesc`；
5. 跑 `.venv/Scripts/python.exe -X utf8 tools/calc_process.py --check`（数字守恒、成绩对账、图例命名全过）。

**不得**往备注里写 `计算` 块——该块已退役。

## 4. 更新成员名单（唯一产出）

1. **官方** —— 改 `agent_workspace/tag_pipeline/official_tags/` 下的分模块（`[A-I]-*.json`），然后跑合并脚本重生成文档：
   - 在每个命中的 TAG 成员表（`| 干员 | 编号 | 条件 | 备注 |`）里按**实装时间倒序**插一行：条件＝硬性要求（精英化／技能／模组与等级／模式限定；天生即具备写「无」），备注＝游戏内原文引用；
   - 跑 `.venv/Scripts/python.exe -X utf8 agent_workspace/tag_pipeline/official_tags/_merge_official_to_docs.py` —— 脚本自动重算各 TAG 的「N 人 · 首现」、§3 总览与 §5 时间线，并合进 `docs/official-tags-members.md`；
   - 管线中间件（`agent_workspace/tag_pipeline/` 下的 `merged.json`、`final_lists.tsv` 等）**不逐条维护**——见 `docs/output-standard.md` §7。
2. **玩家** —— 改分文件（成员表 ＋ 按需的边界／多 TAG 并存），然后跑：
   `.venv/Scripts/python.exe -X utf8 agent_workspace/tag_pipeline/player_tags/_merge_to_docs.py`
   并核对 `docs/player-tags-members.md` 的总览行（受影响 TAG 行数 +N）。
3. **体检** —— `git diff --stat` 只应出现预期的文件；评定标准各节必须原封不动（本管线只更新**成员名单**；需要改评定标准是另一件事，交开发者）。再挑两三条新行确认合并文档里渲染正常。
4. **不要生成 `results/operator-tags.json`** —— 最终 JSON 按 `docs/output-standard.md` 另行产出。除开发者要求外不提交。

## 禁止

- 不得把 `计算` 块写进备注（已退役，计算内容写 `calc_process/`），也不得手改产物里的 `calc`。
- 不得凭模型记忆判定——每个判定都引 `material_datas/PRTS/` 下的 `文件:行号`；不确定的标 `[待考]` → `## 待开发者确认`。
- 不得往任何评定标准小节写日期、轮次标记或编辑痕迹（规则见 `docs/classification-conventions.md`），也不得在加成员时顺手重编号／改写评定标准。
- 不得编辑 `docs/player-tags-specify.md`（开发者所有）。
- 不得擅自新建 TAG；待开发者确认项写在各分文件的 `## 待开发者确认`。
- 不得跳过爬后验收，也不得凭记忆判范围——范围类 TAG（决战歼灭、远程消耗等）以 `攻击范围.md` 为准。
