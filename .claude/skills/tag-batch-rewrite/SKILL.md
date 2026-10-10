---
name: tag-batch-rewrite
description: 批量改写／复算 TAG 条目的回填与守恒审计流程。Use when a batch of tag-rewrite outputs (agent_workspace/_out/<批名>.json) must be applied back to the part files, or after any 条件/备注 rearrangement when 数字/依据 conservation must be verified. 触发词：回填、批次回填、_apply_batch、apply_ops、audit_text_migration、守恒审计。
---

# 批量回填与守恒审计（tag-batch-rewrite）

## 何时用

- 已派出 `tag-rewrite` 子代理，产出了一批 `agent_workspace/_out/<批名>.json`，需要写回分文件；
- 任何「条件／备注」重排之后，需要核对数字、依据与结构守恒。

扫描类的整批作业先读 `docs/scan-protocol.md`（名单文件＋逐人决断＋复核代理），通过复核后才允许回填。

## 回填：`_apply_batch.py`

```bash
# 先 dry-run 核对全部键命中
.venv/Scripts/python.exe -X utf8 .claude/skills/tag-batch-rewrite/scripts/_apply_batch.py \
    --tag P03 --file 03-吃拐一轮秒.json --out agent_workspace/_out/P03-A.json --dry-run
```

- 产出 JSON 的键＝干员名；同一分文件内同名多行时写成 `干员名（子表名）`。
- 脚本按「干员」列名**结构化定位**行、只设「条件」「备注」两个字段；其余字段（编号/子 TAG/范围/依据）原样保留。同名多行（01 真言、02 两子表同名干员等）取文档序最后一处，键写 `干员（子表名）` 可对块标题消歧。
- `--keep-prefix` 从当前行取出并保留行首机器协议前缀（插拔容错的 `救急路径：`、`子 TAG：`）；不带则整批丢子 TAG。
- `_apply_batch` 不增删成员行；**插行／改依据／正文行替换与插入／新建子表**改用 `scripts/apply_ops.py`（输入 JSON 五类操作，默认 dry-run、逐条断言；先 `--dry-run` 再 `--write`；`--root` 可指向副本做冒烟）——勿再手写一次性回填脚本。
- 脚本读工作区文件时按实际换行处理，输出沿用原文件的换行风格。

## 守恒审计：`audit_text_migration.py`

```bash
.venv/Scripts/python.exe -X utf8 .claude/skills/tag-batch-rewrite/scripts/audit_text_migration.py            # 全部成员表
.venv/Scripts/python.exe -X utf8 .claude/skills/tag-batch-rewrite/scripts/audit_text_migration.py --only 01  # 只审某个分文件
```

- 对比 HEAD 与工作区：报「数字丢失／依据丢失／残留禁用／块标签未点名／结构未生成」，均应 0。
- 有意改动的数字必须登记脚本内 `ACCEPTED`（键＝`文件名｜干员`，值＝放行令牌＋理由）；每加一条即一次显式裁定，同名键需合并而非重复。

## 相关

- 子代理类型：`.claude/agents/tag-rewrite`（产出 `agent_workspace/_out/*.json`，不直接改分文件）。
- 条目写法：`docs/concept.md`（条件分条／备注分块）；判据：各分文件的「评定标准」与 `docs/rulings.md`。