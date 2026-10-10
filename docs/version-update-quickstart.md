# 版本更新快线（常规更新开工件）

> 用途：**非结构性版本更新**（新干员／新模组／新召唤物／页面小改）的唯一开工必读。新会话只读本文，并按文中指针**定向读节**——不开前置调研/方案代理、不通读长文档。
> 分流：改评定标准、全库重扫、增删 TAG、改计算规则正本 ＝ **结构性更改**，不走本线（扫描类先读 `docs/scan-protocol.md`，其余按各自流程）。
> 硬纪律不豁免：证据制（一切判定引 `文件:行号`）、未裁定不擅改、裁定四步留痕（见 `AGENTS.md`、`.claude/skills/handoff/SKILL.md`）。
> 目标耗时：开工到交付 ≈30 分钟（不含爬取等待与开发者作答）。此前冗余在四处——前置代理读资料、每层全文通读、子代理多轮往返、手写一次性回填脚本——本线逐项消除。

## 七步流程

### 1. 抓取与登记
- `docs/operators.txt` **顶部**插新干员行（最新在前）：`<干员名> https://prts.wiki/w/<干员名>`。
- `.venv/Scripts/python.exe -X utf8 crawlers/crawl_prts.py --only "A,B,C"`（新干员；已有干员加新模组 → 同命令加 `--force` 重爬该员）。
- `.venv/Scripts/python.exe -X utf8 crawlers/crawl_ranges.py --only "A,B,C"`（攻击范围，独立命令）。
- 验收（细则见 `crawl-prts-operator` 技能的 "Verify after crawling"）：属性表在；无 tooltip 泄漏；无 `## 精英化材料/技能升级材料/后勤技能`；`## 模组` 段无剧情/解锁任务/图片行；召唤物文件齐全。
- **重爬既有干员必做**：`git diff material_datas/PRTS/<干员>/` 白名单核验——只允许「抓取时间行」与「`## 模组` 段追加」。**模组段之前任何差异逐行核查**（PRTS 会在天赋表插入「Y模组2/3级」档位行、令其后**全部行号平移**）；行号平移 → 用一次性脚本对全仓指向该页的 `文件:行号` 人工重锚，并在 `crawlers/strip_prts_noncombat.py` 的 `ACCEPTED` 登记理由（**不跑 `--fix-stale`**——重爬场景它会回退正确重锚）。
- 登记三件套（漏一个都静默降级）：
  - `player_tags/_launch_dates.json` 加上线时间（抄爬取页 `## 获得方式`；按键码位排序、保持原格式）；
  - `char_ids.json` 加 charId——用 `crawlers/crawl_ranges.py` 的 `fetch_wikitext()` 从 PRTS wikitext 正则 `\|干员id=(char_[A-Za-z0-9_]+)` 取（勿裸 requests，无浏览器头 403）；
  - `docs/operators.txt`（见上）。
- `.venv/Scripts/python.exe -X utf8 tools/prts_stats.py` 重建机读属性层 → `--check` 异常应为 0。

### 2. 取计算规则与评标（定向读，不通读）
- 计算规则＝`docs/calc-rules.md`：按目标条目涉及的机制只读对应节（§1 结算层位与总式／§2 游戏文本→因素映射／§3 演算流程／§4 其余规定）。
- 各 TAG 评标＝目标分文件的「## 评定标准」＋「约定」（**注意子表全枚举**）＋「## 边界与排除记录」——**只开目标 TAG**（`player_tags/NN-*.json` 或 `official_tags/[A-I]-*.json`）。
- 写法与结构＝`docs/concept.md`「条件分条／备注分块」＋`docs/output-standard.md` §4.2。

### 3. 异常状态术语（按需）
- 技能涉及异常效果（战栗／虚弱／冻结／停顿／传送／放逐……）时：`docs/abnormal-effects.md` §3「统一检查分类」（**判控制性质的唯一口径**）；词义查 `docs/glossary.md`（纯文本无标题，按词 Grep）。
- 不涉及异常效果则跳过本步。

### 4. 计算伤害
- 取数唯一处：`agent_workspace/tag_pipeline/stats.json`（`tools/prts_stats.py --panel <干员> --stage e2 --pot N --module X --tier 3`）；**不手抄**。
- 默认口径：纯木桩 0 防 0 抗；概率项按期望并写出算式；模组／潜能取「对本 TAG **绝对贡献**最高档」；攻速／间隔按整帧（30fps）换算；固定点数按绝对值计入成绩、不入倍率。
- 判定文本由 `tag-rewrite` 子代理产出 `agent_workspace/_out/<批名>.json`（键＝干员名，值＝`{condition, remark, why}`），**不直接改分文件**。

### 5. 存疑查台账
- `docs/rulings.md` 顶部有**节级目录**——按主题命中节、只读该节；查得到就照办（同一问题不查第二遍、不问第二遍）。
- 查不到且拿不准 → 记为**待裁定项**（见第 7 步）。

### 6. 分配 TAG
- 子代理批次（一律 `.claude/agents/tag-rewrite` 代理类型，可并行）：① 官方 TAG × 全部新干员；② 玩家 TAG × 新干员（人多时可再拆）；③ 模组折入（每个新模组逐既有行）＋跨干员影响清单（`.claude/skills/update-version/SKILL.md` §4 十六维）。
- **每单随发预核验清单**（见下），一次答完，消灭多轮往返；回报＝逐 TAG 决断（加入／不加／待裁＋理由＋依据行）＋产出 JSON，不强制另落名单文件。
- 近失项随后写入该文件「边界与排除记录」一条（干员—不达标项—关键数—依据）。
- 回填：
  - 只改既有行条件/备注 → `.claude/skills/tag-batch-rewrite/scripts/_apply_batch.py`（先 `--dry-run`）；
  - **插行／改依据／正文行替换／正文行后插入／新建子表** → `.claude/skills/tag-batch-rewrite/scripts/apply_ops.py`（输入 JSON 五类操作，先 `--dry-run`，逐条断言）。

### 7. 收尾（审核规则）
- **存在待裁定项**：先走裁定流程（一轮 AskUserQuestion，只问争议项；每条自包含——背景／现状／候选／算式与出处）→ 裁定回答后折入源文件 → **才执行产物链**。**裁定前不生成结果文件**（`results/operator-tags.json`、`docs/untagged-operators.md`）。
- **无待裁定项**：直接执行产物链 → 收尾审核报告（**产物后审核**）。
- 产物链：两个合并脚本（`player_tags/_merge_to_docs.py`、`official_tags/_merge_official_to_docs.py`）→ `tools/generate_results.py --check` → `--write`（成员变化须递增脚本内 `VERSION`）→ 校验最低集 → `tools/recommend.py check`。
- 校验最低集（合起来 ~5 分钟）：`tools/run_all_checks.py`（六项一体）；按改动触发：改依据/行号 → `crawlers/strip_prts_noncombat.py --audit`；改条件/备注 → `.claude/skills/tag-batch-rewrite/scripts/audit_text_migration.py`（预期数字变化先登记 `ACCEPTED`；依据守恒**只可整段追加、不可改同一引用串**）；档位取舍 → `tools/verify_numbers.py` 的 `REVIEWED_TIERS`。

## 预核验清单（每单随发，逐条作答）
1. 0 防木桩下「防御低于初始值」类概率天赋是否生效？不生效 → 列为待裁定（勿默认按高档计）。
2. 损伤系→元素侧读法：爆条固定点数按绝对值计入总伤；元素占比 **<20%** 归主档（统一规则、不分来源）；混伤子表须两类伤害同时存在。
3. `04-远程消耗` 有**三类子表**（超远距离打击／远程部署型召唤物与装置／全场·无距离限制的触发式伤害）——逐类核，一类的排除条勿误伤另一类。
4. 模组取档＝绝对贡献；特限证章线分别计算；不写「更佳/可选」类模糊措辞。
5. 范围/最远距离以该干员 `攻击范围.md` 网格为准（自身格=0、相邻=1、横竖斜同价）。
6. 隐藏前提：专精需精英2＋技能 7 级；模组解锁需精英2（语料查不到，见 `docs/agent-primer.md`）。
7. 产物禁内部代号（范围代号／`S1-3`／表 N／路径 N）；**模组代号必须进**——写「中文线名（代号）」。
8. 新机制无 TAG 覆盖时主动上报（不自行建 TAG、不静默丢）。
9. 官方类：模式限定模组不计；备注只记原文。
10. 一切判定引 `文件:行号`；存疑标 `[待考]` 上报，不硬判。

## 核验强度
「**工具为主＋当轮成果全检**」：产物数字全过 `verify_numbers`／生成器 lint／六项校验（自动、便宜）；**本轮新增与改动的一切条目逐条全检**（数字独立复算、条件齐全性、依据可解析、规范合规）——核验范围＝当轮成果，不扩散到无关存量。子代理自述不是证据：其结论以回源核对过的文本为准。

## 明确不做
- 不开前置调研/方案代理（本文就是路线图）。
- 不通读长文档（rulings 走目录、评标只读目标 TAG、glossary 按词查）。
- 不手写一次性回填脚本（用 `apply_ops.py`）。
- 不复扫无关干员与 TAG、不改评定标准、不动 `docs/player-tags-specify.md`。
- 不提交（除开发者另行要求）。
