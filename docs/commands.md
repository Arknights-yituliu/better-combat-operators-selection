# 命令手册

> 用途：本仓库全部常用命令与参数。开工时**不必读本文**——按 `AGENTS.md` §一 取开工件；本文是执行阶段的查阅件。
> 统一约定：Windows 下用 `.venv/Scripts/python.exe`（POSIX 用 `.venv/bin/python`），**一律带 `-X utf8`**——控制台是 GBK，中文直出会乱码。

## 一、爬取与语料

```bash
# 爬取一名或多名干员（含召唤物）；可断点续爬、限速
.venv/Scripts/python.exe -X utf8 crawlers/crawl_prts.py --only "干员名"
#   新干员？先往 docs/operators.txt 加一行：  干员名 https://prts.wiki/w/干员名
#   参数：--force（连已成功的也重爬）、--delay-min/--delay-max、--operators-file、--out-dir
#   写出前会跑 strip_noncombat()，落盘语料不含剧情／养成内容

# 爬取攻击范围（按精英化阶段 / 技能 / 召唤物）到各干员目录；可断点续爬
.venv/Scripts/python.exe -X utf8 crawlers/crawl_ranges.py            # --only 干员名 / --force

# 刷新 PRTS《特殊机制》快照与规范化条目（联网；限速）
.venv/Scripts/python.exe -X utf8 crawlers/crawl_special_mechanics.py  # --emit / --apply（追加术语章节）/ --input
```

## 二、证据层与守恒审计

```bash
# 核对证据层：全仓库 文件:行号 是否仍指向剥离前的原文（剥离或改行号后必跑）
.venv/Scripts/python.exe -X utf8 crawlers/strip_prts_noncombat.py --audit   # --fix-stale 补正
#   --dry-run 先看改动与冲突

# 核对条件/备注重排：对比 HEAD，查重排行是否丢数字、丢依据、留禁用符号（改过分文件后必跑）
#   有意改动的数字登记在脚本内的 ACCEPTED（键＝文件名｜干员，值＝放行令牌＋理由）
.venv/Scripts/python.exe -X utf8 .claude/skills/tag-batch-rewrite/scripts/audit_text_migration.py   # --only 01 只审某文件
```

## 三、批次回填

```bash
# 把 agent_workspace/_out/<批名>.json（tag-rewrite 子代理的产出，键＝干员名）写回分文件
#   按表头定位列、以 HEAD 重建整行，只替换「条件」「备注」两格；行首机器协议前缀用 --keep-prefix 保留
.venv/Scripts/python.exe -X utf8 .claude/skills/tag-batch-rewrite/scripts/_apply_batch.py --tag P03 --file 03-吃拐一轮秒.json --out agent_workspace/_out/P03-A.json
```

插行／改依据／正文行替换与插入／新建子表 → 用 `.claude/skills/tag-batch-rewrite/scripts/apply_ops.py`（先 `--dry-run`）。

## 四、属性层与数值校准

```bash
# PRTS 语料 → 机读属性层（属性/信赖/潜能/模组档位固定属性）→ agent_workspace/tag_pipeline/stats.json
.venv/Scripts/python.exe -X utf8 tools/prts_stats.py
#   --check 只报覆盖率；--panel 干员 --stage e2 --pot 4 --module Δ --tier 3 复算面板与组成式

# 产物数值校准：面板是否与条件声明的档位相符、模组档位是否取满、恒等式、内部代号、因子覆盖
.venv/Scripts/python.exe -X utf8 tools/verify_numbers.py
#   --only P01 只查某 TAG；--coverage 只看因子覆盖清单
```

## 五、产物链（合并 → 生成 → 校验 → 同步）

```bash
# 改完玩家 TAG 分文件后，重生成合并文档
.venv/Scripts/python.exe -X utf8 agent_workspace/tag_pipeline/player_tags/_merge_to_docs.py
# 官方 TAG 结构性变更（增／改名／合并 TAG、成员改动）后，重生成合并文档与机读字典
.venv/Scripts/python.exe -X utf8 agent_workspace/tag_pipeline/official_tags/_merge_official_to_docs.py --sync-dicts

# 由玩家 TAG 评定标准源文档重生成前端抽屉文案 JSON
.venv/Scripts/python.exe -X utf8 tools/criteria_to_json.py        # --check 只校验；--accept 放行分文件指纹

# 由两份成员文档生成最终结果 JSON（规范：docs/output-standard.md）
.venv/Scripts/python.exe -X utf8 tools/generate_results.py          # --check / --report
#   写出 results/operator-tags.json；--check 只按规范校验、不写盘
#   生成时在内存里套用 tag_order.json 的顺序，重新生成不会打乱展示序
#   同时由 agent_workspace/tag_pipeline/calc_process/ 写出 results/operator-timelines.json

# 单独校验计算过程详情撰写源（规范：docs/calc-process-spec.md）
.venv/Scripts/python.exe -X utf8 tools/calc_process.py --check      # --show 干员 / --emit
#   数值对账：每个情形的 Σ事件伤害必须与成绩块的「总伤」相符（±0.5%）

# 由 docs/glossary.md 重生成战斗术语 JSON（内含镜像核对）
.venv/Scripts/python.exe -X utf8 tools/glossary_to_json.py

# 把 results/ 下的产物同步到消费端目录（路径取自仓库根目录 local.json 的 frontend_results_dir）
.venv/Scripts/python.exe -X utf8 tools/sync_results.py              # --check 只比对 md5
```

**成员变化时须递增 `tools/generate_results.py` 里的 `VERSION`**（同步更新 `docs/untagged-operators.md`）。**顺序变化不升版**，只更新 `updated`。

## 六、排序层

```bash
# 把两处 results 产物重排成 tag_order.json 里的顺序（只重排、不重生成）
.venv/Scripts/python.exe -X utf8 tools/apply_tag_order.py           # 套用；无变化则不写盘（幂等）
.venv/Scripts/python.exe -X utf8 tools/apply_tag_order.py --check   # 一致性校验（run_all_checks 的「排序层校验」用它）
.venv/Scripts/python.exe -X utf8 tools/apply_tag_order.py --seed    # 把产物有、顺序文件没登记的项补到各段末尾（--rebuild 整体重建）
```

## 七、荐（推荐干员）

```bash
# 维护玩家 TAG 的荐；数据文件 player_tags/_recommend.json
.venv/Scripts/python.exe -X utf8 tools/recommend.py list|add|remove|check   # 例：tools/recommend.py add 充电 白铁
```

## 八、维护面板（本地网页版）

四个页签：**「荐」**＝荐的增删（详情＝信息卡＋右栏只读的条件／备注）；**「人工归纳」**＝从某 TAG 里挑出干员（扩展／移动／移除）进暂存区、折进目标子表、编辑条件／备注（写回 `player_tags/NN-*.json` 与 `official_tags/[A-I]-*.json`，并重算官方条目头）；**「TAG 排序」**＝拖拽 TAG／子 TAG 取值成展示序，保存在 `agent_workspace/tag_pipeline/tag_order.json`，保存时把顺序投影到两处产物（只改 `updated`、不动 `version`）；**「结果 JSON」**＝把 `results/*.json` 载入内存（或从规范骨架开始），用结构化卡片＋原始源码视图编辑，再以「覆盖已有文件／新建自定义文件名」保存——**不保存就不落盘**，按 `docs/output-standard.md` 的校验只提醒、不阻断；保存时先按 `tag_order.json` 重排、再按 `_recommend.json`／`_recommend_fallback.json` 重算各玩家 TAG 的荐字段（面板内荐只读）。

```bash
.venv/Scripts/python.exe -X utf8 recommend_gui.py                    # --port / --no-browser / --check
.venv/Scripts/python.exe -X utf8 -m gui                              # 同上（实现都在 gui/ 包内）
```

用法细则见 `gui/README.md`。

## 九、模组与术语

```bash
# 解析 docs/temp.txt（PRTS《模组》页快照）→ 模组隐藏机制汇编 docs/module-hidden-mechanics.md
.venv/Scripts/python.exe -X utf8 tools/module_notes.py            # --list 只看统计；--emit 写出
```

## 十、一键全量校验

```bash
# 十项：属性层覆盖率 / 数值校准 / 生成规范与文本 lint / 计算过程详情 / 排序层 /
#       评定标准严谨版 / 迁移守恒 / 证据层审计 / GUI 自检 / 文档一致性
# 实际清单以 tools/run_all_checks.py 的 CHECKS 为准
.venv/Scripts/python.exe -X utf8 tools/run_all_checks.py
```

文档一致性单独跑：`.venv/Scripts/python.exe -X utf8 tools/doc_consistency.py`（`--list` 列出当前检查项）。

## 十一、网络与控制的注意事项

- PRTS 需要**完整浏览器请求头**（UA + Accept + Accept-Language + Referer）并限速（默认 1.2–2.8 秒／请求），**不要**紧循环爬取。爬虫内部与清洗坑位见 `.claude/skills/crawl-prts-operator/SKILL.md` 与 `docs/crawling-and-strip.md`。
