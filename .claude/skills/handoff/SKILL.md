---
name: handoff
description: >-
  会话转交：把当前工作完整交给一个新窗口。用于上下文将满需要承接、或新会话接手本仓库正在进行中的任务。
  状态快照写在 agent_workspace/handoff/state.md（本地，不进库）；本技能讲开工顺序、现场约定与校验套件。
  触发词：转交、接手、handoff、上下文将满、新窗口继续。
  注意：状态快照有时效——它记的是转交那一刻的进度；与仓库文件冲突之处，一律以文件为准。
---

# 转交（handoff）

## 0. 状态快照写在哪儿、写什么

- 位置：`agent_workspace/handoff/state.md`（本地，`.gitignore` 已排除；接手者开工先读它）。
- 写法：转交者在交付前更新，建议含四节——
  1. **一句话现状**：当前产物版本、md5、是否已同步消费端；
  2. **未完成的目标**：接手后的第一件事、待裁定／待验收项；
  3. **遗留清单**：`agent_workspace/_out/` 里不可删的临时工具与记录；
  4. **时效说明**：写清转交时点。
- 本技能其余各节是长期有效的作业约定，不随轮次变化。

## 1. 开工必读（按此顺序，别跳）

1. `AGENTS.md`（会话自动加载，讲仓库结构与铁律）。
2. `docs/agent-primer.md` —— 作业记忆包（解锁关系、**2★及以下无专精**、作业常识、反面清单）。
3. `docs/rulings.md` —— **裁定台账**（顶部有节级目录：先按主题命节、只读该节，不全文通读；版本更新类案例在「十三」，节号随目录增长）。**判断类问题先查它**。
4. `agent_workspace/workdocs/待裁定.md` —— **仅当存在待裁定项时才有此文件**；存在则先读它。
5. `docs/scan-protocol.md` —— **不漏扫流程正本**（名单文件＋逐人决断＋复核代理），一切扫描类作业先读它。
6. 任务涉及的文件：`player_tags/NN-*.json`、`official_tags/[A-I]-*.json`、`docs/calc-rules.md`、`docs/concept.md`、`docs/ui-render-rules.md`、`docs/output-standard.md`、`docs/module-hidden-mechanics.md`（模组「※」隐藏机制汇编）、`docs/abnormal-effects.md`（PRTS《异常效果》落库：异常效果/组合/统一检查分类/硬软控对照）。
7. **版本更新类任务**（新干员／新模组，非结构性）：先读 `docs/version-update-quickstart.md`（快线：七步流程、预核验清单、验证最低集与审核规则）。

## 2. 三条硬纪律（违反过，代价明确）

1. **未经裁定不得自行改动**：开发者明确要求改的必须动；**你自己发现「可能需要修改」的，只能写进《待裁定.md》问过再动**。
2. **裁定四步缺一不可**：裁定 → 折入正本 → **登记 `docs/rulings.md`** → 才移除/替换《待裁定.md》。
3. **《待裁定.md》必须自包含**：背景＋现状＋候选＋算式与出处；**自创词与模组线当场解释**（开发者明令「不得假设知识对齐」）。

## 3. 现场约定（踩过的坑，直接照办）

- **回填分文件一律用 `.claude/skills/tag-batch-rewrite/scripts/_apply_batch.py`**（按表头定位列、以 HEAD 重建整行）：键＝干员名，同名多行写 `干员名（子表名）`（须与该表上方最近的小节标题匹配；`（2技能）` 这类非标题标签不会命中）；`--keep-prefix` 保留 `救急路径：`／`子 TAG：` 前缀——**若代理产出文本已自带该前缀，回填后会重复，须事后去重**（`^(救急路径：…；)(救急路径：…)` 与 `^\*\*…\*\*；` 两种形态都要处理）。回填前先 `--dry-run` 核全键命中。
- **子 TAG 列与成员增删不由回填脚本管**；被移除行带走的 `文件:行号` 要登记 `strip_prts_noncombat.ACCEPTED`。**新增行**：`_apply_batch` 不能插行——按实装倒序用脚本插整行（沿 `agent_workspace/_out/_p13_insert.py` 的「找下一行锚点」法）。
- **`audit_text_migration.ACCEPTED` 同名键必须合并**（令牌取并集、理由相接），批量登记后跑一次去重；**依据列只可加、不可改同一 token**（`文件.md:1,2` 与 `文件.md:1` 是两个 token，改写会报「依据丢失」——**要整段保留旧 token、另起一段写新行号**，如 `…:130,155,182；仇白/仇白.md:132`）。
- **两线呈现写法**：成绩块情形名＝模式名（`集成战略特限`／`生息演算特限`／`岁的界园志异特限`）或 `通用线`，特限排前；「最低可满足档」排最前；某线无贡献则只写贡献线＋说明。
- **倍率与面板解耦**：写数值前先问「这是倍率还是绝对值」——固定点数／召唤物伤害只进绝对值（总伤／DPS／每秒），倍率只写百分比结构。
- **派 TAG 改写类子代理**：用 `.claude/agents/tag-rewrite` 代理类型；产出写 `agent_workspace/_out/*.json`（**顶层包 `{"Pnn": …}`**）；prompt 里点名「纯固定攻击的更高档不取」「两线呈现格式」「倍率解耦」三条，否则会被读反。**写手自查替代不了独立复核**（本轮两批复核各抓出实质算错：噤声限域基准、落雷基准回退、三件套不自洽、同池连乘——复核代理要给「可复算的更正值」）。
- **外部计算工具（ArkDPS）的引用与标注**（第十批裁定改写原「站点/外部对照信息不入产物」）：**显示成绩**在「站点∩我方」交集内采用「我方基础数据 × 站点算法框架/帧模型/用法分支」（帧模型＝可攻击时长含前后摇、`四舍五入(可攻击时长÷间隔)`；间隔用我方；面板/潜能/条件全用我方；站点默认数值不用）；行内成绩块括注「（帧模型与用法分支参考 ArkDPS（作者：极夜星辰，ark-dps.com））」、结果 JSON 记 `source` 字段（author＝极夜星辰、parts＝引用部分）、详情卡片展示「数据来源：ArkDPS（作者：极夜星辰）｜引用部分：…」；**评定标准与达标判定仍按我方**（交集内达标同源、站点没有的按我方口径）。相对判据（慢热超额/比值/距离/时长/控制）不重算。规则见 `docs/calc-rules.md` §4.10；对照方法（三支 JS：FormulaDialog/formula-snippet/main）见记忆 [[arkdps-site-formula-materials]]。**其余内部代号（范围代号、S1/S2/S3、表 2A、路径⑤）仍不入产物。**
- **ArkDPS 公式的 `取中位数(x,5,100)` 是上下限截断**：木桩 0 法抗下 `100-(法抗-20)=120` 被封顶为 100（乘区 1.0），故「字面读法」与站点默认显示是同一个值；复算以 `agent_workspace/_out/_combo_calc_v3.py` 为准（v1/v2 把截断当普通减法、且漏烛煌 X3 天赋/特性，已作废）。澄闪 +余 行站点默认是 **FUN-Y** 线（攻速+7）。
- **元素损伤（爆条）按元素值（EP）机制演算**：初始满值（普通/精英 1000、**领袖 2000**）、爆条冷却内不可累积、结束重置为满值后重积；涉爆条节奏的成绩按「普通/精英」「领袖」双档并列——机制与算例索引：`docs/mechanism-understanding.md`「元素值（EP）与爆条节奏」＋`agent_workspace/_out/元素损伤-复算留痕-2026-10-11.md`（**演算前必读，别重推**）。
- **前端 ArkDPS 高亮必须单次替换；引用标识只在卡片末尾**：`linkifyArkdps` 把「ArkDPS」与「ark-dps.com」放在**同一轮** replace——分两轮会把第一轮写入 href 的域名再包一次链接、产出嵌套锚点残片（`…ark-dps.com/zh/" target="_blank"…`）。**成绩／说明正文不写引用**；引用描述集中在**详情卡片末尾**的引用块「数据来源：ArkDPS（作者：极夜星辰 · 官网 ark-dps.com/zh/）｜引用部分：{parts}——{detail}」（操作员卡聚合本卡全部带 `source` 条目、组合卡用组合来源）。`source`＝`{model, url, author, parts, detail}`；生成器按「用法」子 TAG 与 `ARKDPS_MEMBER_ROWS` 显式行清单写 source（新增此类行须登记）。
- **禁止「成功记忆」，一切数据回源重读（第十批教训）**：引用/抽取站点或语料数据时**必须回到源文件**用**括号配对/逐对象**方式解析（**禁用邻近窗口与跨块搜索**），并逐条与 `material_datas/PRTS` 语料比对名称；不得凭上一轮产出的印象复述。**已发生实例**：首轮窗口抽取把 **麒麟R夜刀3「空中回旋乱舞」的「巨型敌人」分支泄漏到仇白**（仇白三个技能均无分支）——凡「某干员×某分支」类数据，落盘前必须做**至少一次独立回源抽检**（抽 2–3 名核到源文）。**覆盖修正（本轮）**：`agent_workspace/_out/_arkdps_main.js` 名字条目实为 **103**（旧「只含 100 名」有误——`[A-Z]{2}\d{2}` 正则会漏掉 `USS0`／`REX1` 等 3 字母代号）；**`agent_workspace/_out/_arkdps_dialog.js`（公式弹窗 chunk）含 102 个干员块的逐技能 `rawFormula`**（玛恩纳 5 档、卡涅利安蓄力档、荒芜拉普兰德／烛煌的 +余组合等），抽取方法见 `agent_workspace/_out/_extract_dialog.py`（括号配对、跳字符串），输出 `agent_workspace/_out/dialog_formulas.json`。
- **防御类数值行文不用「面板NNN」**：`tools/verify_numbers.py` 把 `面板(\d+)` 一律按攻击面板校准（DEF 不在其域）；纯御等防御行写「基础防御NNN＝…」，否则报「面板与任何已声明口径都对不上」。
- **P12 子 TAG 新口径（开发者裁定）**：ArkDPS 上有、且涉及的干员已被玩家体感 TAG 收录的「玩家用法组合」→ 收进 **P12 阵容组合**；原有各势力子 TAG **合并为「势力」子 TAG**（原成员全部移入）；新增子 TAG **「用法」** 收录这类组合；条目详情卡文案面向新手写清（尚未实施，见 §6）。
- **`solidify-criteria` skill**：新增/修订 TAG 评定标准只给例子或模糊词时走它（回源枚举同类与边界样例 → 逐条请开发者裁定 → 提炼可量化标准 → 样例回归验证）；本轮「纯御天花板」为首个用例（记录/问答归档见 `agent_workspace/_out/评定标准固化-纯御天花板-记录.md`）。
- **同一行内「条件/成绩/判定窗」必须同排布**：斩业星熊三件套曾分属三个操作场景（4 秒关技／32 秒不关技／关技窗）——复核当场打回；成绩与判定窗取同一次运行。
- **证据只进「依据」列**；产物里不得出现范围代号、`S1/S2/S3`、模组档码、`表 2A`、`路径⑤`、分文件名、门槛重述（「≥3000%」尾巴、`判定：`前缀都不要）。
- **回填只动目标行的「条件」「备注」字段**：`.claude/skills/tag-batch-rewrite/scripts/_apply_batch.py` 结构化写回（tag-part/1）——其余字段（编号/子 TAG/范围/依据）原样保留，HEAD 重建机制已随迁移移除；回填前后以 `.claude/skills/tag-batch-rewrite/scripts/audit_text_migration.py` 的「依据丢失 0」为准。
- **P05（插拔容错）回填配 `--keep-prefix`**：原备注行首的 `救急路径：…；` 前缀由脚本直接取自当前行并保留（不再有 HEAD/工作区取谁之分）；不带则整批丢子 TAG。
- **改分文件一律经 `partdoc.save`**（原子写、CRLF、规范 JSON）——别手写文本；若确需手写字节，`p.write_bytes("\r\n".join(lines).encode("utf-8"))`，用 `write_text` 会因文本模式把 `\r\n` 再转义成 `\r\r\n`（每行后多一个空行），整张表解析崩掉。另：**自己读文件用 `open(..., newline='')`**——universal newline 会把 CRLF 折成 LF。
- **`ACCEPTED` 同名键必须合并**：字典字面量里重复键只有**最后一个**生效——批量登记走 `agent_workspace/_out/_accepted.py`（它按键读旧值、**并集合并**后整体重写，天然去重；勿手工逐条塞重复键）。
- **审计默认只打印前 30 条**：登记放行表时用 `AUDIT_ALL=1` 全量输出到文件再解析（`agent_workspace/_out/_accepted.py` 已内置；strip 审计的 85 条「键分词误报」即用 `正则`（`（…md:(\d+) → 应为`）提取后批量登记）。
- **块标签里的嵌套括号**：块标签形如 `第一天赋「X」（Y模组3级（HOK-Y），潜能5）` 时，标签校验必须按**配对**括号剥除（`generate_results._strip_brackets`）——用正则会漏掉嵌套、把含逗号的标签静默退回正文（表现为「块首疑似标签但未被识别」）。标签字数上限与 lint 阈值均为 `BLOCK_LABEL_MAX`（40）。
- **`agent_workspace/_out/` 里的工具随手删不得**：`agent_workspace/_out/_accepted.py`／`_build_p13_far.py`／`_p13_insert.py` 这类临时件是流程的一部分；清理前先确认后续批次不再需要。
- **模组代号补入脚本**（`agent_workspace/_out/_sweep_codes_labels.py`）对**组合级 bullet**（12-阵容组合，会进 `read_combo_meta`）要按「每个提及点最近的在前干员名」解析（同名是子串时优先取更长的名字，如「归溟幽灵鲨」vs「幽灵鲨」）。
- **引用分词的全角冒号**：`crawlers/strip_prts_noncombat.py` 的 `CITE_RE` 排除集须同时含 `：` 与 `:`；否则「X模组3级：塑心/塑心.md:162」的路径键会连同前缀一起被吞，任何在其前插入文字都会误报「失效」。
- **在引用紧前方改文字 → strip 审计「失效」误报（键名随散文变化）**：消除方式＝在该文件 `strip_prts_noncombat.ACCEPTED` 显式放行（按 `(分文件, HEAD 侧行号)`），注释写明「引用本身未变、仍指向同一处原文」（第八批 49 个键即此类）。
- **「指向已删行」的历史余量**：10 条（07 罗小黑×2、13 霍尔海雅×3／安洁莉娜×2／莫斯提马×1／予愿安洁莉娜×2）为批七前后既有、非本批产生；报告每轮都会列出，属「需人工过一遍」的存量。
- **`_apply_batch.py` 的 CRLF 直读坑已随结构化迁移消失**（现为 JSON 读写）；`.claude/skills/tag-batch-rewrite/scripts/audit_text_migration.py` 经 `agent_workspace/_out/_accepted.py` 文本模式读写可能被转为 LF——功能无碍（autocrlf 归一化）。
- **`.claude/skills/tag-batch-rewrite/scripts/audit_text_migration.py` 的两处判定（勿回退）**：①成员表以「**其后紧跟分隔行**」判定；②同名多行按**出现顺序配对**。
- **子代理的解释性读法要复核后落盘**：裁定原文可能只给判准——写手可能读反，须在回填前由主进程定读法并列入证伪清单。
- **scan-protocol 复核的实际形态**：写手 → 复核（证伪）→ 写手逐条修正 → 复验 → 核销；远距控制第二批（15＋6 项）与决战歼灭两批（各 6-7 项）均走完两轮，**修正清单本身就是交付物的一部分**。
- **每批开发者回复原文必须归档**：折入的同时把逐字回复留存到 `agent_workspace/_out/待裁定-第N批-回复原文.md`（已建第七、八、九、十批）。第八批另含**当场问答**（`/handoff` 会话中以 AskUserQuestion 确认）与**计划审批时的指示**；第十批含 D1–D8 与两项附加问、以及**反幻觉指示**（「仇白跟巨型根本没什么关系，这属于幻觉成果，要万分警觉」）。
- **规划类问题用 AskUserQuestion、外审类问题用《待裁定.md》**：开发者在会话内响应很快；但**口径点定类**（会改产物数值的）一律落《待裁定》条文，保证留痕。
- **DoT 跳数按「[间隔]-[伤害]」循环（裁定 2026-10-03／2026-10-05 复核修正）**：**施加型持续伤害效果（DoT）**按 [间隔]-[伤害] 计时，首次结算在施加后第 1 个间隔，但**持续时长末端的「尾击」计入**——跳数＝**⌊覆盖窗口÷结算间隔⌋**（整倍时即 T/i，如 12 秒@1 秒＝12 跳）；**若施加该状态的那一击本身无伤害（除状态外无伤害输出），另计 1 次「首击」**（施加时立即结算；望 1 技能 6.5 秒＝7 跳、酒神召唤物 6 秒@0.5 秒＝13 跳）；**技能/天赋/装置/召唤物自身按间隔直接造成的伤害与条件状态型伤害不套循环**，按「覆盖时长÷结算间隔（四舍五入）」计；**攻击动作仍含首击**；**帧伤按 2 帧机制原文另计**。落库：`02-次数对策.json` 共同约定①、`docs/calc-rules.md`（跳数式／C5·C6／§4.4）、`agent_workspace/tag_pipeline/player_tags/_reverify/rules.md` R6；台账「八、DoT 跳数循环裁定」。

- **回填结构操作走 `.claude/skills/tag-batch-rewrite/scripts/apply_ops.py`**（插行／改依据／正文行替换／正文行后插入／新建子表；输入 JSON 五类操作、默认 dry-run、逐条断言；`--root` 可指向副本做冒烟）。勿再手写一次性回填脚本。
- **依据键内的反斜杠已归一**：`strip_prts_noncombat.py` 的 `numbers_by_key` 把依据键里的字面反斜杠（审计读**原始 JSON 文本**、以 `\\` 两字符出现）折叠为 `/`——写法统一（`黍\黍.md`→`黍/黍.md`）不再触发整键误报；配合此归一，`audit_text_migration.py` 的「依据守恒」也新增了放行通道（键内令牌含完整引用串，与数字令牌同一 `ACCEPTED`）。
- **重爬既有干员致行号平移＝审计不覆盖场景**：重爬后必须 `git diff` 白名单核验（PRTS 会在天赋表插入「Y模组N级」档位行，**令其后全部行号 +N 平移**）；受影响引用人工重锚 + `strip_prts_noncombat.ACCEPTED` 登记理由——**不跑 `--fix-stale`**（重爬场景它会回退正确重锚；`--audit` 对内容新增也是恒等映射、不会报警）。《特殊机制》等快照重抓同理（本轮 373→399 已登记）。
- **备案（不阻塞，后续轮次留意）**：12-阵容组合 A2「数据结构建议」示例块仍为旧数值示例；CRU-Y「对被阻挡的敌人伤害提升至110%」未折入乌尔比安任何行（重剑手「被阻挡」＝自身阻挡，同线赫德雷先例）。

## 4. 校验套件（改完必跑）

```bash
.venv/Scripts/python.exe -X utf8 tools/prts_stats.py --check          # 属性层覆盖率（异常 0）
.venv/Scripts/python.exe -X utf8 tools/verify_numbers.py              # 数值校准（数值可疑 0；DPS 恒等式已改「÷全时长」并报旧式成绩句；「档位取舍已复核」是已裁定的不取档）
.venv/Scripts/python.exe -X utf8 tools/generate_results.py --check    # 生成 + 文本 lint（0；条件已无字数上限）
.venv/Scripts/python.exe -X utf8 .claude/skills/tag-batch-rewrite/scripts/audit_text_migration.py        # 守恒（数字/依据/结构 0；ACCEPTED 每条一次显式裁定）
.venv/Scripts/python.exe -X utf8 crawlers/strip_prts_noncombat.py --audit # 证据层（失效 0；约 2 分钟，可后台跑——注意别用 tail 截断输出，全量落盘再读）
.venv/Scripts/python.exe -X utf8 recommend_gui.py --check        # GUI 规范（0 错误 0 提醒）
```

改完 `results/operator-tags.json` 后如需同步到消费端：在仓库根的 `local.json`（模板 `local.example.json`）里配置 `frontend_results_dir`，运行 `.venv/Scripts/python.exe -X utf8 tools/sync_results.py`——脚本复制 `results/*.json` 并逐文件核对 md5。

> 校验套件另含 `.venv/Scripts/python.exe -X utf8 tools/calc_process.py --check`（计算过程详情：数字守恒、成绩对账、图例命名）；帧/次数自洽用 `tools/frame_check.py`；与 ArkDPS 公式对账用 `tools/arkdps_replicate.py --calibrate` 与 `tools/arkdps_report.py`（帧模型属性登记在 `agent_workspace/tag_pipeline/arkdps_frame_model.json`）。
