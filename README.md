# better-combat-operators-selection

明日方舟干员筛选系统的**数据生产线**：从 PRTS wiki 爬取干员语料，按两套 TAG 体系（官方设定 TAG / 玩家体感 TAG）逐干员判定，产出供筛选 UI 直接消费的结构化 JSON。

## 项目提供什么

| 产物 | 内容 |
|---|---|
| `results/operator-tags.json` | 主产物：干员 × TAG × 条件／备注，含职业／分支／势力／实装时间、PRTS 深链与 TAG 说明数据；由独立的筛选 UI 项目消费 |
| `results/combat_glossary.json` | 战斗术语表（由 `docs/glossary.md` 生成） |
| `results/player-tags-criteria.json` | 玩家 TAG 评定标准（悬浮说明＋「查看评定标准详情」抽屉文案，由 `docs/player-tags-criteria.md` 生成） |
| `gui/` | 本地网页版维护面板：荐名单 / 人工归纳（名单与条件备注编辑）/ 结果 JSON 编辑 |
| `docs/` | 判定规范、计算规则、裁定台账、术语表与文档索引 |
| `agent_workspace/` | TAG 判定文件与机读字典（工作区索引见 `agent_workspace/README.md`） |

每一条判定都带证据链：引用 `material_datas/PRTS/` 语料的「文件:行号」，数值口径可复算（`tools/prts_stats.py` + `tools/verify_numbers.py`）。

## 目录结构

```
├── material_datas/PRTS/      # PRTS 语料（每干员一个目录，含召唤物与攻击范围）
├── agent_workspace/          # agent 工作区：TAG 判定文件、机读字典、临时批次、工作稿
│   ├── tag_pipeline/         # official_tags/ + player_tags/ + 字典与 stats.json
│   ├── _out/                 # 临时批次目录（本地）
│   ├── workdocs/             # 《待裁定.md》《待验证复算.md》工作稿（本地）
│   └── handoff/              # 转交状态快照（本地）
├── crawlers/                 # PRTS 爬取与语料剥离
├── tools/                    # 生成与校验工具（含一键全量校验）
├── docs/                     # 规范与文档（索引见 docs/README.md）
├── results/                  # 交付 JSON
├── gui/                      # 维护面板
├── recommend_gui.py          # 面板入口（等价于 python -m gui）
└── start_gui.bat / start_gui.sh   # 一键启动
```

## 快速开始

- 环境：Python 3.11+（开发环境 3.14）。爬虫需要第三方依赖，其余工具与面板仅用标准库。

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows；POSIX 为 .venv/bin/python
```

- 启动维护面板：双击 `start_gui.bat`（Windows）或运行 `./start_gui.sh`；也可直接
  `.venv/Scripts/python.exe -X utf8 recommend_gui.py`（面板只监听本机 127.0.0.1）。
- 常用命令：

```bash
.venv/Scripts/python.exe -X utf8 crawlers/crawl_prts.py --only "干员名"   # 爬取一个干员（含召唤物）
.venv/Scripts/python.exe -X utf8 tools/generate_results.py --check        # 校验并生成结果 JSON
.venv/Scripts/python.exe -X utf8 tools/run_all_checks.py                  # 一键全量校验
```

完整命令与工具清单见 `docs/commands.md`；项目结构与文件权属见 `docs/architecture.md`。

## 本地私有配置

复制 `local.example.json` 为 `local.json`（已被 .gitignore 排除），按需填写：

| 字段 | 说明 |
|---|---|
| `frontend_results_dir` | 消费端存放 `results/` 产物的目录；`tools/sync_results.py` 据此复制产物并核对 md5 |

## 如何贡献

- **一切判定以证据为准**：引用 `material_datas/PRTS/` 下的「文件:行号」；条目写法与产物结构见 `docs/concept.md`、`docs/output-standard.md`。
- 改动 TAG 数据有两条路径：
  1. **直接改**：用维护面板，或手工编辑 `agent_workspace/tag_pipeline/` 下的分文件，然后重跑合并／生成／校验；
  2. **由 agent 作业**：按 `AGENTS.md` §一 的分派表挑开工件，使用 `.claude/skills/` 中的技能（新干员评定、版本增量更新、新增 TAG、评定标准固化、批量回填、复算等）。
- 提交前运行 `tools/run_all_checks.py`，通过后再提交；`agent_workspace/_out/`、`workdocs/`、`local.json` 等本地文件不要提交。

## 文档索引

- 文档总览：`docs/README.md`
- agent 开工分派：`AGENTS.md`；仓库架构与文件权属：`docs/architecture.md`；命令手册：`docs/commands.md`
- agent 资源：`.claude/README.md`
- 贡献流程：`CONTRIBUTING.md`

## 数据来源与许可

代码以 MIT 许可发布（`LICENSE`）。干员数据与游戏文本爬取自 PRTS.wiki，版权归游戏权利人；数据文档与结果 JSON 采用 CC BY-NC-SA 4.0。引用与免责声明详见 `NOTICE.md`。