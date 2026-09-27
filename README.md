# 知识库建设流水线 · 最终方案（v3 定稿）

> 自 v2 起的变更：解耦为独立 pipeline repo；固化六条协作纪律；纪律 2 完整性校验钉死为 fail-fast；CI 升格首轮必做并要求先空跑自验证。本文即 pipeline repo 的 README。

## 0. 总览

把教材 PDF、课标 PDF、Obsidian 笔记，逐章加工成 skill repo 已定义的格式资产。**格式由代码保证，人只做教学判断**。双 repo 职责：本仓库（私有）承载工具、契约、唯一真相源；`high-school-ai-tutor-skill`（公开）只收代码与策展后生成物。版权姿态：PDF 衍生物物理隔离在私有侧，公开侧只出现转述后的分析。

```
教材PDF ─┐
课标PDF ─┼→ ①提取 → ②Obsidian采集 → ③起草chapter.yaml → 你审 → ④入库 → ⑤机检 → ⑥冒烟 → ⑦提交
Obsidian ┘                                                        （pipeline repo）      （high repo demo 分支）
```

## 1. 双 repo 结构

```
.                                 # 本仓库
├── core/
│   ├── extract.py                # PDF 切片（通用）
│   ├── find_notes.py             # Obsidian 检索（通用）
│   ├── ir.py                     # chapter.yaml 读写 + 通用校验
│   ├── adapter.py                # 适配器四件套加载（缺件即非零退出）
│   ├── library.py                # 正典、种子、graph.db 读写（路径全由调用方传入）
│   ├── render.py                 # 小模板引擎（{{name}} / {{#each}} / {{#if}}）
│   ├── scaffold.py               # 生成引擎（只调适配器四件，不含任何 target 分支与具体路径）
│   ├── validate.py               # 三道机检：check.py + run.sh + graph init/topo
│   ├── feedback.py               # 上线反馈环（unmatched / weak）
│   └── migrate_seeds.py          # SEED 内联 → data/graph-seeds.py 一次性迁移
├── targets/high-school-ai-tutor/
│   ├── target.yaml               # repo 地址、ref、全部路径映射
│   ├── templates/                # 整章图/学习页/正典行模板（classDef、边标签、七槽逐字对齐 ch1 样例）
│   ├── checks.py                 # check(ir, artifacts) -> list[Violation]
│   └── prompts/draft-chapter.md  # 起草规则（版权红线等）
├── validate.sh                   # 对钉住的 ref 跑对方自带 check.py + run.sh + graph 校验
├── .github/workflows/drift.yml   # 每周漂移检测（见纪律 6）
├── work/
│   ├── raw/                      # <科目>/<书>/ 切片摘录 + <科目>/extensions/ 外部资料 —— .gitignore
│   │                             #   （extensions 下转述分析 JSON 例外强制入库，见纪律 5）
│   ├── chapters/                 # <科目>/ chapter.yaml —— 版本化，唯一真相源
│   └── snippets/                 # SKILL.md 指针 snippet —— .gitignore，打印后人工贴入
└── README.md                     # 本文

high-school-ai-tutor-skill/       # 公开 repo，本方案涉及的一次性变更：
└── scripts/graph.py              # SEED_NODES/SEED_EDGES 抽到 data/graph-seeds.py，
                                  # init 改读数据文件（重构前后 check.py 同绿 = 无行为变化）
```

**交付形态不变**：每章对 high repo 开 demo 分支、一章一个 commit（`kb(chem-bx1-ch2): 钠和氯 正典+图谱+学习页（18 节点）`），验收后合 main；回滚 = `git revert`，四件套同生同灭。

## 2. 双 repo 协作纪律（六条，固定编号）

**纪律 1 · ref 追 main。** 每次开工先 `git fetch`，把 `target.yaml` 的 ref 推进到 `origin/main` HEAD，跑基线机检；绿了钉在新 ref 开工，红了停下调和——破坏性变更要在起草前发现，不是合入时。last-green 仅作红灯时的回退快照，不是常态。

**纪律 2 · 适配器契约，fail-fast。** 四件必需缺一不可；core 启动时校验完整性，**缺任何一件即非零退出**，绝不 warn-and-continue——`checks.py` 缺席还继续跑，悬空边防线就失效。`checks.py` 签名钉为 `check(ir, artifacts) -> list[Violation]`；路径映射全部住 `target.yaml`；core 不知道任何具体路径、不出现任何 target 名分支。

**纪律 3 · 分级幂等。** 同一 yaml + 同一 ref 连跑两次 `--apply`：文本产物第二次必须 `git diff` 为空（字节级）；graph.db 按 SQL dump 等价判定（sqlite 二进制跨环境不保字节稳定）。实现前提：正典追加“已存在即跳过”，seeds 文件“整体重生成、非追加”。

**纪律 4 · 生成物清单 + 行为级禁令。** 生成物 = 正典追加区、整章图、学习页、graph-seeds、graph.db；人写物 = SKILL.md 两行指针（人工贴入）与 pipeline 侧一切。正典是**混合文件**：策展区（如 ch1 的 14 行）人写、追加区生成；scaffold 对正典**只查重追加、永不重写既有行**；一切内容修改回 yaml → 重生成，high repo 侧禁止手改生成物——否则下次重生成会静默覆盖手改。

**纪律 5 · work/ 拆分 + 科目分层。** `raw/<科目>/<书>/`（切片、摘录，gitignore，敏感物不出私有侧）与 `chapters/<科目>/`（真相源，必须版本化）分开；scaffold --all 递归读取全部科目；新增一科时在两个目录下建该科目子目录即可，工具与 target 无需改动（target 是全科 tutor，canon 文件由每份 yaml 的 canon_file 字段指向）。ignore 整个 `work/` 会让真相源丢失历史。外部资料（真题点评、月考模拟、延伸书）放 `raw/<科目>/extensions/<类别>/`：docx/PDF 原件留在忽略区，从中提取的**转述分析 JSON**（如 `2026北京卷-考点提取.json`、`人大附模拟卷-考点提取.json`，老延伸书的时效勘误如 `陈阅增3版-时效勘误.json`）用 `git add -f` 强制入库——`.gitignore` 对 `work/raw/**` 的整体忽略不变，"转述可入库、原件必留私有"由添加动作保证，不由 ignore 规则表达。

**纪律 6 · CI 首轮必做，且先自验证。** 每周定时：推进 ref → 基线机检 → demo 重生成 → 文本 `git diff --exit-code`。workflow 先写、先空跑（stub target），验证三件事：能推进 ref、能跑 validate、diff 非空能红灯——不等第二章才首跑。

## 3. 环境准备（一次性）

1. 建 pipeline repo：README（本文）→ core + 适配层 → CI 空跑。
2. high repo：`python3 tests/check.py` + `bash tests/run.sh` 基线全绿 → SEED 数据文件化重构 → 复跑同绿。
3. `pip3 install -r requirements.txt`（有 PyMuPDF 时提取优先用它，否则用 pypdf）。Python 是 uv/PEP 668 管的时先进 `python3 -m venv .venv` 再装；扫描书 OCR 另需 `pymupdf`、`pillow`、`ocrmac`（仅 macOS）。

## 4. 单章流水线（七步）

**① 提取**：`python3 core/extract.py 教材.pdf --out work/raw/chem-bx1`（课标同）。逐页标页码 → 正则切章 → `toc.txt`。人工核对切分（1 分钟，乱码人工补页码）。

**② Obsidian 采集**：`python3 core/find_notes.py --vault ~/库路径 --query 钠`。只取自己写的分析；整段抄录课文的笔记跳过。

**③ 起草 chapter.yaml**（LLM 会话 + 你审，全流程核心）。规则在 `targets/high-school-ai-tutor/prompts/draft-chapter.md`。schema：

```yaml
chapter_id: chem-bx1-ch2
subject: 化学
book: 人教版《化学 必修 第一册》（2019）
book_short: chem-bx1
chapter_no: 2
chapter_title: 海水中的重要元素——钠和氯
canon_file: references/nodes/chemistry.md
canon_chapter: 必修第一册 第二章 海水中的重要元素——钠和氯
graph_doc: references/pep-chem-bx1-ch2.md
entry_question: 先学哪个节点：钠及其化合物、氯及其化合物，还是物质的量？
sections:
  - title: 钠及其化合物
    nodes:
      - id: kp_na
        display: 钠的性质             # 正典显示名；学习页状态标签用这个名字，文件名用 id
        aliases: [钠单质, 金属钠]      # 科目内唯一
        type: concept                # concept | skill | experiment
        l1: 能说出钠的物理性质和与氧气、水反应的现象   # 课标"了解/知道/举例"级
        l2: 能解释钠与水反应的现象并写出化学方程式     # 课标"说明/判断/应用"级
        l3: 待补录：延伸不在本节点展开
        example: 钠投入滴有酚酞的蒸馏水，浮、熔、游、响、红   # 可选；不填则槽内写"（待补录：……）"
        pitfall: 与盐酸反应不能写成钠先与水反应再中和        # 可选
        confusion: 钠与盐溶液反应：钠先与水反应           # 可选
        source: {textbook: P36-38, curriculum: 主题2}    # 仅页码引用
edges:                               # 标签只有 直接前置 | 同章衔接
  - [kp_na, kp_na2o2, 直接前置]
combo:                               # 虚线，可指向他章已入库节点
  - [kp_na2o2, kp_ion_eq, 常考组合]
later:
  - {id: ch3_fe, display: 第三章 铁}
```

起草红线：定义必须转述、禁止逐字摘录课文；例题自编并标“示例题非教材原题”；不搬插图；争议别名不入库（留 raw 给反馈环收编）；边标签三选一；拿不准的节点不写。

你的审阅：全表快扫（前置、超纲、实验遗漏、别名）+ **边抽检**（抽 3 条让起草会话自证“为什么是直接前置”，深审这 3 条）+ **如实记录耗时**（校准后续排期）。

**④ 入库**：`python3 core/scaffold.py work/chapters/chem-bx1-ch2.yaml --repo <high repo 检出> [--apply]`。写入前硬校验，任一失败即中止并指到 yaml 位置：id 全库唯一；别名科目内查重；`# id` 注释指向显示名；**三方节点集一致**（整章图 = 正典新增 = seeds）；**边端点存在性**；边标签枚举；本章实线边无环。产物：正典追加、`references/pep-chem-bx1-ch2.md`、`references/study-pages/chem-bx1-ch2/kp_*.md`（七槽 + 状态标签；“已机验：通过”只标判别自测槽，语义是自测题的核对状态而非页面完整度；自测题从已审 L1 派生；占位槽显式“待补录”）、`data/graph-seeds.py` 重生成 + `graph.py init` 重建 db、SKILL.md 指针 snippet（打印出来，并写到 `work/snippets/`，人工贴入）。

**⑤ 机检**：`./validate.sh --repo <high repo 检出> --chapter chem-bx1-ch2`。三道闸：`tests/check.py`；`bash tests/run.sh`（当前 32 用例保持全绿）；`graph.py init + topo`（无环）。**topo 三态规则**（已对 `graph.py` 的排序实现核实）：

| 节点状态 | 排序 | 环检测 | 章末预告 |
|---|---|---|---|
| 本章正式节点 | 参与 | 参与 | — |
| 他章节点 / later 灰占位 | 不参与 | 不参与 | 自动列出，有页标“有讲解页” |
| 悬空端点 | 静默忽略 | 静默忽略 | JOIN 静默丢弃 |

第三行即纪律 2 fail-fast 与④端点校验存在的理由：**三道机检对悬空边全部失明，scaffold 是唯一防线**。`validate.sh` 另加一道：种子里该章每个非灰节点都必须出现在 topo 输出里，丢掉了就当有环，非零退出。

**⑥ 冒烟（每章必做，5 分钟）**：装 skill 问“我要自学人教版化学必修一第二章”。查：状态标签正常；节点名命中正典显示名（E17c 不报错）；整章图原样输出。

**⑦ 提交**：一章一 commit；回滚 = revert。**红线：不改第一章 combo 边指向**（`ch2_na` 等占位保持原样——`test_graph.py` 断言章末预告 `asset=False`，ch2 节点带页后改指向必红；将来清理须连测试一起改并单独成 commit）。

## 5. 上线反馈环（每两周约 15 分钟）

`python3 core/feedback.py --repo <high repo 检出>` 会先跑对方的 `records.py unmatched`，再跑 `records.py weak`。补录表就是 unmatched 打出的「频次 | 原文 | 建议补录为」；weak 用来排下一章。人工确认 → 补 aliases（回 yaml 重生成，或按纪律 4 处理策展区）→ 重跑 check.py。别名枚举不完是设计内状态。

## 6. 时间线与默认值

首轮：pipeline repo + CI 空跑 → high repo 基线与 SEED 重构 → 第二章 demo 全绿交付。后续每章：起草 15–30 分钟 + 审阅 + 冒烟，首轮实测耗时后校准。扩展顺序：化学必修一全册 → 课标覆盖其他册 → 按 weak 频率扩科。现状（2026-09）：主线已转生物备考——人教五本教材 + 两版课标，25 章真相源在 `work/chapters/生物/`，真题/模拟/延伸书资产在 `work/raw/生物/extensions/`（含陈阅增 OCR 与时效勘误、生理学第 10 版）；化学线待定。默认值：试点 = 化学必修一第二章；通行内容起草 + PDF 校准（初稿标”待校准”）；demo 分支交付；SEED 重构做；**待补 = Obsidian 库路径与目录结构**（缺了不阻塞，步骤②后补）。教材 PDF 与课标 PDF 到位后再跑①和③。

## 7. 风险对策

| 风险 | 对策 |
|---|---|
| 教学语义机检盲区 | 边抽检 + 冒烟必做 + 人工审唯一关卡 |
| 格式漂移（high repo 变更） | 纪律 1 追 main + 纪律 6 CI 漂移检测 |
| 分层名存实亡 | 纪律 2 fail-fast + core 无 target 分支 |
| 重生成噪音 / 手改被覆盖 | 纪律 3 分级幂等 + 纪律 4 行为级禁令 |
| 真相源丢历史 / 敏感物泄露 | 纪律 5 目录拆分 |
| 悬空边静默 | scaffold 端点校验（唯一防线） |
| 版权 | 转述红线入 prompt + schema 无原文字段 + 私有/公开物理隔离 |

## 8. 本仓库命令

```bash
pip3 install -r requirements.txt
python3 -m unittest discover -s tests -t . -v   # 含 stub 空跑
python3 scripts/ci_dry_run.py                   # 只跑空跑

python3 core/migrate_seeds.py --repo <high repo 检出> [--apply]
python3 core/extract.py 教材.pdf --out work/raw/chem-bx1
python3 scripts/ocr_fill.py work/raw/<科目>/extensions/<书名>   # 无文本层扫描书全书 OCR，按人工核对的 toc.txt 切章（macOS Vision）
python3 core/find_notes.py --vault ~/库路径 --query 钠
python3 core/scaffold.py work/chapters/<id>.yaml --repo <high repo 检出> [--apply]
python3 core/scaffold.py --all --repo <high repo 检出> --apply
./validate.sh --repo <high repo 检出> --chapter <id>
python3 core/feedback.py --repo <high repo 检出>
python3 scripts/drift_check.py --target high-school-ai-tutor
```

`migrate_seeds.py` 把内联 `SEED_NODES` / `SEED_EDGES` 抽到 `data/graph-seeds.py`，`graph.py init` 改为读这个文件，缺文件就非零退出。已经迁过的仓库再跑是空操作。在当前 `origin/main`（`53b875b`）上迁完之后，种子 SQL dump 与原 `graph.db` 一致，`tests/check.py` 通过，`tests/run.sh` 为 32/32。公开仓库上的这次改动需要单独提交；在那之前，`scaffold.py --apply` 会拒绝写入。

每周 workflow（`.github/workflows/drift.yml`）在定时和手动触发时克隆 high repo、推进 ref、跑三道机检、重生成。push / pull request 上先跑单测和 stub 空跑。空跑证明三件事：能 `fetch` 并钉新 ref、基线 `validate` 能绿、文本 diff 非空会红灯；基线变红时 ref 留在上一块 last-green。

## 9. 家庭使用与讲解协议（家长与孩子约定，2026-09-26）

1. 孩子提问，讲解必须给出依据：教材页码 + 课标条目号，原文在 `work/raw/` 可当场对照。
2. 孩子说"不对"：先记录争议、文件不动；出示依据让他对比分析。确认知识库错了才改 yaml 重生成；
   确认孩子错了，原始说法记入反馈环（records raw），下次换角度讲。
3. 还没讲的（课内未学）：正常讲解，依据注明所属章节与页码，提示学校进度。
4. 问题模糊：先对齐到课标条目或教材某节，讲清"这个问题的准确范围"再作答。
5. 超纲内容：可用大学/竞赛教材讲解，深度以回答问题为限，并明示"这超纲了"。
   引用分两档：书未入库时只报书名+版次+章节，页码标"待核对"，禁止凭记忆编页码；
   书的电子版放入 `work/raw/<科目>/extensions/<书名>/` 并经 extract.py 建索引后，页码引用才可落死；
   扫描件无文本层时三步走：extract.py（占位）→ 渲染目录页人工核对 toc.txt → ocr_fill.py 全书 OCR（检索用，引用以渲染图为准）。
   老版延伸书（如 2009 年成书的陈阅增）讲解前先查该书 `*-时效勘误.json`，按条目分级处理：
   框架级先校正再讲、事实级报现行数字、补充级标超纲。
6. 真相源永远是 yaml + 教材 + 课标 + 已入库的延伸书，不因任何一方口头说法单方面更新。
