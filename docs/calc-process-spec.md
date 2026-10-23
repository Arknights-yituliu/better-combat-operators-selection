# 计算过程详情与帧级时间轴规范

> 本文定义「更好的作战干员筛选」详情卡片中**计算过程详情**栏的数据来源、结构与撰写规则。
> 产物：`results/operator-timelines.json`（时间轴）＋ `results/operator-tags.json` 成员上的 `calc` 字段（步骤）。
> 撰写源：`agent_workspace/tag_pipeline/calc_process/<干员>.json`，一干员一文件。
> 工具：`tools/calc_process.py`（`--check` 校验 + 数值对账，`--show <干员>` 展开查看，`--emit` 单独写出）。
> 生成器 `tools/generate_results.py` 会自动读取撰写源、写入 `calc`，并写出时间轴产物。
> **`计算` 块已退役**：源分文件里不再有它，存量已全量删除（历史见 git）；本文件是计算内容的唯一权威源。

## 1. 为什么要单独成一个产物

`operator-tags.json` 首屏就由页面动态 import（列表渲染必需），2.55 MB 已接近可接受上限。帧级事件逐点展开后，73 名干员的量级在数 MB，因此**时间轴单独成文件**，前端只在首次打开带图表的详情弹窗时按需加载。

| 产物 | 内容 | 加载时机 |
|---|---|---|
| `operator-tags.json` | 成员 `calc`：`timeline` 引用、`metric`、分步 `steps` | 首屏 |
| `operator-timelines.json` | `timelines[干员@技能]`：各情形的帧级 `events` | 首次打开含图表的详情 |

## 2. 撰写源结构（`calc_process/<干员>.json`）

```json
{
  "operator": "克莱门莎",
  "timelines": {
    "S3": {
      "fps": 30,
      "scenarios": [
        {
          "id": "normal",
          "name": "普通/精英敌人（元素值 1000）",
          "durationFrames": 2793,
          "panel": 1065,
          "series": [
            { "key": "attack", "group": "主攻击", "label": "主攻击（235%）",
              "damageType": "physical", "colorRole": "physical",
              "pattern": { "type": "periodic", "startFrame": 15, "intervalFrames": 36, "count": 74,
                           "segments": [{ "untilFrame": 87, "damage": 2815.6 }, { "damage": 3128.4 }] } }
          ]
        }
      ]
    }
  },
  "members": [
    { "tag": "P01", "match": "精英2；3技能（专精3数值）", "timeline": "S3", "metric": "damage",
      "scoreNames": { "normal": "普通/精英敌人（元素值 1000）", "leader": "领袖敌人（元素值 2000）" },
      "expected": { "damage": { "normal": 480566, "leader": 542509 } },
      "note": "（显示在「计算过程详情」标题右侧的口径说明）",
      "scenarios": {
        "normal": [ { "section": "① 攻击次数", "title": "…", "expr": "…", "result": "74", "unit": "次", "note": "…" } ]
      } }
  ]
}
```

### 2.1 时间轴（`timelines.<名称>`）

| 字段 | 说明 |
|---|---|
| `fps` | 固定 30 |
| `scenarios[]` | 情形（与 `calc.scenarios` 的 `id` 一一对应） |
| `scenarios[].id` / `name` | `id` 稳定短名（`normal`／`leader`／`wild`…）；`name` 是页面情形按钮文案 |
| `scenarios[].durationFrames` | 演算窗口总帧数；所有事件帧必须落在 `[0, durationFrames]` |
| `scenarios[].panel` | 该情形使用的面板攻击力（供读者核对，不参与绘制） |
| `scenarios[].series[]` | 数据系列，见下 |

**`series[]` 双层命名**（关键约定）：

- `key` 是**数据单元**，`label` 是它的名字；
- `group` 是**图例单位**：同一 `group` 的多条 series 在曲线与图例上合并求和，tooltip 仍按 key 分项。
- 因此逻各斯恰好 **3 个图例**（主攻击／爆发期元素／凋亡持续），但内部有 5 个数据单元。

**图例命名规范**（`--check` 强制）：

| 规则 | 内容 |
|---|---|
| 长度 | `group` ≤ 12 字（含标点），不允许整句 |
| 唯一性 | 同一时间轴内 `group` 不得重复 |
| 风格 | `〈来源〉〈形态〉`：2–6 字为主，如 `主攻击`、`轰炸·物理`、`轰炸·元素`、`侵蚀爆发`、`凋亡持续`、`爆发期元素`、`固定点`；不得写「每次攻击本身造成的…」这类叙述 |
| 完整语义 | 每组**必须**给 `groupDesc`（tooltip 与图例补全用）；同组内可只在首条写 |

`damageType` ∈ `physical` / `art` / `element` / `true` / `fixed`，仅用于 tooltip 标注。

**配色按 `colorRole`（颜色角色）**——先按伤害类型定色，同一张图上同类型的第 2/3 个图例取同色相的变体档位（虚线区分），跨干员保持一致：物理恒为橙、法术恒为紫。`colorRole` ∈ `physical` / `art` / `true` / `weakpoint` / `element` / `apoptosis` / `burn` / `neural` / `erosion`，**必填**，且同一时间轴内同一 `group` 的各条 series 必须同角色（图例才是配色单位）。

`colorRole` 按 series **实际造成的伤害类型**判定，不看它是不是「固定值」或「独立机制」：

| 判定依据 | colorRole |
|---|---|
| `damageType: physical` | `physical` |
| `damageType: art` | `art` |
| `damageType: true` | `true` |
| 伤害类型为弱点伤害（`groupDesc` 写明） | `weakpoint` |
| `damageType: fixed` | 按它实际的伤害类型归类（逻各斯 剜魂具辞是「受到的法术伤害提高 165 点」→ `art`） |
| 元素损伤四类，由图例名区分 | 凋亡 → `apoptosis`、灼燃 → `burn`、侵蚀 → `erosion`、神经 → `neural` |
| 元素伤害但非损伤爆发（如克莱门莎 轰炸·元素） | `element` |

配色表（前端 `CombatCalcDetail.vue` 的 `ROLE_COLORS`，此处只列首档；深色为同色相在深底上的取值）：

| colorRole | 浅色 | 深色 | 语义 |
|---|---|---|---|
| `physical` | `#e0701a` | `#cf7a35` | 物理伤害（橙） |
| `art` | `#7c3aed` | `#a78bfa` | 法术伤害（亮紫） |
| `true` | `#b0248f` | `#e0579f` | 真实伤害（品红） |
| `weakpoint` | `#a07622` | `#c9a94a` | 弱点伤害（暗金） |
| `element` | `#10938a` | `#40c9b8` | 元素伤害（青绿） |
| `apoptosis` | `#8a8a8a` | `#c0c0c0` | 凋亡损伤（灰） |
| `burn` | `#b3202e` | `#d4564a` | 灼燃损伤（赤） |
| `erosion` | `#1f6fd0` | `#5a9ce8` | 侵蚀损伤（蓝） |
| `neural` | `#0f9ba0` | `#45b8bd` | 神经损伤（青） |

同类型第 2/3 个图例取该色相的变体档位（更亮/更暗一档）并画虚线；超过档位数的按最后一档处理。新增色值时用 dataviz 校验器对**同一张图实际出现的组合**做校验（色觉模拟 ΔE ≥ 8、正常视觉 ΔE ≥ 15、对底对比度 ≥ 3:1）。

**事件**在产物里是 `[frame, damage, hits]`；`hits` 为段数（缺省 1）。同一份事件同时支撑「伤害」「段数」两种纵轴，无需重复存储。

### 2.1b 无时间轴的条目

没有 ArkDPS 帧模型的干员，或纯判据型条目（P13 控制时长、P08 增益、P09 保人、P07 充电），**不写 `timeline`**、只写 `steps`。此时：

- 页面不渲染图表区与度量/视图切换，只显示标题 + 分步算式；
- 多情形时**必须**在成员上给 `scenarioNames`（`{ 情形id: 名称 }`），否则页面只能显示 `normal`/`leader` 这类 id（`--check` 会报错）；
- 有 `timeline` 的条目也可以有**超出时间轴的情形**（如 P02 同一条覆盖 2 技能与 3 技能、而时间轴只建了 3 技能）：这些情形同样要写 `scenarioNames`。

### 2.2 `pattern`（撰写侧写法）

产物只认显式 `events`；撰写源可用 pattern 压缩表达，`tools/calc_process.py` 展开：

| type | 字段 | 说明 |
|---|---|---|
| `list` | `events` | 直接列出（状态机输出、爆条时点等无法用公式覆盖的） |
| `periodic` | `startFrame`, `intervalFrames`, `count`, `damage` 或 `segments` | 等间隔 N 次；`segments` 按 `untilFrame` 分段取不同伤害 |
| `periodicInWindows` | `windows`, `intervalFrames`, `countPerWindow`, `damage` | 每个窗口内从起点起周期性结算，至多 `countPerWindow` 次 |
| `windowsPerSecond` | `windows`, `perSecond` | 窗口内每秒 1 次持续点伤；末尾不足 1 秒按比例折算 |

`hits` 可在 pattern 上写（缺省 1）；`damage` 型事件一般 `hits: 0`（不计段）。

### 2.3 成员规则（`members[]`）

| 字段 | 说明 |
|---|---|
| `tag` | `P01`…；用于定位产物里的 TAG |
| `match` | 与清洗后的 `condition` **前缀**比对；同一 TAG 下同干员多条成员时靠它区分。必须**恰好命中 1 条**，否则 `--check` 报错 |
| `timeline` | 本成员的图用哪条时间轴（可跨 TAG 共用，如克莱门莎 P01 与 P02 共用 `S3`） |
| `metric` | 默认纵轴：`damage`（默认）或 `hits`（次数对策） |
| `scenarios` | 情形 id → 步骤数组；情形集合必须与时间轴一致 |
| `scoreNames` | 情形 id → 成绩块情形名（用于自动对账）。成绩块把多情形写在一句里时置 `null` |
| `expected` | 直接写死对账期望：`{ "damage": {sid: N}, "hits": {sid: N} }` |
| `note` | 显示在标题右侧的口径说明 |

### 2.4 步骤（`steps[]`）

| 字段 | 说明 |
|---|---|
| `section` | 分节标题（「部分 1–5」的载体），渲染为小标题，其下步骤重新从 1 编号 |
| `title` | 本步做什么 |
| `expr` | **只放算式**，不得混入自然语言（`--check` 拒绝「按／即／因为／含首击」等词） |
| `result` / `unit` | 结果与单位，与算式分列显示 |
| `note` | **只放注释**：参数来源、口径、口径差异、前提 |

> 这是「算式与注释分离」的落点：读者一眼能顺着算式复算，注释不打断算式。

### 2.5 帧模型登记（`agent_workspace/tag_pipeline/arkdps_frame_model.json`）

复核攻击间隔/次数时，**哪些属性会改变帧模型必须落库**，不得凭记忆：

- **会改变帧模型**：基础攻击间隔、技能的攻击间隔缩短/延长、攻速加成（天赋/潜能/模组/技能/场地）、
  技能持续、弹药/充能/目标数上限。
- **不会改变**：攻击力、伤害倍率、防御、法抗、元素值、损伤类型，以及只加属性不加速度的模组/潜能。
- **换算**：`帧数 = ROUND(秒 × 30)`；`攻击次数 = ROUND(持续秒 × 30 ÷ 帧数)`（含首击）；
  攻速只改变秒数，不改取整规则。
- **基础间隔取游戏数据的精确帧数**：PRTS 面板会四舍五入到 0.1 秒（艾雅法拉精确为 49 帧＝1.6333 秒，
  按 1.6 秒反推会少 1 帧）；有 ArkDPS 时优先采用其详情行的「X秒 (N帧)」。
- **元素损伤爆发期间不可累积**：必须等爆发结束后重新累积；爆发时长按类型——凋亡 15 秒、
  神经 10 秒、灼燃 10 秒、侵蚀按技能/敌人文本。爆条时点与次轮重积按攻击帧对齐（ArkDPS 公式同此）。
- 每个有二维图的干员在登记表里记录：我方帧数/次数、ArkDPS 的 `AttackSpan/AttackCount`、
  是否一致，以及差异原因（攻速来源/模组/条件）。新增或改动时间轴时同步该文件。

复核工具：`tools/frame_check.py`（帧/次数自洽）、`tools/arkdps_replicate.py`（公式复刻与校准）、
`tools/arkdps_report.py`（我方模型 vs 站点公式对账）。

## 3. 撰写流程

1. **定情形**：按成绩块出现的情形建 `scenarios`（普通/精英、领袖、地形分支、高低档……），id 取短名。
2. **算时间轴**：先复用 `_out/` 既有脚本（如 `_klms_final_calc.py` 的 `s3()`、`_manre_calc_v3.py` 的逐帧状态机），确认逐击/爆条时点与总伤。
3. **写 series**：一个伤害来源一条 series；把同属一个图例的 series 填同一个 `group`。
4. **写步骤**：按「面板 → 倍率 → 次数 → 各分流 → 合计」顺序，必要时再拆分节。
5. **对账**：`tools/calc_process.py --check`。它要求 Σ events.damage 与成绩块 `总伤 ≈N` 相差 ≤ 0.5%，Σ hits 与段数一致，且所有事件帧不越界。
6. **生成与同步**：`tools/generate_results.py` → `tools/sync_results.py`。
7. **删除源块**：迁移校验通过后运行 `tools/calc_process.py --strip <TAG> <干员>`，把源单元格里的「计算」块删掉。

> **源单元格里的「计算」块在迁移交付时删除**，不再保留。守恒审计已同步收窄（两侧都先剥掉 `计算` 块再比对），删除不会触发「数字丢失」；
> 数字守恒改由 `tools/calc_process.py --check` 以 **git 历史**为基准守住——它取 `HEAD` 侧的原文，比对 `steps`/`events` 是否覆盖了每个数字。

## 4. 样板算例

### 4.1 逻各斯 · P01 决战歼灭

- 面板 855＝671＋90＋27＋67；技能期攻击力 3420＝855×(1+300%)；19 下＝round(30÷1.6)（含首击）。
- 凋亡累积 401.4 点/击＝286.8（主伤害 8%×(3420+165)）＋114.6（法术附加 60%×8%×(3420×65%+165)）。
- 普通/精英 1000 元素值：第 3 击（t=3.2 s）爆条，15 秒爆发；爆发结束重置后第 3 击（t=22.4 s）再爆，覆盖到技能结束 7.6 秒。
- 领袖 2000：第 5 击（t=6.4 s）爆条，覆盖 15 秒；次轮自 t=28.8 s 起、仅 1.2 秒。
- 分项（普通/精英）：主攻击 64980＋法术附加 25342.2＋爆发期元素附加 18468＋凋亡持续 18080＋剜魂具辞固定点 5016＝**131886**（产物 131886）。
- 领袖：64980＋25342.2＋12312（10 击×60%）＋12960＋5016＝**120610**（产物 120610）。

### 4.2 克莱门莎 · P01 3 技能 / P02 次数对策

- 首击 t=0.5 s（帧 15），间隔 36 帧；10 发弹药打完。
- 普通/精英：74 击，首爆 t=1.7 s（第 2 击，触发击按爆发前档），此后 72 击按 ×1.25；10 轮爆条。
-  bombard：每发 3 次结算，每次 1065×300%×1.25＋1065×250%＝6656.25；10 发＝199687.5。
- 爆条：10×5000＝50000。
- 攻击：2×2815.6＋72×3128.4＝230878.8；合计 **480566.3**（产物 480566）。
- 领袖：94 击、首爆前 4 击；攻击 4×2815.6＋90×3128.4＝292821.6，合计 **542509.1**（产物 542509）。
- P02：攻击 74＋轰炸 30＋爆发 10＝**114 段**（88.13 秒，1.3 段/秒）；领袖 94＋30＋10＝**134 段**。

## 5. 前端渲染（消费端）

`src/components/tools/CombatCalcDetail.vue`，在详情弹窗每条成员备注之后渲染：

- 容器：左边框 `3px solid rgb(var(--v-theme-primary))`、**无圆角**、标题主色（与成绩块同族）；
- 情形 chips（>1 个情形时；无图条目取 `calc.scenarios[].name`）；
- 图表：ECharts（全局 CDN），横轴帧数；「伤害 / 攻击段数」×「累计伤害 / 单次伤害」（段数模式为「累计段数 / 单次段数」）两组切换；纵轴不写单位；图例为短名 `group`、tooltip 补全 `groupDesc`；**配色按 `colorRole`**（同类型多图例取同色相变体档位 + 虚线，见 §2.1）；
- 步骤：按 `section` 分组，`expr` 用等宽字体、`result` 主色高亮、`note` 小字灰色。

## 6. 迁移状态与流程

- **已完成全量迁移**：全部计算块已迁入本目录，源分文件里的 `计算` 块已删除。
- 后续按干员增量维护：改 `calc_process/<干员>.json` → `tools/calc_process.py --check` → `tools/generate_results.py` → `tools/sync_results.py`。
- 无 ArkDPS 帧模型的条目只写 `steps`、省略 `timeline`（不出图），多情形必须给 `scenarioNames`。
- 前端 `renderRemark` 的 `calc` 分支已删除（`计算` 块不再渲染）。
