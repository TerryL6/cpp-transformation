---
name: transform framework v2 - source location
overview: 为现有 srcML+lxml 严格树到树 C/C++ 变换框架新增"源位置追踪"体系:先做 srcML 位置行为可行性研究(不假设),再评估单树/双树设计并落地位置追踪。记录候选/选中/变换前/变换后的 line/column,并区分 file、function、snippet、JSONL 字段四类输入下行号的含义,能恢复仓库真实位置才恢复、信息不足不编造。lxml 仍是默认且唯一改写后端。仓库级验证已拆分到 V3。本阶段只产出技术方案,不改任何代码。
todos:
  - id: srcml-position-study
    content: 可行性研究(不假设,由 agent 直接实测、不留表格/测试文件):实测 srcML --position 的 start/end 表示、1-based/0-based、tab 对列的影响、哪些节点带位置、位置是否干扰 mutation/unparse、变换后是否失效、是否需重解析;测完口头汇报结果供你自行判断
    status: completed
  - id: single-vs-dual-decision
    content: 基于研究结果在单树/双树间决策;若需双树,落地"干净树 locate + 位置 sidecar + 结构索引路径映射";位置在 locate 时即时固化为 SourceLocation 值对象
    status: completed
  - id: location-model
    content: 实现 SourceLocation 模型与 input/original/transformed/repo basis、mapping_status,修正 source_location 解析(start+end),frontend 增加 with_position 选项
    status: completed
  - id: location-flow
    content: 让位置信息贯穿 locate/pick/transform/unparse/report,扩展输出 JSONL 与报告,定义文件/函数/片段/JSONL 字段语义与仓库行号恢复规则
    status: completed
  - id: output-location-extension
    content: 扩展 TransformResult/run_log/report 的 locations 字段与位置可恢复率汇总
    status: completed
isProject: false
---

# C/C++ 变换框架 V2:源位置追踪(仅规划,不实现)

> 约束遵守:本方案**不修改任何现有代码**。lxml 仍是默认且唯一的改写后端。
> 拆分说明:本 V2 **只覆盖源位置追踪**;仓库级编译验证已拆分到 **V3**(`framework_plan_v3_*`)。V3 的"定位文件与代码位置/行号反向映射"依赖本 V2 的位置模型。

---

## 0. 实施状态(✅ 已完成 — 2026-06,含评审后精简)

本方案已实现并通过全部 36 个测试。决策:**采用方案 A(单树)**——可行性研究证实位置属性对 mutation/unparse **零干扰**,无需双树;`SourceLocation` 在 locate 时即时固化(改树前)。

**评审后的最终数据模型(已精简,9 字段 → 6 字段)**

- `SourceLocation`(6 字段):`source`(文件路径或 JSONL 字段名)、`relative_to`(`input` | `file` | `output` | `repo`)、`start_line/start_col/end_line/end_col`(1-based)。
  - 合并:旧 `basis` + `mapping_status` → 单一 `relative_to`;重命名:`path_or_field` → `source`。
  - 删除:`confidence`(死字段)。移走:`tab_size` → **run-level**(`run_log.jsonl` 的 `run_meta` 行 + 报告各一处)。
- `transform` 块(扁平化,去掉 `locations` 子块):
  - `candidate_count`:定位到的候选总数(选中+未选中)。
  - `selected_candidates`:被改候选的**瘦身**结构化描述(`cid`/`node_type`/`enclosing_function`/`original_text`/`source_location`);**改前位置**即每个候选的 `source_location`(精确、按候选)。
  - `transformed_location`:**改后位置 = 改动行段列表(B 档)**,由 `changed_line_spans` 对 原文/输出 行级 diff 得到,`relative_to=output`,列号留空;纯删除记为零宽度点。
- **去重**:旧设计把"改前位置"存了三遍(`candidate`/`selected[0]`/`original`),现合并为"每个选中候选自带 `source_location`",一处真相。

**各文件改动**

- **新增** [location/model.py](cpp_transform/location/model.py) + [__init__.py](cpp_transform/location/__init__.py):`SourceLocation`、`from_srcml_node()`、`apply_input_context()`、`changed_line_spans()`。
- **frontend**:`parse(..., with_position=False)`,带位置附加 `--position --tabs=N`;`tab_size` 仍是 frontend 配置(默认 8)。
- **pipeline**:带位置解析 → 富集改前位置 → mutate → unparse → 填 `candidate_count`/`selected_candidates`/`transformed_location`。
- **cli**:区分输入语义(`file`/`snippet`/`jsonl_field`);run_log 增 `candidate_count`/`before_line`/`relative_to`,并写 run-level `tab_size` 的 `run_meta`;combined 模式聚合。
- **report**:「Source locations」小节(before/after 覆盖率 + `relative_to` 分布 + `tab_size`)。
- [io/writer.py](cpp_transform/io/writer.py) **无需改动**:随 `TransformResult.to_dict()` 自动落盘。

**关键语义与定稿**

- 输入语义:`file` 输入 → 改前 `relative_to=file`;`function/snippet/jsonl_field` → `relative_to=input`(**不编造**仓库行号)。
- **仓库行号恢复(`relative_to=repo`)推迟到 V3**(需数据集文件/commit 锚点;`line_changes.line_no` 是函数相对的,正是 V3 要补的缺口)。
- 改后位置定位为**行级、用于报告 + V3 报错归因**;检测评估按 repo/函数级,不需要列级精确的"按候选改后位置"。
- 开放问题定稿:默认 `--tabs=8`;主战场 **WSL**;方案 A 无 sidecar 性能问题。

---

## 1. 需求理解

为每次变换记录 line/column,覆盖四个点:**候选定位 / 被选中候选 / 变换前原始代码 / 变换后生成代码**;并区分 file、function、snippet、JSONL 字段四类输入下"行号"各自的含义;能恢复仓库真实位置时才恢复,信息不足时**不编造**。

## 2. 与现有框架的关系评估

- 现有管线高度解耦([cpp_transform/pipeline.py](cpp_transform/pipeline.py) 串联 parse→locate→pick→transform→unparse→validate),[Candidate](cpp_transform/model/candidate.py) 已含 `source_location/confidence/metadata`,[TransformResult](cpp_transform/model/result.py) 已含可扩展的 `validation` dict。**位置追踪可作"扩展"而非重写。**
- **关键缺陷(本需求起点)**:[locators/base.py](cpp_transform/locators/base.py) 的 `source_location()` 解析 `pos:start`,但 [frontends/srcml_frontend.py](cpp_transform/frontends/srcml_frontend.py) `parse()` 未传 `--position`,故位置目前恒为 `None`。
- **关键约束(影响单/双树决策)**:transform 直接在 `cand.node` 这个**活 lxml 节点**上 graft/insert/remove(见 [transforms/variable_chain.py](cpp_transform/transforms/variable_chain.py) `apply`)。因此候选节点必须属于"被改写并反解析"的那棵树。
- 数据集 `sven_sample_10.jsonl` 每条含 `file_name / func_name / line_changes`,其中 `line_changes.line_no` 是**函数相对**(从函数文本首行计),非文件相对——这正是本 V2 要澄清并形式化的映射问题。
- 结论:新增 `location/` 子系统,并小幅扩展 frontend/pipeline/model/io/report。

## 3. srcML 位置行为可行性研究(由我直接实测,不留产物)

> 原则:**不假设任何行为**。文档查到的事实(1-based、默认 tab=8、`pos` 命名空间、`L:C` 冒号格式)只作**待验证假设**,以实测为准。
> 执行方式:由我(agent)用临时的小输入直接跑 `srcml` 完成实测,**不生成表格、不在仓库留测试文件**;测完把结论**口头汇报**给你,你据此自行再判断一次。

需实测并回答的问题:
- **start/end 表示**:`pos:start`/`pos:end` 是否为 `行:列`;end 指向元素末字符还是其后一位。
- **1-based vs 0-based**:文件第一个 token 是否为 `1:1`。
- **tab 对列的影响**:同一含 `\t` 行,`--tabs=1` 与 `--tabs=8` 下 tab 后 token 的列差。
- **哪些节点类型带位置**:是否每个元素都带 `pos:*`,还是仅部分类型。
- **位置是否干扰 mutation/unparse**:带位置 XML 直接反解析并与原文 diff;带位置树 graft 后反解析 vs 干净树同样改写,逐字节对比。
- **变换后是否失效**:graft 后周边节点 `pos:*` 是否仍是旧坐标(预期失效)。
- **是否需重解析**:对反解析出的 transformed 源码再 `--position` 解析,确认能取得新坐标。
- 附加:grafted 子树(snippet 单独解析,位置相对 snippet)并入主树后位置的不一致性。

汇报内容仅为上述问题的实测结论(口头),作为方案 A/B 决策与后续设计的事实依据。

### 已得结论(2026-06,WSL 实测:srcml 1.1.0 / srcql 1.0.0 / lxml 6.1.1)

- **start/end 表示**:`pos:start="行:列"` / `pos:end="行:列"`(冒号分隔);**end 为闭区间,指向元素最后一个字符**(如 `int`→`1:1`..`1:3`,`main`→`1:5`..`1:8`);边界节点偶现列 0(如 `block_content` 的 `pos:end="3:0"`)。
- **1-based**:行、列**均 1-based**(首 token `int` 即 `1:1`)。
- **tab 影响列**:确有影响——含 `\t` 行,`--tabs=1` 时该处 `int` 在列 2,`--tabs=8` 时在列 9;默认 tab=8,并在 `<unit>` 记录 `pos:tabs="8"`。
- **哪些节点带位置**:**几乎所有元素**都带 `pos:start/end`(function/type/name/parameter_list/block/block_content/decl_stmt/decl/init/expr/literal 等),非仅部分类型。
- **位置不干扰 mutation/unparse**:带位置 XML 与干净 XML 反解析**逐字节相同**;真实 graft(带位置 snippet 子树插入带位置主树)反解析输出正确;`parse(--position)→unparse` **完全无损**。→ srcml 反解析**忽略位置属性**。
- **变换后位置失效**:graft 后原节点仍声称旧坐标、snippet 节点带相对 snippet 的坐标(错位)。
- **需重解析**:对 transformed 源码再 `--position` 解析方得正确新坐标(如 `z`→`2:5`、`x`→`3:5`)。
- **附带**:文件路径输入会泄漏 `filename` 属性,stdin(`-`)不会(框架已用 stdin)。
- **对决策的含义**:位置对 mutation/unparse **零干扰**,故 **方案 A(单树)成立且更简**;**初步推荐方案 A**(最终由用户判断)。

## 4. 单树 vs 双树设计评估与推荐

> 不自动采纳双树。三点先行洞察:
> 1. **位置在 locate 时即时固化为 `SourceLocation` 值对象**(不依赖节点 `pos:*` 属性)→ 变换后属性是否失效都不影响已记录的位置。两方案都采用此前提。
> 2. **lxml 跨树节点不可互换**:两次解析得到不同对象;现有 transform 直接在 `cand.node` 上改写,**不能**把"另一棵树的节点"交给它。
> 3. 故映射方向必须保证 `cand.node` 属于改写树。

**方案 A — 单树(推荐默认,前提:研究确认位置不干扰 mutation/unparse)**
- 解析一次(带 `--position`)→ locate → 即时固化位置 → 同树 mutate → unparse。
- 优点:最简单;候选身份天然一致;**locator/transform 接口零改动**;无映射问题。
- 缺点/风险:依赖"位置属性对 unparse/graft 无害"(预期成立,因 srcml 反解析靠元素文本而非位置属性);grafted 子树位置不一致,但因位置已即时固化、变换后本就需重解析,影响为零。

**方案 B — 修正版双树(回退,仅当研究测出位置干扰)**
- locator 仍在**干净改写树**上跑(保证 `cand.node` 对 transform 有效);另解析一棵**位置 sidecar 只读树**;对每个候选节点用其在干净树中的**结构索引路径**到 sidecar 解析同一路径节点,读 `pos:*` 写入 `SourceLocation`。
- 优点:改写/反解析与现状完全一致,零干扰风险;transform 接口零改动(永不把外来节点交给 transform)。
- 缺点:多一次解析 + 一个路径映射 helper;pipeline/locator 增加"位置富集"步骤。

**候选→位置 映射设计(方案 B 用)**
- **首选:结构索引路径**——从 root 起逐层子元素序号(如 `[0,3,1,2]`)。同一源码带/不带位置解析出的两棵树**结构同构**(仅多属性),索引路径 1:1 唯一、**确定性、无碰撞**。
- **校验**:逐层 `localname/节点类型`必须相等;`归一化文本相等`仅作断言(不作主键)。
- **明确**:绝不复用另一棵树的 lxml 节点对象;只用路径在目标树**重新解析**出本树节点。
- 不采用文本指纹 /(函数名+类型)作主键(重复语句会碰撞)。

**推荐**:**测试优先;默认方案 A;仅当研究测出干扰才退回方案 B。** 两者都先把位置即时固化为 `SourceLocation`。

## 5. 源位置追踪设计(数据模型)

- **开启位置标注**:frontend 增加 `parse(..., with_position=False)`;按需附加 `--position`(可选 `--tabs=N`),输出 `pos:start="L:C"`/`pos:end="L:C"`。
- **修正解析**:扩展 `source_location()` 同时解析 start 与 end(现仅 start),冒号分隔,容错缺失。
- **位置元数据模型 `SourceLocation`**(新 `cpp_transform/location/model.py`),字段:
  - `start_line/start_col/end_line/end_col`(均 1-based,以研究结论为准);
  - `basis`:枚举 `input_relative | original_source | transformed_output | repo_relative`;
  - `path_or_field`:文件路径或 JSONL 字段名;
  - `mapping_status`:`exact | input_only | repo_recovered | ambiguous | unknown`;
  - `confidence`、`tab_size`。
- **位置失效规则**:变换+unparse 后原 position 失效;若需变换后位置,必须对 transformed 源码**重新 parse(带 --position)**取得,而非沿用旧位置。

## 6. 文件 / 函数 / 片段 / JSONL 字段的位置语义

- **完整文件**:位置即**文件相对**,可直接对应真实仓库行列。
- **抽取的函数 / 片段**:位置仅**相对该抽取输入**(从片段第 1 行计),不等于仓库行号。
- **JSONL 字段**:位置相对**该字段(如 `func_vuln`)存储的代码字符串**,需显式记录 `path_or_field`。
- **能否恢复仓库真实位置**:
  - 能:当具备"字段在原文件中的起始行/字符偏移"映射(如能定位 `func_name` 在 `file_name` 中的起始行,或数据集提供 char offset)时,可由 input-relative 推出 repo-relative,`mapping_status=repo_recovered`。
  - 不能:仅有孤立片段、无文件锚点时,只能给 input-relative,`mapping_status=input_only`,**不编造仓库行号**。
- 注意 srcML 列号受 tab 影响(默认 tab=8,以研究为准),且历史上多字节 Unicode 列号有偏差(2025 已修);需在元数据记录 `tab_size` 以便复现。

## 7. 对现有架构与数据模型的改动

- **新增** `cpp_transform/location/`:`SourceLocation` 模型 +(方案 B 时)结构索引路径映射 helper +(可选)input→repo 映射骨架(真正反向映射在 V3 落地)。
- **小幅扩展**(不重写):
  - [frontends/srcml_frontend.py](cpp_transform/frontends/srcml_frontend.py):`parse(..., with_position=False)` 选项(方案 B 再加位置 sidecar 解析)。
  - [locators/base.py](cpp_transform/locators/base.py):`source_location()` 解析 start+end,返回 `SourceLocation`;locate 时即时固化位置。
  - [model/candidate.py](cpp_transform/model/candidate.py):`source_location` 改用 `SourceLocation`。
  - [model/result.py](cpp_transform/model/result.py):新增 `locations`(candidate/selected/original/transformed)字段。
  - [pipeline.py](cpp_transform/pipeline.py):locate 后填充位置;(可选)对 transformed 重 parse 取变换后位置;延续"单条失败隔离、整批继续"。
  - [io/writer.py](cpp_transform/io/writer.py)/[report/report.py](cpp_transform/report/report.py):输出与报告扩展。
- 位置信息流向:locate(input 位置,即时固化)→pick(选中位置)→transform→unparse→(可选)对 transformed 重 parse 取变换后位置→report。

## 8. 输出元数据与状态

- transform 元数据新增:`locations`: `{candidate, selected, original, transformed}` 各为 `SourceLocation`(含 `basis` 与 `mapping_status`)。
- 日志:`run_log.jsonl` 增位置摘要字段;report 增"位置可恢复率"(各 `mapping_status` 分布)汇总。

## 9. 分阶段实施计划与依赖

- **阶段 0(可行性研究,不改主代码)**:由我直接跑第 3 节实测并口头汇报结果(不留表格/测试文件)。
- **阶段 1(设计决策)**:据研究在 方案 A/方案 B 间定夺;确定 `SourceLocation` 模型与位置即时固化策略。
- **阶段 2(必做)**:位置追踪 MVP —— 开 `--position`、修 `source_location`、模型、basis/mapping_status 标注;若方案 B 则落地结构路径映射。
- **阶段 3(必做)**:位置贯穿 locate/pick/transform/unparse/report,输出 JSONL 与报告扩展,四类输入语义与仓库行号恢复规则落地。
- **阶段 4(可选增强)**:input→repo 行号反向映射增强(为 V3 复用)。
- **依赖**:阶段 0 → 1 → 2 → 3;本 V2 是 **V3 仓库级验证**"定位文件与代码位置"的前置。

## 10. 风险、限制与未决问题

- **风险/限制**:位置是否干扰 unparse/graft 需实测(决定 A/B);列号受 tab 与多字节 Unicode 影响;`line_changes.line_no` 函数相对 vs 文件相对的映射缺口;不同数据集字段不一致。
- **需你拍板的开放问题**:
  1. 默认 `--tabs` 取值(沿用 srcML 默认 8 还是固定 1)?
  2. 若采用方案 B,是否每条记录都额外解析位置 sidecar 树(性能 vs 信息完整)?
  3. 运行主战场是 **WSL** 还是原生 Windows(影响列/换行处理)?

## 11. 关于"先做什么"的建议

- **先做**阶段 0(可行性研究)→ 阶段 1(单/双树决策):风险低、用事实定方案,且是 V3 的前置依赖。
- 默认走**方案 A 单树**;仅在研究测出位置干扰时退回**方案 B**。
- 全程 **lxml 保持默认且不动**;仓库级验证按 **V3** 推进。
