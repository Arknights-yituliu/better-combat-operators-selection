---
name: add-official-tag
description: 给本项目新增一个官方设定 TAG（A–I 类）。当开发者说想 新增/添加 一个官方设定 TAG、按 PRTS《异常效果》《术语释义》词条开设新条目、或扩展官方 TAG 体系时使用（触发词：新增官方TAG、官方设定tag、新官方条目、add official tag）。与 add-player-tag 相对：官方类不涉成绩计算，判据取自 PRTS 官方词条。
---

# 新增一个官方设定 TAG

> 官方 TAG 的权威源是 `agent_workspace/tag_pipeline/official_tags/[A-I]-*.json`（tag-part/1，`kind:"official"`）；
> 玩家 TAG 走 `.claude/skills/add-player-tag/SKILL.md`。区分：官方类判「PRTS 官方词条／分支文本里点名的机制」，
> 不写成绩、不做数值演算（`docs/classification-conventions.md` 第 16 行）。

## 第 0 条 —— 先定评定标准，再动成员

同 `add-player-tag` 的第 0 条：纳入、排除、有无子 TAG、与既有 TAG 的关系四点必须没有歧义。
判据必须锚在 **PRTS 官方词条**（《异常效果》43 条、《术语释义》ba.* 词条、分支职业文本），
不能自拟；只有「文案里出现该机制名」才算，等效机制（语义相同但无该词）按铁律「名称≠机制」的反向读法**不收**，
否则会与既有 TAG 大量重复。

**判断「是否已有 TAG 承接」的方法**：遍历 `official_tags/*.json` 的全部 `entries[].name` 与 `rest`，
按「效果本体」与「施加行为」两轴各查一遍——很多新机制只是既有条目的**另一个轴**（例：屏障 vs 施加触发型效果）。

## 步骤

### 1. 选模块与 id

- 模块按 `docs/official-tags-members.md` §3 的九个类别；跨方向的条目按「成员多数所在方向」选，
  并在 `rest` 首句写明「方向不限」。
- id 形如 `A_trigger`（`gui/results_json.py` 校验 `^[A-I]_[a-z0-9_]+$`），**发布后不得复用或更改**。

### 2. 写分模块条目（`official_tags/[A-I]-*.json`）

```json
{ "format": "tag-part/1", "kind": "official",
  "entries": [
    { "name": "施加触发型效果",
      "rest": "一句话定义（官方术语：…）",
      "items": [
        { "t": "p", "lines": ["", "> 备注：纳入／排除／子 TAG／与其它 TAG 的关系", ""] },
        { "t": "table", "columns": ["干员", "编号", "条件", "备注"],
          "rows": [["冻河", "char_4244_tocka", "1技能／2技能／3技能", "子 TAG：对友方、受击时。…"]] },
        { "t": "p", "lines": [""] } ] } ],
  "trailing_newlines": 1 }
```

硬约束（`agent_workspace/tag_pipeline/partdoc.py`）：每条目**恰 1 张表**、列头逐字 `["干员","编号","条件","备注"]`、
单元格单行且不含 `|`、`rest` 非空、成员按实装时间倒序。**成员表行按 `_launch_dates.json` 倒序插入**。

### 3. 登记三处

| 文件 | 加什么 |
|---|---|
| `agent_workspace/tag_pipeline/catalog.json` | `{id, cat, name, keys, rule, dims, note}`；`name` 必须与条目名逐字一致；`version` +1 |
| `agent_workspace/tag_pipeline/tag_order.json` | 所属类别 `tags[]` 末尾追加 `{id, name}` |
| `tools/generate_results.py` | `OFFICIAL_SUB_GROUPS` 加该 TAG 的子 TAG 组与取值闭集；`VERSION` +1 |

### 4. 生成与校验

```bash
.venv/Scripts/python.exe -X utf8 agent_workspace/tag_pipeline/official_tags/_merge_official_to_docs.py
.venv/Scripts/python.exe -X utf8 tools/generate_results.py --check
.venv/Scripts/python.exe -X utf8 tools/generate_results.py
.venv/Scripts/python.exe -X utf8 tools/apply_tag_order.py --check
.venv/Scripts/python.exe -X utf8 tools/run_all_checks.py
```

`§3 总览`、`§4 成员表`、`§5 时间线` 与头部总数由合并脚本重算；**`§7 附录 A`、`§8 附录 B` 需手改**
（脚本不管这两节——新词条补进 §8.2／§8.4，若该机制原在 §7「无持有者」名单中则移出）。

### 5. 留痕

- `docs/rulings.md` 新增一节并在顶部节级目录补一行。
- 若改动了其它文档里的 TAG 总数（如 `docs/output-standard.md`），同步更新。

## 禁止

- 不得凭模型记忆判定——每条成员引 `material_datas/PRTS/` 的 `文件:行号`。
- 不得往评定标准写日期、轮次或编辑痕迹（`docs/classification-conventions.md` 第 54 行）。
- 不得为凑成员而放宽「名称≠机制」：原文无该机制名的等效效果不收。
- 模式限定模组（ISW-α／RA-α 等）对官方 TAG **不计**（`docs/official-tags-members.md` §1 铁律⑤）。
