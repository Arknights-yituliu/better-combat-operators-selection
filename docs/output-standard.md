# 最终输出 JSON 规范（干员 TAG 分类结果）

> 本文定义本项目最终产出、供 UI 项目消费的 **干员 TAG 分类结果 JSON**：一个文件同时承载官方设定 TAG 与玩家体感 TAG 下的全部干员，TAG 与干员为多对多关系，每条关系带「条件」「备注」。
> 上游依据：`docs/concept.md`（结果 JSON 要求、条件/备注规则）、`docs/official-tags-members.md`（官方设定 TAG 名单）、`docs/player-tags-members.md`（玩家体感 TAG 名单）。
> 另一份产物「战斗术语 JSON」（`results/combat_glossary.json`）不在本文范围内。

## 1. 文件、版本与更新

| 项 | 约定 |
|---|---|
| 文件 | `results/operator-tags.json`（生成后复制到 UI 项目使用） |
| 编码 | UTF-8（无 BOM）；`ensure_ascii=False`，中文直书；2 空格缩进 |
| `version` | 版本标记，首次发布固定为 `"v1"`，此后每次内容变更递增（`"v2"`、`"v3"`…） |
| `updated` | 当前版本日期，`yyyy-MM-dd` |

**需要升版本的变化**（任一条发生即更新 `updated`、递增 `version`）：

1. TAG 增删、改名、排序变化（官方类／玩家类均含）；
2. TAG 下成员增删；
3. 荐（`recommended`）变化；
4. 干员基本信息（稀有度／职业／分支／势力／实装时间等）修正；
5. 新干员实装并进入任一 TAG 成员表；
6. 子 TAG／分组（`subTags`）的增删、组名或取值变化；
7. 字段的形状变化（如 `remark` 由字符串改为块数组）。

UI 项目据 `version` 判断是否需要重新导入数据；`updated` 供人查看当前数据的新旧。

## 2. 顶层结构

```json
{
  "version": "v1",
  "updated": "2026-09-12",
  "operators": [],
  "tags": []
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| version | string | 是 | 版本标记，`"v1"` 起 |
| updated | string | 是 | 更新日期，`yyyy-MM-dd` |
| operators | array | 是 | 干员基本信息表（§3）。只收录**至少在 1 个 TAG 成员表中出现过**的干员 |
| tags | array | 是 | TAG 列表（§4）：官方设定 TAG 在前、玩家体感 TAG 在后 |

**不得进入本文件的内容**：评定标准（含判定规则、定义句）、`文件:行号` 证据、边界与排除记录、待开发者确认项、检索记录。这些只属于生产文档；UI 侧不需要，也不应出现在结果 JSON 中。生产文档的路径引用（`08-拐杖.json`、`_brief.md` §x、`<干员>/攻击范围.md` 等）同样不进入：生成时改写为产品可读表述（`08-拐杖.json` → `「拐杖」TAG`）或直接删除。

## 3. 干员基本信息（operators）

一张信息卡片中**与 TAG 无关、固定不变**的部分；只存一份，成员表通过「干员名」引用（避免同一干员在多 TAG 下重复存储而不一致）。

```json
{
  "name": "白铁",
  "charId": "char_4072_ironmn",
  "rarity": 6,
  "class": "辅助",
  "branch": "工匠",
  "faction": "维多利亚",
  "releaseDate": "2022-10-11",
  "prtsUrl": "https://prts.wiki/w/%E7%99%BD%E9%93%81"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| name | string | 干员名（成员表的引用键）。形态名保留原文括号，如 `阿米娅(近卫)`、`阿米娅(医疗)`、`Mon3tr` |
| charId | string | 干员编号（如 `char_1035_wisdel`）。来源：资源项目 `character_table.json`（`char_*` 条目）；阿米娅(近卫)/(医疗) 等形态条目取自 `char_patch_table.json` 的 `patchChars`；重名条目取 `isNonObtainable=False` 者（如 暮落→`char_4025_aprot2`）。映射缓存：`agent_workspace/tag_pipeline/char_ids.json` |
| rarity | int | 稀有度 1–6（PRTS 干员信息里的「稀有度」是 0 基字段，此处取其值 +1，即星级） |
| class | string | 职业（先锋／近卫／狙击／重装／医疗／辅助／术师／特种） |
| branch | string | 分支（如 工匠、策士、处决者） |
| faction | string | 势力：取 PRTS「属性」表「所属势力」（多个并列时以 `、` 连接，如 `阿戈尔、深海猎人`）；为空时取「隐藏势力」；均无时取 `""` |
| releaseDate | string | 实装时间 `yyyy-MM-dd`（PRTS「获得方式」表的上线时间） |
| prtsUrl | string | 干员主页 URL（干员名 percent 编码，不带锚点） |

- 数据来源：`material_datas/PRTS/<干员>/<干员>.md`（稀有度·职业＝干员信息，稀有度取原始字段 +1；分支＝特性表；势力＝属性表；实装时间＝获得方式表；实装时间缓存见 `agent_workspace/tag_pipeline/player_tags/_launch_dates.json`）。
- 数组顺序按实装时间倒序；UI 不应依赖该顺序。

## 4. TAG 与成员

### 4.1 TAG 条目

```json
{
  "id": "D_zone",
  "name": "待部署区支援",
  "source": "official",
  "category": "D 部署与编队",
  "members": []
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 稳定标识。官方类＝TAG 字典 id（`A_stun`、`D_zone`…）；玩家类＝`P01`–`P13`（与 `agent_workspace/tag_pipeline/player_tags/NN-*.json` 编号一致；**`P10`／`P11` 已退役**——原「大力推拉」「阻挡数5」并入 `P13`「高档控制」作其子 TAG，**退役 id 不得复用**）。**一经发布不得复用或更改**；TAG 改名时保留原 id |
| name | string | 是 | TAG 名称（与名单文档一致，如 `阻挡数5`、`待部署区支援`） |
| source | string | 是 | `"official"`（官方设定类）或 `"player"`（玩家体感类）；UI 可分源筛选、可互相引用 |
| category | string | 官方类必填 | 类别名：`A 控制·异常`、`B 伤害类型`、`C 生存与增益`、`D 部署与编队`、`E 技力与技能资源`、`F 治疗与支援`、`G 召唤物`、`H 攻击行为特征`、`I 全场光环`（取自 `docs/official-tags-members.md` §3 总览，省略括号补充） |
| recommended | array | 仅玩家类 | **荐**名单（§6）：元素为干员名；无荐时为空数组 `[]`。官方类省略该字段 |
| recommendedFallback | array | 仅玩家类 | **兜底荐**名单（§6）：`recommended` 为空数组时由 UI 展示；无兜底荐时为空数组 `[]`。官方类省略该字段 |
| recommendedBySub | array | 仅玩家类（有子 TAG 的 TAG） | **按子 TAG 的荐**（§6）：元素 `{group, value, names}`；无时省略。无子 TAG 的 TAG 与官方类省略该字段 |
| recommendedFallbackBySub | array | 同上 | 按子 TAG 的**兜底荐**（§6）：元素同上；无时省略 |
| members | array | 是 | 成员（TAG×干员关系），见 4.2 |

- 排序：`tags` 数组顺序＝UI 展示顺序——官方类按 `docs/official-tags-members.md` §4 顺序（A→I），玩家类按 `player_tags/_merge_to_docs.py` 的 `TAGS` 顺序（决战歼灭、次数对策、吃拐一轮秒、远程消耗、插拔容错、初动增加、充电、拐杖、保人、**高档控制**、阵容组合）。
- 官方类 id 以 TAG 字典（`agent_workspace/tag_pipeline/catalog.json`）为准；`merged.json`／`final_lists.tsv` 由 `_merge_official_to_docs.py --sync-dicts` 从分模块同步（维护方式见 §7 末），逐 TAG 的计数、首现、名单一律以 `docs/official-tags-members.md` §4 为准。

### 4.2 成员（TAG×干员关系）

```json
{
  "operator": "林",
  "condition": "精英1；2技能（专三）",
  "remark": [
    { "label": "2技能", "items": [
      { "text": "25 秒内使攻击范围内所有友方单位享受第一天赋效果——每个干员单独获得可抵挡所有伤害的琉璃璧、单独计算破碎与恢复" } ] }
  ],
  "subTags": [
    { "group": "子 TAG", "value": "屏障·护盾" }
  ],
  "source": { "model": "ArkDPS", "url": "https://ark-dps.com/zh/", "author": "极夜星辰", "parts": "帧模型与用法分支", "detail": "可攻击时长与取整帧采用站点帧模型；情形名采用站点用法分支名；间隔、面板与判定按我方" },
  "prtsUrl": "https://prts.wiki/w/%E6%9E%97#技能"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| operator | string | 是 | 干员名，指向 `operators[].name` |
| condition | string | 是 | **硬性达成条件**（精英化／技能／专精／模组与等级／模式限定／目标限制）；精英 0·1 级即具备者写 `"无"`；`；` 分隔各条要求、`／` 表「或」。**两档并列只用于玩家体感 TAG**——最低档即满足该 TAG、且满配档抵达最高成绩者，两档各自的硬性条件用 `／` 并列（`精英1＋2技能（7级数值） ／ 精英2＋2技能（专精3数值）`）；官方类与其余干员一律只写达成该 TAG 所需的那一档（写法见 `docs/concept.md`「条件分条」） |
| remark | array | 否 | **信息加工后的备注**（数值、持续时间、隐藏机制、特殊用法、战术帮助），块数组，结构见下；无内容时省略该字段（模组隐藏机制查 `docs/module-hidden-mechanics.md`） |
| subTags | array | 否 | 子 TAG／分组（支持两级嵌套，可被筛选，多选取交集），元素为 `{group, value, detail?}`，见 4.3；无分组时省略 |
| source | object | 否 | **外部计算工具来源**：显示成绩采用了 ArkDPS 的帧模型／算法框架／用法分支时给出 `{model, url, author, parts, detail}`——`model` 工具名、`url` 官网、`author` 作者（极夜星辰）、`parts` 本条引用的部分（如「帧模型与用法分支」「组合公式与默认数据」）、`detail` 该部分的详细说明（口径见 `docs/calc-rules.md` §4.10）；未采用者省略。消费端**仅在详情卡片末尾**据此展示一条「数据来源：ArkDPS（作者：极夜星辰 · 官网 ark-dps.com/zh/）｜引用部分：{parts}——{detail}」 |
| prtsUrl | string | 是 | 该 TAG 下点击卡片的 PRTS 跳转地址，见 §5 |

**`remark` 的块结构**（撰写写法与块序见 `docs/concept.md`「备注分块」，撰写侧不手写本结构）：

```json
"remark": [
  { "label": "成绩 最高档（精英2 满级＋满信赖＋潜能3）",
    "items": [ { "label": "2技能", "text": "15 秒总伤 ≈62868、平均 DPS ≈4191/秒" } ] },
  { "label": "2技能「重力自定义」",
    "items": [ { "label": "持续", "text": "22 秒" },
               { "label": "范围", "text": "攻击范围扩大（15 格）、同时攻击 5 个目标" } ] }
]
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| label | string | 否 | 块标签：`成绩` 或 `成绩 <情形名>（<面板口径>）`、能力全称（`2技能「…」`／`第一天赋「…」`／`特性`／`模组「X」N级`／`召唤物「…」`）、`计算`、`说明`；无标签块省略该字段 |
| items | array | 是 | 块内的条，至少一条 |
| items[].label | string | 否 | 条标签：成绩块与计算块＝技能名，能力块＝维度词（`持续`／`范围`／`伤害`／`打数`／`其它` 等）；无则省略 |
| items[].text | string | 是 | 条正文 |

- 块序固定（成绩 → 各能力块 → 计算 → 说明）；`items` 为空的块、空数组的 `remark` 一律省略。
- 旧文本（源单元格不含 `｜`）自动成为「单块 + 条按 `；` 拆分」，两个字段的形状对所有条目一致。

**「阵容组合」（P12）的成员为组合条目**（字段形状与上表不同，其余 TAG 沿用上表）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| combo | string | 是 | 组合名（如 `深海猎人`），同一 TAG 内唯一 |
| condition | string | 是 | **组合级硬性条件**（来自分文件的「触发条件」bullet） |
| remark | string | 否 | **组合整体机制**（来自「组合整体机制」bullet）；无内容时省略该字段 |
| beneficiaries | array | 否 | **受益者名单**（展示用，不参与干员维度筛选），元素为干员名；不可枚举的全阵营组合省略该字段、范围写进备注 |
| providers | array | 是 | **提供者明细**，至少一名；元素为 `{operator, condition, remark?, prtsUrl}`，逐项同「成员」字段规则 |

- 组合条目的 `subTags` 为子 TAG 分类（`子 TAG`＝`势力`／`用法`，见 §4.3）；唯一性以组合为界——**组合名在同一 TAG 内唯一、组合内提供者不重复；同一提供者可出现在多个组合**。
- 同一干员可属多个 TAG（多对多，属其他 TAG 不构成排除理由）；**唯一性以末端子 TAG（组＋值）为界——同一干员可在同一 TAG 的不同末端子 TAG 下各出现一条（如 次数对策 的机械师同时命中「多段伤害」「间隔伤害」；官方 闪避 下「物理闪避」与「可给予他人」是两个不同末端），同一末端子 TAG 内不得重复**；无子 TAG 的 TAG 视为只有一个末端（即 TAG 自身）。
- 名单文档（`docs/official-tags-members.md`、`docs/player-tags-members.md`）的成员表含「编号」列（charId，文档展示用）；本文件的成员仍按 `operator` 名引用 `operators[].name`，编号只在 `operators[]` 存一份。
- 条件／备注的写法与成绩项（总攻/总伤、平均 DPS、等效每秒段数）沿用 `docs/concept.md`「结果展示」，备注的分块与分条见同文「备注分块」；**官方类**另按 `docs/official-tags-members.md` §1：条件＝硬性要求（精英化／技能／模组与等级／模式限定；天生即具备写「无」），备注以游戏内原文引用为证据。
- 成员顺序＝名单文档顺序（实装时间倒序；同实装日按拼音序），UI 默认按此顺序展示；**UI 提供实装时间正序／倒序切换**——排序键取该干员的 `operators[].releaseDate`（§3），同日成员保持文档内相对次序、不随切换倒转。成员表分多张子表的 TAG（决战歼灭、次数对策、吃拐一轮秒、远程消耗、充电、初动增加、保人、高档控制）合并为单一成员列表后按实装时间倒序重排（稳定排序，子 TAG 分组信息保留在 `subTags`）；「阵容组合」除外——其成员即组合条目（上表），按分文件的组合顺序排列，不按实装时间重排，正序／倒序切换不影响其顺序。

### 4.3 子 TAG（subTags）

子 TAG 用于区分同一 TAG 下的实现方式、数值类型、生效范围等，同样可被筛选（`docs/player-tags-specify.md` 要求）；支持**两级嵌套**（组 → 值，更深一层见下「嵌套」一条；必要时第三层 `detail`）。取值直接使用各分文件成员表的分组：

```json
"subTags": [
  { "group": "增益类型", "value": "攻击力(加算)" },
  { "group": "生效方式", "value": "触发时", "detail": "造成治疗时" }
]
```

| 玩家 TAG | group（组） | value（取值闭集） |
|---|---|---|
| 决战歼灭 | 子 TAG | `小范围`、`大范围`、`主物理伤害`、`主法术伤害`、`主真实伤害`、`主弱点伤害`、`物法混伤`、`物真混伤`、`物元混伤`、`法元混伤`（判据按技能；每个技能在范围轴（行内「范围」列）与伤害轴（所在子表）各归一档、恰取 1 个范围值＋1 个伤害值；**排列顺序即本列序**） |
| 吃拐一轮秒 | 子 TAG | `聚爆`、`连射`、`慢热`（多值可并存） |
| 高档控制 | 子 TAG | `大力推拉`、`阻挡数5`、`长效控制`、`远距控制`（之下再分 `独立达成`、`需配合`）、`硬控`、`软控` |
| 次数对策 | 子 TAG | `多段伤害`、`间隔伤害` |
| 远程消耗 | 子 TAG | `超远距离打击`、`远程部署型召唤物与装置`（之下再分 `召唤师 / 装置型召唤物`）、`全场触发式伤害` |
| 插拔容错 | 救急路径；承载方式 | 救急路径：`低再部署循环`、`部署即生效`、`不占部署位`、`撤退收益`、`初动为满的落地点火`、`远位蓄力`、`能够实现重部署`；承载方式：`召唤物承载`（其余为干员本体承担、不设值） |
| 初动增加 | 子 TAG | `编入队伍`、`部署时点` |
| 充电 | 子 TAG | `直接补充技力`、`技力回复速度加快`、`补弹` |
| 拐杖 | 增益类型；生效方式 | 增益类型：`攻击力(加算)`、`攻击力(倍率)`、`攻击速度`、`易伤(脆弱)`、`伤害提升(友方)`、`附加伤害(友方)`；生效方式：`在场`、`编入`、`携带`、`部署时`、`技能开启时`、`技能期间`、`触发时`（detail：`造成治疗时`、`击倒敌人时`、`装置升级时`、`吟唱后`） |
| 保人 | 子 TAG | `治疗·减免·防御·法抗·庇护`、`屏障·护盾`、`闪避·迷彩`、`元素损伤防护`、`免死·锁血·伤害转移`、`嘲讽·吸引火力·指定承伤` |
| 阵容组合 | 子 TAG | `势力`（各阵营/小队联动组合）、`用法`（ArkDPS 上有组合计算、且参与者已被玩家体感 TAG 收录的玩家用法组合） |

- 同一 `group` 可出现多次（如「聚爆＋连射」、拐杖的多条生效方式）；`detail` 仅在「触发时」一档使用；同一组值不重复。**覆盖**：有子 TAG 的玩家 TAG，其**全部成员必须至少归属一个子 TAG**（去重后的并集＝该 TAG 的全部成员）；**TAG 级不承载成员**（子 TAG 是唯一落人处）。
- **嵌套**：`subTags` 的元素是「父节点 → 子节点」的一条边。子 TAG 之下再分组时（`docs/player-tags-specify.md`：两级嵌套），把上一级的 `value` 用作下一级的 `group` 续写——如 远程消耗「表 2」下再分 2A：`{"group": "子 TAG", "value": "远程部署型召唤物与装置"}` ＋ `{"group": "远程部署型召唤物与装置", "value": "召唤师 / 装置型召唤物"}`。末端＝链上没有下级的那个值。
- **筛选语义**：末端子 TAG 即可筛选项。**多选取交集**——同一 TAG 下勾选多个子项时，干员须**逐项命中**：对每个已选子项，该干员在该 TAG 下都存在某条条目带有该子项（可分散在不同条目上）；不勾任何子项 ＝ 该 TAG 不限子项。「阵容组合」（P12）的子项＝子 TAG（`势力`／`用法`）与组合名；多选时按「逐项命中」过滤组合（子 TAG 取组合的 `subTags`，组合名取组合名），为本条的 P12 专用读法。
- 备注中的结构性前缀在写入 `subTags` 后不再保留：官方类「子 TAG：…。」、玩家类 插拔容错 的「救急路径：…」；剥离完这些前缀后，余下文本才按「备注分块」解析为 `remark` 的块数组。其余备注原文保留（含官方「抗削弱」的作用范围注记，如 `作用范围/仅自身`，属备注内容、不作 `detail`）。
- 官方类的子 TAG 同样写入本字段。**同一 TAG 可有多个子 TAG 组**：组名不写在行内，由「取值 → 组名」的取值闭集判定，与前缀先后无关（闪避 同时有「闪避类型」「作用范围」两组，成员行写作 `子 TAG：物理闪避、法术闪避。子 TAG：可给予他人。…`）。单层分组用 `{"group": "子 TAG", "value": "…"}`；例：全场光环 的 `伤害光环`／`削弱光环`／`增益光环`／`治疗光环`／`增伤光环`，抗削弱 的 `下限保护`／`上限提高`，帧级结算 的 `帧级判定`／`帧伤`，闪避 的 `物理闪避`／`法术闪避`／`全伤害闪避`（组名「闪避类型」），以及 护盾（按层抵挡）／屏障（吸收值）／免死·复活·替身／闪避／伤害减免·减伤／庇护（物法减伤）／迷彩／抵抗／嘲讽·吸引攻击／降低被攻击优先级 的 `仅自身`／`可给予他人`（组名「作用范围」；两者互斥——能作用于其他我方单位即记 `可给予他人`，判定以效果实际可及为准）。

## 5. PRTS 跳转地址

点击某 TAG 下的干员卡片时，打开该关系上的 `prtsUrl`。

- **地址构成**：`https://prts.wiki/w/` ＋ 干员名（UTF-8 percent 编码，大写十六进制）＋ 可选锚点。
- **锚点取该 TAG 能力在干员页中的位置**：只有当该能力**只来自一个章节**时才加锚点；跨章节或由干员整体机制构成时落到干员主页（无锚点）。

| 该 TAG 能力来源 | 锚点 | 示例 |
|---|---|---|
| 仅技能（含技能自带的装置／召唤物） | `#技能` | 白铁·充电（仅 2 技能）→ `https://prts.wiki/w/%E7%99%BD%E9%93%81#技能` |
| 仅天赋（模组只做强化时仍算天赋） | `#天赋` | 陈·充电（天赋「呵斥」，X 模组仅强化） |
| 仅模组（能力本身由模组追加） | `#模组` | 归溟幽灵鲨·充电（技力回复由 Y 模组 2 级追加） |
| 仅分支特性（条件为「无（分支特性）」等，条件里未提及其它来源） | `#特性` | 溯光星源·施加停顿（凝滞师分支特性自带停顿） |
| 仅召唤物／装置（常驻，不随技能） | `#召唤物信息` | 官方「拥有召唤物」「召唤物退场返还/自动刷新」「技能-召唤物绑定」类 TAG：召唤物随技能者锚 `#技能`，常驻者锚「召唤物信息」段 |
| 跨两类及以上，或无法确定唯一来源 | 无锚点（干员主页） | 凛御银灰·官方「待部署区支援」：天赋与技能均可支援待部署区 → `https://prts.wiki/w/%E5%87%9B%E5%BE%A1%E9%93%B6%E7%81%B0` |

- 锚点用 PRTS 章节名原文（如 `#技能`），浏览器会自动编码，与 `#%E6%8A%80%E8%83%BD` 等价；可用锚点即干员页的 `#特性`／`#天赋`／`#技能`／`#模组`／`#召唤物信息` 五个章节。
- 锚点按「能力来源」判定，来源以该关系的「条件／备注」文本为准（条件为主判据，备注主句作补充）；判定不确定时一律用干员主页（宁可不锚定，不可跳错）。目前由生成脚本按此规则自动判定，锚不准的条目可在面板中改。

## 6. 荐（recommended / recommendedBySub）

- **定义**：**荐**＝人工指定的名单，默认指定「该范围内推荐新手优先培养」的干员；当某范围**没有值得新手优先培养的干员**时，转为指定「该范围下综合实力较强」的干员（写入兜底文件）。两份名单均人工指定，程序只负责读取与渲染，不计算、不生成任何名单。
- **作用域**：**有子 TAG 的顶级 TAG，荐下沉到子 TAG**——按子 TAG 分别指定与展示（便于玩家知道干员因何被荐）；**TAG 级不得设荐**（TAG 级不承载，新增会被 `tools/recommend.py` 与面板拒绝、`check` 会列出）。没有子 TAG 的顶级 TAG 用 TAG 级名单。
- **位置**：无子 TAG 的玩家 TAG 用 `recommended` / `recommendedFallback`（字符串数组，无名单时为空数组 `[]`）；有子 TAG 的玩家 TAG 用 `recommendedBySub` / `recommendedFallbackBySub`（数组，元素 `{group, value, names}`，`value` 为该 TAG 的子 TAG 名；无名单时省略字段），此时 `recommended`/`recommendedFallback` 必须保持空数组（仅存兼容空值，不得设置 TAG 级荐）。官方类 TAG 省略以上字段。
- **读取规则**：每个子 TAG 的「有效荐名单」＝该子 TAG 的 `names` 非空时用它、为空时用 `recommendedFallbackBySub` 中同名子 TAG 的 `names`；顶级 TAG 的荐＝其全部子 TAG 有效名单的并集（勾选子 TAG 时只取所选子 TAG 的名单取交集）；未下沉的 TAG 按 `recommended` 非空用它、为空用 `recommendedFallback`。同时选中多个玩家体感 TAG 时仍取**交集**（每个 TAG 都要有荐才显示）。
- **约束**：两份名单的元素都必须是该作用域的成员（干员或组合名）；同一作用域内不重复（由工具强制校验，避免笔误产生悬空引用）。
- **阵容组合（P12）**：`recommended` 元素可为**组合名**（须为该 TAG 的组合条目名）或该组合内的**提供者干员名**，二者可混排且**互相独立**——为组合加荐不等于为其提供者加荐，反之亦然；UI 以组合为列表容器、在组容器与组员元素上分别展示荐标识（组荐与组员荐不是覆盖关系）。
- **指定方式**：两份名单均由开发者人工指定（AI 可提出建议，不直接写入）。
- **维护工具**：`tools/recommend.py`（命令行）与 `recommend_gui.py`（本地网页面板；当前面板只维护「荐」，兜底荐用 `tools/recommend.py --fallback` 维护），源文件 `agent_workspace/tag_pipeline/player_tags/_recommend.json` 与 `_recommend_fallback.json`。

```bash
python tools/recommend.py                     # 列出 11 个玩家 TAG 及当前荐（含子作用域）
python tools/recommend.py list 充电           # 查看某作用域的荐
python tools/recommend.py list 高档控制/纯御天花板
python tools/recommend.py add 充电/直接补充技力 白铁   # 添加荐（可一次多个）
python tools/recommend.py add 高档控制/纯御天花板 蛇屠箱
python tools/recommend.py remove 充电/直接补充技力 白铁  # 移除荐
python tools/recommend.py check               # 校验两份名单（TAG／子值／成员是否仍然有效）
python tools/recommend.py --fallback list 充电           # 查看兜底荐
python tools/recommend.py --fallback add 充电 白铁       # 添加兜底荐
python tools/recommend.py --fallback remove 充电 白铁    # 移除兜底荐

python recommend_gui.py                 # 网页面板：「荐」页按 TAG 与子作用域切换编辑（左键加荐 / 右键取消）；
                                        #   「人工归纳」页摘取干员并入 TAG 并编辑「条件」「备注」；
                                        #   「结果 JSON」页编辑产物，保存时按两份荐文件重算荐字段
```

- 两份名单只维护在 `_recommend.json` / `_recommend_fallback.json`（不写进名单文档）；生成结果 JSON 时按 TAG 名合并进 `recommended` / `recommendedFallback` 字段，重新生成不会丢失。「结果 JSON」页保存时同样按两份荐文件重算荐字段（面板内荐为只读展示），覆盖保存后产物与荐文件一致。
- 面板中「荐」页只负责增删荐（点「详情」在右栏查看干员信息卡片）；「条件」「备注」在「人工归纳」页维护（按「块＋行下标＋行现值」结构化写回分文件对应行，保存后自动重新合并名单文档）。「人工归纳」页还可增删成员行：扩展＝新行条件/备注留空，移动＝把源行的条件/备注/依据带到新行并删除源行，移除＝直接删除该行；官方分文件的条目头「（N 人 · 首现 日期）」为渲染期派生值，无需重算。

## 7. 数据来源、生成与发布

| JSON 部分 | 来源 |
|---|---|
| `operators` | `material_datas/PRTS/<干员>/<干员>.md`（含 `_launch_dates.json` 的实装时间）＋ `agent_workspace/tag_pipeline/char_ids.json`（charId 映射） |
| 官方类 `tags` | `docs/official-tags-members.md`（79 个 TAG 成员表：干员／编号／条件／备注）＋ TAG 字典 `agent_workspace/tag_pipeline/{catalog.json, merged.json, final_lists.tsv}`（文档维护层：`agent_workspace/tag_pipeline/official_tags/*.md`，经 `_merge_official_to_docs.py` 合入文档 §3/§4/§5） |
| 玩家类 `tags` | `docs/player-tags-members.md`（由其分文件 `agent_workspace/tag_pipeline/player_tags/NN-*.json` 合并生成） |
| `recommended` | `agent_workspace/tag_pipeline/player_tags/_recommend.json`（`tools/recommend.py` 维护） |
| `subTags` | 玩家类＝各分文件成员表的分组（「子 TAG」列／子表标题／「救急路径：」等行内标记）；官方类＝备注开头的「子 TAG：…。」（可连续多个前缀＝多个组），组名按 `tools/generate_results.py` 的取值闭集表判定：闪避（闪避类型／作用范围）、全场光环、抗削弱、帧级结算，以及 护盾（按层抵挡）／屏障（吸收值）／免死·复活·替身／伤害减免·减伤／庇护（物法减伤）／迷彩／抵抗／嘲讽·吸引攻击／降低被攻击优先级 的「作用范围」组 |
| `prtsUrl` | 按 §5 规则生成（干员名编码＋锚点） |

**机读字典与一致性**：`catalog.json` 是脚本唯一读取的 TAG 字典（手写维护，name 必须与分模块条目标题逐字一致）；`merged.json`（干员→TAG id，id 按 catalog 顺序）与 `final_lists.tsv`（TAG→成员）由 `agent_workspace/tag_pipeline/official_tags/_merge_official_to_docs.py --sync-dicts` 从分模块重建，改 TAG 结构后需重跑；`deterministic.json` 为基础属性快照，不随 TAG 变化。各处的 TAG 数／关系数一律以 `docs/official-tags-members.md` §3 为准，其它文档不另行记数。

1. 生成脚本：`tools/generate_results.py`。读两份名单文档＋字典／charId 映射／实装时间／荐文件，按本规范合成 `results/operator-tags.json`（CRLF、2 空格缩进、`ensure_ascii=False`）；`--check` 只生成到内存并跑规范校验，`--report` 另打印逐 TAG 计数。同一次运行另写出**辅助名单** `docs/untagged-operators.md`（`docs/operators.txt` 全量 − `operators[]`，即未进任何成员表的干员）。
2. 生成时顺带做文本规范化（不改变含义）：去 markdown 强调标记与 `文件:行号` 证据（源单元格里的 `**` 只作编辑标记、不进产物；产物的文本不使用 md 语法，行内强调用 HTML 白名单标签 `<strong>`／`<code>` 书写——前端按白名单渲染，见 `docs/ui-render-rules.md` §7）；生产文档路径引用改写为产品表述（`08-拐杖.json` → `「拐杖」TAG`、`_brief.md` §x → 删除、PRTS 素材路径 → 删除）；备注开头的结构性前缀（「子 TAG：…。」「救急路径：…」，可连续多个）折入 `subTags` 后不再保留；`remark` 按 `｜`（块）与 `；`（条）解析为 §4.2 的块数组。
3. 文本 lint：生成时按 `docs/concept.md`「备注分块」的禁用项检查源单元格（`★` 分类标记、`备注：`／`PRTS 备注：` 等前缀、`（下详）` 类悬空引用、`S2` 类简写、UI 指令文字），`--check` 逐条列出、不阻断写出——报告即存量待重排清单。

发布流程：`.venv/Scripts/python.exe -X utf8 tools/generate_results.py`（先 `--check` 确认零问题）→ 核对 `version`／`updated` 与抽查若干干员卡片 → 复制到 UI 项目。

**手工编辑**：`recommend_gui.py` 的「结果 JSON」页可把 `results/` 下的 json 载入内存编辑（结构化卡片 + 源码视图共用一份数据，编辑期间不写盘），再由「保存…」选择覆盖已有文件或新建自定义文件名；保存前按本规范列出问题（可定位，但不阻断保存，仅内容不是合法 JSON 时拒绝写盘），内容有变化时按 §1 更新 `version`／`updated`。该页只编辑、不生成初版。

## 8. 待定与扩展

1. 官方 TAG 家族关系（如 造成元素损伤 顶层与四个子系）是否需加 `parent` 字段；当前各自为独立 TAG，层级只记录在文档中。
2. 官方类 TAG 是否也需要「荐」；如需要，扩展方式与玩家类相同。
3. 干员基本信息是否补充其他字段（如 获取方式、阵营标签）由 UI 需求决定，新增即需升版本。

## 9. 完整示例（节选）

```json
{
  "version": "v1",
  "updated": "2026-09-12",
  "operators": [
    {
      "name": "凛御银灰",
      "charId": "char_1045_svash2",
      "rarity": 6,
      "class": "先锋",
      "branch": "策士",
      "faction": "谢拉格",
      "releaseDate": "2025-11-01",
      "prtsUrl": "https://prts.wiki/w/%E5%87%9B%E5%BE%A1%E9%93%B6%E7%81%B0"
    },
    {
      "name": "松桐",
      "charId": "char_4199_makiri",
      "rarity": 5,
      "class": "先锋",
      "branch": "策士",
      "faction": "东",
      "releaseDate": "2025-08-02",
      "prtsUrl": "https://prts.wiki/w/%E6%9D%BE%E6%A1%90"
    },
    {
      "name": "白铁",
      "charId": "char_4072_ironmn",
      "rarity": 6,
      "class": "辅助",
      "branch": "工匠",
      "faction": "维多利亚",
      "releaseDate": "2022-10-11",
      "prtsUrl": "https://prts.wiki/w/%E7%99%BD%E9%93%81"
    },
    {
      "name": "归溟幽灵鲨",
      "charId": "char_1023_ghost2",
      "rarity": 6,
      "class": "特种",
      "branch": "傀儡师",
      "faction": "阿戈尔、深海猎人",
      "releaseDate": "2022-05-01",
      "prtsUrl": "https://prts.wiki/w/%E5%BD%92%E6%BA%9F%E5%B9%BD%E7%81%B5%E9%B2%A8"
    }
  ],
  "tags": [
    {
      "id": "D_zone",
      "name": "待部署区支援",
      "source": "official",
      "category": "D 部署与编队",
      "members": [
        {
          "operator": "凛御银灰",
          "condition": "无",
          "prtsUrl": "https://prts.wiki/w/%E5%87%9B%E5%BE%A1%E9%93%B6%E7%81%B0"
        },
        {
          "operator": "松桐",
          "condition": "无",
          "prtsUrl": "https://prts.wiki/w/%E6%9D%BE%E6%A1%90"
        }
      ]
    },
    {
      "id": "P07",
      "name": "充电",
      "source": "player",
      "recommended": ["白铁"],
      "recommendedFallback": [],
      "members": [
        {
          "operator": "白铁",
          "condition": "精英1；2技能（高效补给）；由支援装置对范围内一名我方干员生效",
          "remark": [
            { "label": "装置型", "items": [
              { "text": "装置使一名我方干员每 3.5 秒获得 1 点技力" },
              { "text": "技能期间装置强化为每 3 秒/2.5 秒/2 秒获得 1 点，但装置生命流失翻倍" },
              { "text": "技能结束装置销毁" },
              { "text": "装置效果可叠加" } ] }
          ],
          "prtsUrl": "https://prts.wiki/w/%E7%99%BD%E9%93%81#技能"
        },
        {
          "operator": "归溟幽灵鲨",
          "condition": "精英2；Y模组3级；仅【深海猎人】；编入队伍时（不需在场）",
          "remark": [
            { "label": "光环型（阿戈尔的深邃）", "items": [
              { "text": "编入队伍时所有【深海猎人】干员技力自然回复速度 +0.5/秒（Y模组3级）" },
              { "text": "属技力光环类，同类效果取最高" } ] }
          ],
          "prtsUrl": "https://prts.wiki/w/%E5%BD%92%E6%BA%9F%E5%B9%BD%E7%81%B5%E9%B2%A8#模组"
        }
      ]
    },
    {
      "id": "P12",
      "name": "阵容组合",
      "source": "player",
      "recommended": [],
      "recommendedFallback": [],
      "members": [
        {
          "combo": "深海猎人",
          "condition": "各成员天赋独立生效、可叠加；斯卡蒂/安哲拉/归溟幽灵鲨的加成「编入队伍即生效」，歌蕾蒂娅/乌尔比安/幽灵鲨需在场上；多数需精英2解锁对应天赋，幽灵鲨的阵营天赋必须开启 X 模组",
          "remark": [
            { "items": [
              { "text": "多名深海猎人的天赋分别作用于攻击力、攻击速度、生命值、生命回复、造成伤害与技力回复，来源互不冲突、可叠加" },
              { "text": "乌尔比安是唯一「场上击杀叠层 + 与队友同步」的机制" } ] }
          ],
          "beneficiaries": ["乌尔比安", "安哲拉", "幽灵鲨", "归溟幽灵鲨", "斯卡蒂", "歌蕾蒂娅"],
          "providers": [
            {
              "operator": "归溟幽灵鲨",
              "condition": "精英2（第二天赋）；Y模组2/3级可增幅；编入队伍即生效",
              "remark": [
                { "items": [
                  { "text": "编入队伍时所有【深海猎人】生命值+20%（潜5 +23%）" },
                  { "text": "Y2：+25%且技力自然回复+0.3/秒；Y3：+30%且+0.5/秒（同类取最高）" } ] }
              ],
              "prtsUrl": "https://prts.wiki/w/%E5%BD%92%E6%BA%9F%E5%B9%BD%E7%81%B5%E9%B2%A8#天赋"
            }
          ]
        }
      ]
    }
  ]
}
```

> 示例说明：官方类「条件／备注」按 §7 前置工作补录（本示例中 待部署区支援 为策士分支特性，精英 0·1 级即具备，故 `condition` 为「无」；逐条备注待补）；玩家类条件／备注节选自 `agent_workspace/tag_pipeline/player_tags/07-充电.json`；「阵容组合」组合条目节选自 `12-阵容组合.json`（`members` 元素即组合条目，见 §4.2）。
