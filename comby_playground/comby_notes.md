# Comby Notes

## What Comby Is

Comby is a structural search-and-replace tool for source code. It matches
code-shaped templates and rewrites them with code-shaped replacement templates.
This is a better fit than raw regex for small source transformations because it
understands balanced delimiters, comments, strings, and formatting variation.

Comby is not a C/C++ compiler or type checker. It does not resolve headers,
typedefs, overloads, declarations, or real symbol identity.

## Placeholder `:[x]`

`:[x]` is a named hole. In this pattern:

```text
sink(:[x]);
```

Comby can match:

```c
sink(input);
```

and capture `input` as `x`. The rewrite can reuse `:[x]` to insert the captured
text into the output.

## Toy Transformation Goal

The target Simple Array transformation is:

```c
sink(input);
```

to:

```c
char *tmp_arr[3] = {"safe1", input, "safe2"};
sink(tmp_arr[1]);
```

The output file must be `comby_playground/toy_simple_array.c`. The original
`toy.c` should not be overwritten.

## Source And Sink

Source:

```c
argv[1]
```

Sink:

```c
printf("%s\n", x);
```

Toy data flow:

```text
argv[1] -> vuln(input) -> sink(input) -> printf
```

## Why This Is Vulnerability-Preserving

The transformation is intended to preserve the vulnerable data flow, not fix it.
After the rewrite, the same value reaches the sink:

```text
input -> tmp_arr[1] -> sink(tmp_arr[1]) -> printf
```

There is no sanitizer, validation, encoding, or guard. The toy transformation
only hides the flow behind array indexing.

## Current Limitation

This is only a toy demo. The rule assumes the captured sink argument is
compatible with `char *tmp_arr[3]`, but Comby cannot verify that. This is not a
general C/C++ transformation framework yet.

## Result

Comby is now available through WSL:

```text
/home/terry/.local/bin/comby
1.7.0
```

The Simple Array transformation was executed on `comby_playground/toy.c`.
The transformed output was saved to:

```text
comby_playground/toy_simple_array.c
```

The transformed file compiled successfully with Windows `gcc`:

```text
comby_playground/toy_simple_array.exe
```

Runtime check:

```text
comby_playground/toy_simple_array.exe hello
```

Output:

```text
hello
```

## Mapping Table

| Toy Transformation | transforms_summary.md mapping | Status |
| --- | --- | --- |
| Simple Array | Transform 90 - Simple Array | Completed |
| Variable Chain | No exact one-to-one transform; warm-up taint propagation test | Completed |
| Wrapper Function | Simplified version of Transform 20 - Long Function Call Chain | Completed |

## Simple Array

Original code pattern:

```c
sink(input);
```

Transformed code pattern:

```c
char *tmp_arr[3] = {"safe1", input, "safe2"};
sink(tmp_arr[1]);
```

Output file:

```text
comby_playground/toy_simple_array.c
```

Exact Comby command:

```bash
pattern='sink(:[x]);'
rewrite=$'char *tmp_arr[3] = {"safe1", :[x], "safe2"};\n    sink(tmp_arr[1]);'
comby "$pattern" "$rewrite" comby_playground/toy.c -matcher .c -stdout > comby_playground/toy_simple_array.c
```

Compile result: succeeded.

Runtime result:

```text
hello
```

Source-to-sink flow is preserved:

```text
argv[1] -> vuln(input) -> tmp_arr[1] -> sink(tmp_arr[1]) -> printf
```

Limitation: this assumes the captured argument is compatible with
`char *tmp_arr[3]`. Comby does not verify C/C++ types.

## Variable Chain

Original code pattern:

```c
sink(input);
```

Transformed code pattern:

```c
char *tmp1 = input;
char *tmp2 = tmp1;
sink(tmp2);
```

Output file:

```text
comby_playground/toy_variable_chain.c
```

Exact Comby command:

```bash
pattern='sink(:[x]);'
rewrite=$'char *tmp1 = :[x];\n    char *tmp2 = tmp1;\n    sink(tmp2);'
comby "$pattern" "$rewrite" comby_playground/toy.c -matcher .c -stdout > comby_playground/toy_variable_chain.c
```

Compile result: succeeded.

Runtime result:

```text
hello
```

Source-to-sink flow is preserved:

```text
argv[1] -> vuln(input) -> tmp1 -> tmp2 -> sink(tmp2) -> printf
```

Limitation: this is a toy taint propagation warm-up. It assumes a local
`char *` context and does not check name collisions, existing variables, scopes,
or real C/C++ types.

## Wrapper Function

Original code pattern:

```c
void vuln(char *input) {
    sink(input);
}
```

Transformed code pattern:

```c
static char *identity_wrapper(char *x) {
    return x;
}

void vuln(char *input) {
    sink(identity_wrapper(input));
}
```

Output file:

```text
comby_playground/toy_wrapper_function.c
```

Exact Comby command:

```bash
insert_pattern=$'void vuln(:[params]) {\n    :[body]\n}'
insert_rewrite=$'static char *identity_wrapper(char *x) {\n    return x;\n}\n\nvoid vuln(:[params]) {\n    :[body]\n}'
comby "$insert_pattern" "$insert_rewrite" comby_playground/toy.c -matcher .c -stdout > /tmp/toy_wrapper_step1.c

sink_pattern='sink(:[x]);'
sink_rewrite='sink(identity_wrapper(:[x]));'
comby "$sink_pattern" "$sink_rewrite" .c -stdin -stdout < /tmp/toy_wrapper_step1.c > comby_playground/toy_wrapper_function.c
```

Compile result: succeeded.

Runtime result:

```text
hello
```

Source-to-sink flow is preserved:

```text
argv[1] -> vuln(input) -> identity_wrapper(input) -> sink(...) -> printf
```

Limitation: this is only a one-layer identity wrapper and a simplified version
of the longer call-chain idea. The sink-call rewrite uses the Comby placeholder
`:[x]` to capture `input`, but the demo still assumes the wrapper type is
`char *`. It does not check helper-name collisions, existing declarations,
linkage, macros, or real C/C++ types, so it is not a general framework yet.
