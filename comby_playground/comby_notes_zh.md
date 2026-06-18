# Comby 中文笔记

## Comby 是什么

Comby 是一个 structural search/replace 工具。它用“像代码一样”的模板匹配代码，再用 rewrite 模板生成替换结果。相比普通 regex，它更适合做小型代码 transformation，因为它能处理括号、字符串、注释和格式变化。

Comby 不是 C/C++ compiler，也不是 type checker。它不会解析真实类型、include、typedef、overload 或 symbol identity。

## `:[x]` placeholder 是什么

`:[x]` 是 named hole，也就是具名占位符。例如：

```text
sink(:[x]);
```

可以匹配：

```c
sink(input);
```

这里 `:[x]` 捕获到 `input`。rewrite 模板里再次使用 `:[x]`，就会把 `input` 放回输出代码。

## Toy transformation 目标

这次 Simple Array transformation 的目标是把：

```c
sink(input);
```

改成：

```c
char *tmp_arr[3] = {"safe1", input, "safe2"};
sink(tmp_arr[1]);
```

输出文件必须是 `comby_playground/toy_simple_array.c`，不能覆盖 `toy.c`。

## Source 和 sink

source 是：

```c
argv[1]
```

sink 是：

```c
printf("%s\n", x);
```

toy 数据流是：

```text
argv[1] -> vuln(input) -> sink(input) -> printf
```

## 为什么这是 vulnerability-preserving

这个 transformation 不是修漏洞，而是保持漏洞语义不变。改写后数据流仍然是：

```text
input -> tmp_arr[1] -> sink(tmp_arr[1]) -> printf
```

中间没有 sanitizer、validation、encoding 或 guard。它只是把数据流藏进数组索引访问里。

## 当前 limitation

这还只是 toy demo。这个规则假设 `sink` 参数可以放进 `char *tmp_arr[3]`，但 Comby 不真正理解 C/C++ type。所以现在不能说它是 general C/C++ transformation framework。
