# Comby Playground Commands

This log records the successful toy workflow only. Comby was installed manually
by the user before these commands.

## Working Directory

Run commands from the WSL terminal in:

```bash
cd /mnt/c/Users/TerryLu/Desktop/Transformation
```

## Check Comby

### Command

```bash
command -v comby
comby -version
```

### Result

```text
/home/terry/.local/bin/comby
1.7.0
```

## Preview Simple Array Transformation

### Command

```bash
pattern='sink(:[x]);'
rewrite=$'char *tmp_arr[3] = {"safe1", :[x], "safe2"};\n    sink(tmp_arr[1]);'
comby "$pattern" "$rewrite" comby_playground/toy.c -matcher .c
```

### Result

Comby previewed this change:

```diff
-    sink(input);
+    char *tmp_arr[3] = {"safe1", input, "safe2"};
+    sink(tmp_arr[1]);
```

## Generate Transformed File

### Command

```bash
pattern='sink(:[x]);'
rewrite=$'char *tmp_arr[3] = {"safe1", :[x], "safe2"};\n    sink(tmp_arr[1]);'
comby "$pattern" "$rewrite" comby_playground/toy.c -matcher .c -stdout > comby_playground/toy_simple_array.c
```

### Result

Generated:

```text
comby_playground/toy_simple_array.c
```

## Check Transformed File

### Command

```bash
cat comby_playground/toy_simple_array.c
```

### Result

```c
#include <stdio.h>

void sink(char *x) {
    printf("%s\n", x);
}

void vuln(char *input) {
    char *tmp_arr[3] = {"safe1", input, "safe2"};
    sink(tmp_arr[1]);
}

int main(int argc, char **argv) {
    if (argc < 2) {
        return 1;
    }

    vuln(argv[1]);
    return 0;
}
```

## Compile

### Command

```bash
gcc comby_playground/toy_simple_array.c -o comby_playground/toy_simple_array.exe
```

### Result

Succeeded. No compiler errors.

## Run

### Command

```bash
comby_playground/toy_simple_array.exe hello
```

### Result

```text
hello
```

## Status

The toy Simple Array transformation ran successfully with Comby. The transformed
file compiled and printed `hello`. This is still only a toy demo, not evidence
that the rule is general for real C/C++ CVE repositories.

## Preview Variable Chain Transformation

### Command

```bash
pattern='sink(:[x]);'
rewrite=$'char *tmp1 = :[x];\n    char *tmp2 = tmp1;\n    sink(tmp2);'
comby "$pattern" "$rewrite" comby_playground/toy.c -matcher .c
```

### Result

Comby previewed this change:

```diff
-    sink(input);
+    char *tmp1 = input;
+    char *tmp2 = tmp1;
+    sink(tmp2);
```

## Generate Variable Chain File

### Command

```bash
pattern='sink(:[x]);'
rewrite=$'char *tmp1 = :[x];\n    char *tmp2 = tmp1;\n    sink(tmp2);'
comby "$pattern" "$rewrite" comby_playground/toy.c -matcher .c -stdout > comby_playground/toy_variable_chain.c
```

### Result

Generated:

```text
comby_playground/toy_variable_chain.c
```

## Check Variable Chain File

### Command

```bash
cat comby_playground/toy_variable_chain.c
```

### Result

```c
#include <stdio.h>

void sink(char *x) {
    printf("%s\n", x);
}

void vuln(char *input) {
    char *tmp1 = input;
    char *tmp2 = tmp1;
    sink(tmp2);
}

int main(int argc, char **argv) {
    if (argc < 2) {
        return 1;
    }

    vuln(argv[1]);
    return 0;
}
```

## Compile Variable Chain

### Command

```bash
gcc comby_playground/toy_variable_chain.c -o comby_playground/toy_variable_chain
```

### Result

Succeeded. No compiler errors.

## Run Variable Chain

### Command

```bash
./comby_playground/toy_variable_chain hello
```

### Result

```text
hello
```

## Preview Wrapper Function Step 1: Insert Wrapper

### Command

```bash
pattern=$'void vuln(:[params]) {\n    :[body]\n}'
rewrite=$'static char *identity_wrapper(char *x) {\n    return x;\n}\n\nvoid vuln(:[params]) {\n    :[body]\n}'
comby "$pattern" "$rewrite" comby_playground/toy.c -matcher .c
```

### Result

Comby previewed insertion of `identity_wrapper` before `vuln`:

```diff
+static char *identity_wrapper(char *x) {
+    return x;
+}
+
 void vuln(char *input) {
     sink(input);
 }
```

## Generate Wrapper Function File

### Command

```bash
insert_pattern=$'void vuln(:[params]) {\n    :[body]\n}'
insert_rewrite=$'static char *identity_wrapper(char *x) {\n    return x;\n}\n\nvoid vuln(:[params]) {\n    :[body]\n}'
comby "$insert_pattern" "$insert_rewrite" comby_playground/toy.c -matcher .c -stdout > /tmp/toy_wrapper_step1.c

sink_pattern='sink(:[x]);'
sink_rewrite='sink(identity_wrapper(:[x]));'
comby "$sink_pattern" "$sink_rewrite" .c -stdin -stdout < /tmp/toy_wrapper_step1.c > comby_playground/toy_wrapper_function.c
```

### Result

Generated:

```text
comby_playground/toy_wrapper_function.c
```

Important point: the sink call rewrite uses the placeholder `:[x]`:

```bash
sink_pattern='sink(:[x]);'
sink_rewrite='sink(identity_wrapper(:[x]));'
```

## Check Wrapper Function File

### Command

```bash
cat comby_playground/toy_wrapper_function.c
```

### Result

```c
#include <stdio.h>

void sink(char *x) {
    printf("%s\n", x);
}

static char *identity_wrapper(char *x) {
    return x;
}

void vuln(char *input) {
    sink(identity_wrapper(input));
}

int main(int argc, char **argv) {
    if (argc < 2) {
        return 1;
    }

    vuln(argv[1]);
    return 0;
}
```

## Check Wrapper Function Conditions

### Command

```bash
grep -c '^static char \*identity_wrapper' comby_playground/toy_wrapper_function.c
grep -n 'sink(identity_wrapper(input));' comby_playground/toy_wrapper_function.c
```

### Result

```text
1
12:    sink(identity_wrapper(input));
```

## Compile Wrapper Function

### Command

```bash
gcc comby_playground/toy_wrapper_function.c -o comby_playground/toy_wrapper_function
```

### Result

Succeeded. No compiler errors.

## Run Wrapper Function

### Command

```bash
./comby_playground/toy_wrapper_function hello
```

### Result

```text
hello
```

## Current Status

Simple Array, Variable Chain, and Wrapper Function all ran successfully on the
toy C file. Each transformed file compiled and printed `hello`. These are still
toy transformations only, not general C/C++ CVE-repo transformations.

## Final Verification

### Command

```bash
ls -l comby_playground
./comby_playground/toy_variable_chain hello
./comby_playground/toy_wrapper_function hello
```

### Result

Generated files include:

```text
toy_simple_array.c
toy_variable_chain.c
toy_wrapper_function.c
toy_variable_chain
toy_wrapper_function
```

Runtime output:

```text
hello
hello
```
