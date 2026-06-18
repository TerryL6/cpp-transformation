---
name: cpp srcml transform framework
overview: 基于 srcML(无损 XML 往返)+ lxml 重建一个模块化、strict 树到树的 C/C++ 源码变换框架:候选定位 / pick / 树改写 / 反解析 / 验证 / JSONL 批处理与报告全部解耦,首版实现 variable_chain 与 macro_alias 两个变换,服务后续 LLM 与 CodeQL 漏洞检测对抗实验。
todos:
  - id: scaffold
    content: 创建 cpp_transform 包骨架、requirements.txt(lxml)、README;落地 Frontend 协议与 srcml_frontend(subprocess + lxml)
    status: completed
  - id: roundtrip
    content: srcML 往返地基:parse→不改→unparse;对 sven_sample_10 分别记录 exact/normalized equality、reparse、compiler validation、diff;语言判定 --language>字段>扩展名,无则 skipped/error
    status: completed
  - id: model-locators
    content: 实现 Candidate/Context/Result 模型与 decl_locator、call_locator(XPath,只读不改);CLI 可 dump 候选
    status: completed
  - id: pick
    content: 实现 pick 策略:first / random(seed) / all / one_per_function
    status: completed
  - id: variable-chain
    content: 实现 variable_chain 树到树变换(snippet 解析+graft,严禁字节编辑);仅 primitive/enum/普通 pointer,跳过 class/struct/template/reference/array/aggregate/volatile/多声明/全局;命名冲突防护
    status: completed
  - id: validation
    content: 实现 validators:srcML reparse(必需)+ compiler abstraction(clang/clang++ 优先,gcc/g++ fallback,-fsyntax-only)+ structural + applied 检查 + 回退
    status: completed
  - id: macro-alias
    content: 实现 macro_alias(preprocessor/round-trip 演示):唯一宏名+全树冲突检查+bare callee 限制+插入
    status: completed
  - id: cli-file
    content: 实现 file 子命令:单文件/单函数,指定 transform/pick/seed/out
    status: completed
  - id: batch-jsonl
    content: 实现 batch 子命令:流式 JSONL、字段识别、错误隔离、per-transform/combined、保留原文+元数据
    status: completed
  - id: report-tests
    content: 实现 report(markdown + unified diff + 汇总)与 run_log.jsonl;pytest 覆盖往返/定位/两变换/冲突/批处理隔离
    status: completed
isProject: false
---

# C/C++ 树到树变换框架方案 (srcML + lxml)

## 决策依据
- 用户已确认:可安装 srcML;v1 必须为 **strict 树到树**(解析→修改结构化树→反解析),禁止裸字节偏移编辑。
- 现有原型 [adversarial_transform.py](C:\Users\TerryLu\Desktop\Transformation\adversarial_transform.py) 与两个 playground 均为"tree-sitter/Comby 定位 + 字节替换",不满足 strict 树到树,仅作参考。

## 工具链
- 运行环境:**WSL** 运行 srcML 与整个框架(srcml/clang/gcc 经 WSL 调用)。
- 主后端:**srcML 二进制**(无损解析/反解析,保留注释/宏/预处理/格式,无需 compile_commands)+ **lxml**(XPath 定位 + 子树增删改实现真正树到树)+ subprocess。
- 验证:**compiler abstraction**——优先 `clang/clang++`,`gcc/g++` 作 fallback;srcML reparse 为**必需**验证。Tree-sitter 二级校验**不进入 v1**(留作后续)。
- 不选 tree-sitter/Comby 作主改写器(只能字节编辑);不选 Clang 作 v1 后端(需编译信息、pretty-print 有损、对无头文件片段脆弱)。

## STRICT 树到树硬约束(实现红线)
- **禁止**用 byte offset 编辑或对整段 source string 做替换来实现任何 transformation。
- 所有变化必须修改 **lxml/srcML 结构化树**;最终源码**必须**经 `srcml --unparse` 生成。
- 构造新节点的标准做法:用 srcML **解析一个小 snippet** 得到子树,再 **graft(嫁接)** 到主树相应位置(而非手写 XML 文本拼接到源码里)。
- byte offset 仅允许出现在"只读"用途(定位/报告/diff),绝不用于生成输出源码。

## 模块/目录
- `cpp_transform/frontends/`:`base.py`(Frontend 协议 parse/unparse)、`srcml_frontend.py`。
- `cpp_transform/model/`:`candidate.py`、`context.py`(tree/nsmap/命名计数器)、`result.py`。
- `cpp_transform/locators/`:`base.py`、`decl_locator.py`、`call_locator.py`。
- `cpp_transform/pick/strategies.py`:first / random(seed) / all / one_per_function / by_confidence。
- `cpp_transform/transforms/`:`base.py`(ABC + REGISTRY + @register)、`variable_chain.py`、`macro_alias.py`。
- `cpp_transform/codegen/unparse.py`、`validation/validators.py`、`io/dataset.py`+`writer.py`、`report/report.py`、`tests/`、`cli.py`。
- 新增变换接口:`find_candidates / can_apply / apply(就地改 XML) / structural_check` + `@register`。

## v1 两个变换
- `variable_chain`(主,general data-flow 变换):`T x = E;` → 树内 graft 两个 decl_stmt `T __chain_x = E; T x = __chain_x;`;类型复用声明树 `<type>`。
  - **仅应用于明确安全的简单类型**:primitive(int/char/float/...)、enum、普通 pointer(`T*`)。
  - **跳过**:class/struct object、template type、reference(`T&`/`T&&`)、array、aggregate(花括号初始化)、`volatile`、multiple declarators、`static`/`extern` 全局。原因:额外 temporary 可能改变 C++ copy/move、析构与 lifetime 语义。
  - `__chain_<name>` 全树标识符查重,冲突则追加序号。
- `macro_alias`(第二个,**preprocessor / tree round-trip 演示**,非通用 data-flow 变换):对 bare-identifier callee 的内存调用(如 `free`),在合适位置 graft `<cpp:define>` 唯一宏名(如 `SAFE_FREE_<n>`),改写命中调用 `<name>`,并在作用域结束/文件末尾的合适位置插入 `#undef`,避免宏影响后续代码。
  - 约束:唯一宏名 + 全树冲突检查;仅 bare callee(跳过函数指针/成员调用);类型无关,C/C++ 通用。
- **下一项通用 data-flow 变换**:`array_indirection`(v2 首选),其后 pointer 间接、wrapper_function(C 需类型预言机)、struct_field、func-ptr forwarding、dead-code。

## 语言判定(不静默默认)
- 判定优先级:`--language` 显式参数 > dataset `language`/`lang` 字段 > 文件扩展名。
- 三者都无法判定时:**不默认 C/C++**,该条标记 `skipped`/`error` 并记录原因(批处理继续)。

## 验证(分层,不夸大;compiler abstraction)
- syntax(必需):srcML **重解析必过**。
- compilation(compiler abstraction):优先 `clang/clang++`,fallback `gcc/g++`,`-fsyntax-only` + 宽松 preamble;片段缺头文件常 N/A → 标 skipped(不算失败)。
- structural:每变换专属断言;applied 检查防 no-op。
- assumed-semantic / vulnerability:不形式化证明,标 assumed,留待 CodeQL/LLM 经验核对。
- 失败 → 回退原文 + 记 run_log.jsonl + 继续整批。

## round-trip 测试(不预设 srcML 绝对无损)
对每条片段分别记录并报告:**exact-text equality**、**normalized equality**(归一空白)、**srcML reparse** 成功与否、**compiler validation** 结果、**unified diff**。不假设所有 snippet 都无损往返,真实统计保真率。

## 环境与批处理默认(已确认)
- 运行环境:**WSL**。
- batch 默认只转换 `func_vuln`/`vuln_func`,支持 `--fields vuln|fixed|both`。
- 输出默认 **separate transform records**(每变换一条记录)。
- 语言无法判定时**不默认**,记失败或要求显式 `--language`。
