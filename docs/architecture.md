# 仓库架构与文件权属

> 用途：项目是什么、数据怎样流动、每个目录负责什么、哪些文件可信可改、哪些是生成物。
> 开工时**不必读本文**——按 `AGENTS.md` §一 的分派表取开工件；本文是「需要了解结构」时的查阅件。

## 一、这个仓库是什么

一个**数据生产仓库**（不是应用）：从 PRTS wiki 爬取干员语料，按两套 TAG 体系（官方设定 TAG / 玩家体感 TAG）逐干员判定，产出供筛选 UI 消费的结构化 JSON。仓库内没有构建／lint／测试工具链，代码是一组一次性的 Python 数据脚本。工作语言为中文，一切文档与产物均为中文（见 `docs/README.md`「撰写语言」）。

**最终产物**（由**另一个** UI 项目消费，本仓库不消费）：

| 产物 | 内容 | 规范／源 |
|---|---|---|
| `results/operator-tags.json` | 主产物：干员 × TAG × 条件／备注，含职业／分支／势力／实装时间、PRTS 深链与「荐」 | `docs/output-standard.md` |
| `results/operator-timelines.json` | 帧级时间轴，详情弹窗按需加载 | `docs/calc-process-spec.md` |
| `results/combat_glossary.json` | 战斗术语表 | 由 `docs/glossary.md` 生成 |
| `results/player-tags-criteria.json` | 各 TAG 评定标准（前端抽屉文案） | 由 `docs/player-tags-criteria.md` 生成 |

TAG 定义、成员名单、计数与开放问题变化频繁——`docs/` 是内容的唯一权威源；本文只描述**稳定结构**。

## 二、数据流

```
docs/operators.txt ──► crawlers/crawl_prts.py ──► material_datas/PRTS/<干员>/<干员>.md（＋<召唤物>.md 同级文件）
crawlers/crawl_ranges.py ──► material_datas/PRTS/<干员>/攻击范围.md
                             （攻击范围网格：各精英化阶段 / 技能 / 召唤物；PRTS 用内联 SVG 绘制，主爬虫不抓）
                                              │
        官方 TAG：agent_workspace/tag_pipeline/{catalog,merged,deterministic}.json + final_lists.tsv
                  agent_workspace/tag_pipeline/official_tags/[A-I]-*.json（tag-part/1 分模块：条目头＋干员 | 编号 | 条件 | 备注）
                  └─► docs/official-tags-members.md（_merge_official_to_docs.py 重生成 §3/§4/§5）
        玩家 TAG：docs/player-tags-specify.md（定义）
                  agent_workspace/tag_pipeline/player_tags/NN-*.json（tag-part/1 分 TAG 判定文件，含逐条 文件:行号 证据）
                  _brief.md（作业规范）+ _launch_dates.json + _merge_to_docs.py + _recommend.json（荐，tools/recommend.py 维护）
                  └─► docs/player-tags-members.md（自动生成，勿手改：改分文件后重新合并）
                  └─► results/operator-tags.json（最终输出，tools/generate_results.py 生成）
                  └─► docs/untagged-operators.md（未归 TAG 干员，随生成一并写出）
        计算过程详情：agent_workspace/tag_pipeline/calc_process/<干员>.json（帧级时间轴＋分步算式，撰写源）
                  └─► results/operator-timelines.json（帧级时间轴，随生成一并写出；前端详情弹窗按需加载）
                  └─► members[].calc（分步算式；备注里已无「计算」块，该块已退役、存量已全量删除）
                  规范 docs/calc-process-spec.md；校验 tools/calc_process.py --check（Σ伤害＝成绩块总伤的对账、数字守恒、图例命名）
                  --pending（待迁移清单）/ --show-entry（看源「计算」块与成绩块）/ --strip（删除源「计算」块）
        玩家 TAG 文案：docs/player-tags-criteria.md（严谨版源：通俗说明＋精确条件＋计算式＋对照例子）
                  └─► results/player-tags-criteria.json（tools/criteria_to_json.py；前端「查看评定标准详情」抽屉）
        展示顺序：agent_workspace/tag_pipeline/tag_order.json（手写：官方类别序／类内 TAG 序、玩家 TAG 序、每 TAG 取值序）
                  └─► tools/apply_tag_order.py（只重排、不重生成）──► 两处 results/ 产物的顺序与玩家的 subOrder
```

## 三、目录职责

- **`material_datas/PRTS/`** —— 一干员一目录，干员页＋每只召唤物一个同级 `.md`。`_manifest.json` 是爬虫的续爬记录（各干员状态／文件／召唤物关联）。语料**只含作战信息**：章节级剧情（`干员档案`／`语音记录`／`干员密录`…）由 `STOP_SECTIONS` 整节丢弃；模组剧情、模组解锁任务、升级材料、`后勤技能` 由 `strip_noncombat()` 剥离（模组等级图标改写为 `**模组等级N**` 文本行，模组类型码保留为 `**ART-X**` 文本行）。剥离会压缩行号、令全仓库 `文件:行号` 整体平移——细则见 `docs/crawling-and-strip.md`。

- **`agent_workspace/tag_pipeline/`** —— TAG 判定与机读字典所在：
  - `catalog.json` = TAG 字典（**脚本唯一读取的字典**）；
  - `tag_order.json` = TAG／取值的展示顺序（手写机读源，见数据流图；唯一维护处）；
  - `merged.json` = 干员→TAG ids；`final_lists.tsv` = TAG→成员。二者由 `_merge_official_to_docs.py --sync-dicts` 重建，**无脚本读取**；
  - `deterministic.json` = 解析出的基础属性／召唤物快照，**不随 TAG 变化**；
  - `stats.json` = **机读属性层**（每干员 E0–E2 满级攻击／信赖上限／潜能各档／模组各档固定属性，由 `tools/prts_stats.py` 从 PRTS 语料抽取）——**面板与档位的唯一取数处**；
  - `player_tags/` = 玩家 TAG 分文件与作业规范；`official_tags/` = 官方 TAG 分模块；
  - `calc_process/` = 计算过程详情撰写源（一干员一文件）；
  - `arkdps_frame_model.json` = 帧模型登记表（哪些属性改变帧、逐干员的帧数／次数与 ArkDPS 对照，见 `docs/calc-process-spec.md` §2.5）。

- **`agent_workspace/`** —— agent 工作区（子目录用途见 `agent_workspace/README.md`）：`tag_pipeline/` 为判定文件与字典；`_out/` 为临时批次目录（本地，不进库）；`workdocs/` 存《待裁定.md》《待验证复算.md》等工作稿（本地，不进库，模板在 `docs/templates/`）；`handoff/` 存转交状态快照（本地，不进库）。

- **`crawlers/`** —— PRTS 爬取与语料剥离：`crawl_prts.py`、`crawl_ranges.py`、`crawl_special_mechanics.py`、`strip_prts_noncombat.py`。细则见 `docs/crawling-and-strip.md`。

- **`tools/`** —— 生成与校验工具：`prts_stats.py`、`verify_numbers.py`、`generate_results.py`、`calc_process.py`、`frame_check.py`、`arkdps_replicate.py`、`arkdps_report.py`、`apply_tag_order.py`、`glossary_to_json.py`、`criteria_to_json.py`、`module_notes.py`、`recommend.py`、`run_all_checks.py`、`sync_results.py`、`doc_consistency.py`。根目录只保留 GUI 入口 `recommend_gui.py` 与启动脚本。

- **`gui/`** —— 维护面板（Python 包）：`config/errors/md`（叶子）→ `tags/roster/recommends/merges/results_json/order`（数据）→ `writeback/model`（业务）→ `server/selfcheck/__main__`；页面资产在 `gui/static/`（`index.html` + `app.css` + `app.js`，用 ak-ui 深色令牌，出处与密度折中见 CSS 文件头）。根目录 `recommend_gui.py` 是薄入口（`python -m gui` 等价）。用法见 `gui/README.md`。

- **`docs/`** —— 规范、规则正本、台账与索引；总目录见 `docs/README.md`。

- **UI 本身不在本仓库范围**：上面的维护面板是维护者工具，不是产品 UI。

## 四、文件权属表（改谁、信谁）

### 手写权威源（要改就改这些）

`docs/concept.md`（意图＋条件／备注规则）、`docs/output-standard.md`（产物规范）、`docs/calc-process-spec.md`（计算过程详情＋帧级时间轴规范）、`docs/player-tags-specify.md`（玩家 TAG 定义）、`docs/calc-rules.md`（计算规则正本：结算层位／文本→因素映射／演算流程；复算作业副本为 `agent_workspace/tag_pipeline/player_tags/_reverify/rules.md`）、**`docs/rulings.md`（裁定台账：裁定／理由／适用范围／折入位置；判断类问题先查它）**、`docs/term-map.md`（代称映射表：一切自创代称／缩写／自编号的含义与查阅位置，新增代称时同步）、`docs/classification-conventions.md`（分类约定与评定标准写法）、`agent_workspace/tag_pipeline/official_tags/[A-I]-*.json`（官方 TAG 定义与成员，tag-part/1 JSON，GUI 可写回）、`agent_workspace/tag_pipeline/player_tags/NN-*.json`（玩家 TAG 判定＋证据，tag-part/1 JSON；`_brief.md` 为作业规范）、**`agent_workspace/tag_pipeline/calc_process/<干员>.json`（计算过程详情撰写源：时间轴 series ＋ 分步 steps；改后跑 `tools/generate_results.py`）**、**`docs/player-tags-criteria.md`（玩家 TAG 评定标准严谨版：前端抽屉文案源，撰写要求见其文件头；`tools/criteria_to_json.py` 校验指纹）**、`docs/glossary.md`（术语；前 5 节手写，后 6 节由 `crawlers/crawl_special_mechanics.py --apply` 追加）、字典 `catalog.json`／`char_ids.json`／`_launch_dates.json`／`docs/operators.txt`、**`agent_workspace/tag_pipeline/tag_order.json`（TAG／取值的展示顺序，唯一维护处）**。

### 生成物（勿手改，改上列源文件后重生成）

| 生成物 | 生成者 |
|---|---|
| `docs/official-tags-members.md` §3/§4/§5 | `_merge_official_to_docs.py` |
| `docs/player-tags-members.md` | `player_tags/_merge_to_docs.py` |
| `results/operator-tags.json`、`results/operator-timelines.json`、`docs/untagged-operators.md` | `tools/generate_results.py` |
| `results/combat_glossary.json` | `tools/glossary_to_json.py` |
| `results/player-tags-criteria.json` | `tools/criteria_to_json.py` |
| `docs/module-hidden-mechanics.md`（各模组「※」隐藏机制汇编；源＝`docs/temp.txt`） | `tools/module_notes.py --emit` |
| `material_datas/PRTS/**`（含 `_manifest.json`、`_range_codes.json`、`特殊机制/`） | 三个爬虫 |
| `merged.json`、`final_lists.tsv` | `--sync-dicts`（无脚本读取） |
| `agent_workspace/tag_pipeline/stats.json` | `tools/prts_stats.py` |

两个例外说明：`deterministic.json` 是基础属性快照（不随 TAG 变化）；`results/operator-tags.json` 与 `results/player-tags-criteria.json` 的**顺序**另有第二个写者 `tools/apply_tag_order.py`（只重排、不重生成）。

### 属性与数值工具（非生成链路，按需运行）

`tools/prts_stats.py`（PRTS 语料 → `stats.json`，并提供 `panel_of()` 面板复算）与 `tools/verify_numbers.py`（对着 `stats.json` 校准产物里的面板／档位／恒等式／内部代号／因子覆盖）。两者与 `stats.json` 一样**是生成物**：要改 `stats.json` 就改爬虫侧或重跑 `tools/prts_stats.py`，不手改。

### 其余按需工具

`crawlers/strip_prts_noncombat.py`（剥离回填与审计，见 `docs/crawling-and-strip.md`）、`.claude/skills/tag-batch-rewrite/scripts/_apply_batch.py`（批次回填）、`tools/module_notes.py`（模组「※」条文汇编）——用法见 `docs/commands.md` 与各自技能文档。

### 只为背景、不作依据

`docs/verification-complaints.md`、`agent_workspace/tag_pipeline/player_tags/_mode-limited-module-audit.md`、`agent_workspace/tag_pipeline/official-fullmap-aura.md`（历史转制稿）、`docs/history-notes.md`（历史记录汇编）。`docs/mechanism-understanding.md` 是**机制常识正典**——判别原则以它为准（其中的计数与举例如有出入，以现行文件为准）。

## 五、稳定作业约定

- 分支 `master`；`docs/player-tags-specify.md` 由开发者不定期手改。
- 一切手写文档正文用中文（规则见 `docs/README.md`「撰写语言」）。
- 提交前跑 `tools/run_all_checks.py`（十项，清单以脚本 `CHECKS` 为准）；除开发者要求外不提交。
- Windows 控制台是 GBK：Python 一律加 `-X utf8`（或 `PYTHONIOENCODING=utf-8`），否则中文直出是乱码。
- 机制文档（`mechanism-understanding.md`、`verification-complaints.md`）存在的原因是同类误判反复发生（灼烧 DoT ≠ 灼燃损伤；屏障 vs 护盾 vs 闪避；「每帧检测」的实装注记 vs 真实帧机制）——断言某个机制前先查它们。
- 游戏术语定义在 `docs/glossary.md`；判任何以术语表述的东西前先查（例：过载＝技能进行到一半触发额外效果、覆盖后半程；魔力、吟唱同理）。
