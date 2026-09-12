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
5. 新干员实装并进入任一 TAG 成员表。

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

**不得进入本文件的内容**：评定标准（含判定规则、口径说明、定义句）、`文件:行号` 证据、边界与排除记录、待开发者确认项、检索记录。这些只属于生产文档；UI 侧不需要，也不应出现在结果 JSON 中。

## 3. 干员基本信息（operators）

一张信息卡片中**与 TAG 无关、固定不变**的部分；只存一份，成员表通过「干员名」引用（避免同一干员在多 TAG 下重复存储而不一致）。

```json
{
  "name": "白铁",
  "rarity": 5,
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
| rarity | int | 稀有度 1–6 |
| class | string | 职业（先锋／近卫／狙击／重装／医疗／辅助／术师／特种） |
| branch | string | 分支（如 工匠、策士、处决者） |
| faction | string | 势力：取 PRTS「属性」表「所属势力」；为空时取「隐藏势力」；均无时取 `""` |
| releaseDate | string | 实装时间 `yyyy-MM-dd`（PRTS「获得方式」表的上线时间） |
| prtsUrl | string | 干员主页 URL（干员名 percent 编码，不带锚点） |

- 数据来源：`material_datas/PRTS/<干员>/<干员>.md`（稀有度·职业＝干员信息；分支＝特性表；势力＝属性表；实装时间＝获得方式表；实装时间缓存见 `material_datas/tag_pipeline/player_tags/_launch_dates.json`）。
- 数组顺序按实装时间倒序；UI 不应依赖该顺序。

## 4. TAG 与成员

### 4.1 TAG 条目

```json
{
  "id": "D_zone",
  "name": "待部署区支援（策士）",
  "source": "official",
  "category": "D 部署与编队",
  "members": []
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 稳定标识。官方类＝TAG 字典 id（`A_stun`、`D_zone`…）；玩家类＝`P01`–`P13`（与 `material_datas/tag_pipeline/player_tags/NN-*.md` 编号一致）。**一经发布不得复用或更改**；TAG 改名时保留原 id |
| name | string | 是 | TAG 名称（与名单文档一致，如 `阻挡数5`、`待部署区支援（策士）`） |
| source | string | 是 | `"official"`（官方设定类）或 `"player"`（玩家体感类）；UI 可分源筛选、可互相引用 |
| category | string | 官方类必填 | 类别名：`A 控制·异常`、`B 伤害类型`、`C 生存与增益`、`D 部署与编队`、`E 技力与技能资源`、`F 治疗与支援`、`G 召唤物`、`H 攻击行为特征`、`I 全场光环`（取自 `docs/official-tags-members.md` §3 总览，省略括号补充） |
| recommended | array | 仅玩家类 | **荐**名单（§6）：元素为干员名，数组顺序即展示优先级；无荐时为空数组 `[]`。官方类省略该字段 |
| members | array | 是 | 成员（TAG×干员关系），见 4.2 |

- 排序：`tags` 数组顺序＝UI 展示顺序——官方类按 `docs/official-tags-members.md` §4 顺序（A→I），玩家类按 P01→P13（决战歼灭、次数对策、吃拐一轮秒、远程消耗、插拔容错、初动、充电、拐杖、保人、抗削弱、大力推拉、阻挡数5、阵容组合）。
- 官方类 id 以 TAG 字典（`material_datas/tag_pipeline/catalog.json`）为准；字典与 80 个 TAG 尚未完全对齐（已含 B-造成百分比伤害；仍缺 待部署区支援、全场光环 等，见 §7），生成前先补齐。

### 4.2 成员（TAG×干员关系）

```json
{
  "operator": "林",
  "condition": "精英1；2技能（专三）",
  "remark": "2技能：25秒内使攻击范围内所有友方单位享受第一天赋效果——每个干员单独获得可抵挡所有伤害的琉璃璧、单独计算破碎与恢复",
  "subTags": ["屏障·护盾"],
  "prtsUrl": "https://prts.wiki/w/%E6%9E%97#技能"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| operator | string | 是 | 干员名，指向 `operators[].name` |
| condition | string | 是 | **硬性达成条件**（精英化／技能／专精／模组与等级／模式限定／目标限制）；精英 0·1 级即具备者写 `"无"` |
| remark | string | 否 | **信息加工后的备注**（数值、持续时间、隐藏机制、特殊用法、战术帮助）；无内容时省略该字段 |
| subTags | array | 否 | 子 TAG／分组（可被筛选），见 4.3；无分组时省略 |
| prtsUrl | string | 是 | 该 TAG 下点击卡片的 PRTS 跳转地址，见 §5 |

- 同一干员可属多个 TAG（多对多，属其他 TAG 不构成排除理由）；**同一 TAG 内 `operator` 不重复**。
- 条件／备注的写法沿用 `docs/player-tags-members.md` §0「通用评定标准」：条件写硬性要求，备注写加工后的信息，不写游戏内一眼可见的内容。
- 成员顺序＝名单文档顺序（实装时间倒序；同实装日按拼音序），UI 默认按此顺序展示；**UI 提供实装时间正序／倒序切换**——排序键取该干员的 `operators[].releaseDate`（§3），同日成员保持文档内相对次序、不随切换倒转。
- 「阵容组合」先按组合分组、组合内成员再按实装时间排序（切换同理）；其成员为**提供者**（组合内受益者、成队人数、计数池等为展示性信息，见 §8 待定）。

### 4.3 子 TAG（subTags）

子 TAG 用于区分同一 TAG 下的实现方式、数值类型、生效范围等，同样可被筛选（`docs/player-tags-specify.md` 要求）。取值直接使用各分文件成员表的分组：

| 玩家 TAG | subTags 取值 | 来源 |
|---|---|---|
| 吃拐一轮秒 | `聚爆`、`连射` | 分文件「子 TAG」列（两值可并存） |
| 次数对策 | `多段伤害`、`间隔伤害` | 分文件两张子表 |
| 远程消耗 | `打击范围越界与周期全场打击`、`远程部署型召唤物与装置`、`全场触发式伤害` | 分文件表 1／2／3 |
| 拐杖 | 增益类型＋生效方式两组，如 `["攻击力(加算)", "在场"]` | 分文件「子 TAG」列 |
| 保人 | `减免·防御·法抗·庇护`、`屏障·护盾`、`闪避·迷彩`、`抵抗`、`元素损伤防护`、`免死·锁血·伤害转移`、`嘲讽·吸引火力·指定承伤` | 分文件七张子表 |
| 抗削弱 | `下限保护`、`上限提高` | 分文件两张子表 |
| 阵容组合 | 组合名，如 `["深海猎人"]` | 分文件 §A 各组合 |

- 官方类的子 TAG（如 全场光环 的 `伤害光环`／`削弱光环`／`增益光环`／`治疗光环`／`增伤光环`）同样写入本字段。
- 一条关系可带多个子 TAG；其余 TAG 无分组，省略 `subTags`。

## 5. PRTS 跳转地址

点击某 TAG 下的干员卡片时，打开该关系上的 `prtsUrl`。

- **地址构成**：`https://prts.wiki/w/` ＋ 干员名（UTF-8 percent 编码，大写十六进制）＋ 可选锚点。
- **锚点取该 TAG 能力在干员页中的位置**：只有当该能力**只来自一个章节**时才加锚点；跨章节或由干员整体机制构成时落到干员主页（无锚点）。

| 该 TAG 能力来源 | 锚点 | 示例 |
|---|---|---|
| 仅技能（含技能自带的装置／召唤物） | `#技能` | 白铁·充电（仅 2 技能）→ `https://prts.wiki/w/%E7%99%BD%E9%93%81#技能` |
| 仅天赋（模组只做强化时仍算天赋） | `#天赋` | 陈·充电（天赋「呵斥」，X 模组仅强化） |
| 仅模组（能力本身由模组追加） | `#模组` | 归溟幽灵鲨·充电（技力回复由 Y 模组 2 级追加） |
| 仅召唤物／装置（常驻，不随技能） | `#召唤物信息` | 官方「拥有召唤物」类 TAG → 干员页「召唤物信息」段 |
| 跨两类及以上，或无法确定唯一来源 | 无锚点（干员主页） | 凛御银灰·官方「待部署区支援（策士）」：天赋与技能均可支援待部署区 → `https://prts.wiki/w/%E5%87%9B%E5%BE%A1%E9%93%B6%E7%81%B0` |

- 锚点用 PRTS 章节名原文（如 `#技能`），浏览器会自动编码，与 `#%E6%8A%80%E8%83%BD` 等价。
- 锚点按「能力来源」判定，来源以该关系的「条件／备注」文本为准；判定不确定时一律用干员主页（宁可不锚定，不可跳错）。

## 6. 荐（recommended）

- **定义**：人工指定的「该 TAG 下推荐用」干员名单，用于 UI 在该 TAG 下优先展示／加推荐角标。一个干员可以只在部分 TAG 下有荐（在 A TAG 有、B TAG 没有）。
- **位置**：玩家体感 TAG 的 `recommended` 字段（官方类 TAG 暂无此字段）；数组顺序即展示优先级，无荐时为空数组。
- **约束**：荐必须是该 TAG 的成员；同一 TAG 内不重复（由工具强制校验，避免笔误产生悬空引用）。
- **维护工具**：`recommend.py`（命令行），源文件 `material_datas/tag_pipeline/player_tags/_recommend.json`。

```bash
python recommend.py                     # 列出 13 个玩家 TAG 及当前荐数量
python recommend.py list 充电           # 查看「充电」的荐（按优先级）
python recommend.py add 充电 白铁       # 添加荐（可一次多个；--first 置顶）
python recommend.py remove 充电 白铁    # 移除荐
python recommend.py check               # 校验荐名单（TAG／成员是否仍然有效）
```

- 荐只维护在 `_recommend.json`（不写进名单文档）；生成结果 JSON 时按 TAG 名合并进 `recommended` 字段，重新生成不会丢失。
- 调整优先级＝`add --first` 置顶，或手改 `_recommend.json` 中数组顺序（数组顺序即优先级）。

## 7. 数据来源、生成与发布

| JSON 部分 | 来源 |
|---|---|
| `operators` | `material_datas/PRTS/<干员>/<干员>.md`（含 `_launch_dates.json` 的实装时间） |
| 官方类 `tags` | `docs/official-tags-members.md`（80 个 TAG 名单）＋ TAG 字典 `material_datas/tag_pipeline/{catalog.json, merged.json, final_lists.tsv}` |
| 玩家类 `tags` | `docs/player-tags-members.md`（由其分文件 `material_datas/tag_pipeline/player_tags/NN-*.md` 合并生成） |
| `recommended` | `material_datas/tag_pipeline/player_tags/_recommend.json`（`recommend.py` 维护） |
| `prtsUrl` | 按 §5 规则生成（干员名编码＋锚点） |

**发布前置工作**（首次生成 v1 前需完成）：

1. **官方类逐条「条件／备注」尚未产出**——`docs/official-tags-members.md` 目前只有名单；需按该文件 §9 的流程（以 `material_datas/PRTS/` 原文为证据）为 1000 条官方 TAG×干员关系补录 `condition`／`remark`。
2. **官方 TAG 字典需与 80 个 TAG 对齐**——`catalog.json` 已含补录的 `B_percent`（造成百分比伤害），但仍缺 `A_mortalwound`（施加死亡宣告）、`D_zone`（待部署区支援）、`H_liftoff`（起飞/空中作战）等 id，且无「全场光环」条目；`merged.json` 尚未并入全场光环（961 条关系，缺 I 类 22 条）。生成前先补全 id 并统一三份文件。
3. 生成脚本尚未编写（本规范为其接口契约）。

发布流程：生成 `results/operator-tags.json` → 核对 `version`／`updated` 与抽查若干干员卡片 → 复制到 UI 项目。

## 8. 待定与扩展

1. 「阵容组合」组合级元数据（成队人数、计数池、组合内受益者等，见 `material_datas/tag_pipeline/player_tags/13-阵容组合.md` §数据结构建议）是否进入 JSON、以何种结构进入，待开发者确定；当前只保证 `subTags` 带组合名、成员为提供者。
2. 官方 TAG 家族关系（如 造成元素损伤 顶层与四个子系）是否需加 `parent` 字段；当前各自为独立 TAG，层级只记录在文档中。
3. 官方类 TAG 是否也需要「荐」；如需要，扩展方式与玩家类相同。
4. 干员基本信息是否补充其他字段（如 获取方式、阵营标签）由 UI 需求决定，新增即需升版本。

## 9. 完整示例（节选）

```json
{
  "version": "v1",
  "updated": "2026-09-12",
  "operators": [
    {
      "name": "凛御银灰",
      "rarity": 5,
      "class": "先锋",
      "branch": "策士",
      "faction": "谢拉格",
      "releaseDate": "2025-11-01",
      "prtsUrl": "https://prts.wiki/w/%E5%87%9B%E5%BE%A1%E9%93%B6%E7%81%B0"
    },
    {
      "name": "松桐",
      "rarity": 4,
      "class": "先锋",
      "branch": "策士",
      "faction": "东",
      "releaseDate": "2025-08-02",
      "prtsUrl": "https://prts.wiki/w/%E6%9D%BE%E6%A1%90"
    },
    {
      "name": "白铁",
      "rarity": 5,
      "class": "辅助",
      "branch": "工匠",
      "faction": "维多利亚",
      "releaseDate": "2022-10-11",
      "prtsUrl": "https://prts.wiki/w/%E7%99%BD%E9%93%81"
    },
    {
      "name": "归溟幽灵鲨",
      "rarity": 5,
      "class": "特种",
      "branch": "傀儡师",
      "faction": "阿戈尔",
      "releaseDate": "2022-05-01",
      "prtsUrl": "https://prts.wiki/w/%E5%BD%92%E6%BA%9F%E5%B9%BD%E7%81%B5%E9%B2%A8"
    }
  ],
  "tags": [
    {
      "id": "D_zone",
      "name": "待部署区支援（策士）",
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
      "members": [
        {
          "operator": "白铁",
          "condition": "精英1；2技能（高效补给）；由支援装置对范围内一名我方干员生效",
          "remark": "装置型：装置使一名我方干员每 3.5 秒获得 1 点技力；技能期间装置强化为每 3 秒/2.5 秒/2 秒获得 1 点，但装置生命流失翻倍；技能结束装置销毁；装置效果可叠加",
          "prtsUrl": "https://prts.wiki/w/%E7%99%BD%E9%93%81#技能"
        },
        {
          "operator": "归溟幽灵鲨",
          "condition": "精英2；Y模组2级（3级更强）；仅【深海猎人】；编入队伍时（不需在场）",
          "remark": "光环型（阿戈尔的深邃）：编入队伍时所有【深海猎人】干员技力自然回复速度+0.3/秒(Y2)、+0.5/秒(Y3)；同类效果取最高",
          "prtsUrl": "https://prts.wiki/w/%E5%BD%92%E6%BA%9F%E5%B9%BD%E7%81%B5%E9%B2%A8#模组"
        }
      ]
    }
  ]
}
```

> 示例说明：官方类「条件／备注」按 §7 前置工作补录（本示例中 待部署区支援 为策士分支特性，精英 0·1 级即具备，故 `condition` 为「无」；逐条备注待补）；玩家类条件／备注节选自 `material_datas/tag_pipeline/player_tags/07-充电.md`。
