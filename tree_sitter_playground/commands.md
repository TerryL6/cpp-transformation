# Commands: tree-sitter playground

This file records commands actually run for this playground and their results.

## Environment checks

```powershell
python --version
```

Result: `Python 3.12.1`

```powershell
gcc --version
```

Result: `gcc.exe (x86_64-win32-seh-rev0, Built by MinGW-W64 project) 8.1.0`

```powershell
python -c "import tree_sitter, tree_sitter_cpp; print('tree_sitter ok', tree_sitter.__version__ if hasattr(tree_sitter, '__version__') else 'unknown')"
```

Result: `tree_sitter ok unknown`

The install command from the README was not run because both Python packages
were already importable in this environment.

## Playground runs

```powershell
python ts_playground.py toy.c --mode tree
```

Result: success. The parse tree was printed, and the target node was found:

```text
expression_statement [98, 110) 'sink(input);'
found exact statement at [98, 110): 'sink(input);'
```

```powershell
python ts_playground.py toy.c --mode chain --out outputs/toy_chain.c
```

Result: success.

```text
edit [98, 110) -> 'const char *tmp = input;\n    sink(tmp);'
wrote outputs\toy_chain.c
```

```powershell
python ts_playground.py toy.c --mode wrapper --out outputs/toy_wrapper.c
```

Result: success. The two edits were applied in reverse byte-offset order:

```text
edit [98, 110) -> 'wrapper(input);'
edit [63, 63) -> 'static void wrapper(const char *x) {\n    sink(x);\n}\n\n'
wrote outputs\toy_wrapper.c
```

## Compile checks

```powershell
gcc -Wall -Wextra -c toy.c -o outputs/toy.o
```

Result: success, no compiler output.

```powershell
gcc -Wall -Wextra -c outputs/toy_chain.c -o outputs/toy_chain.o
```

Result: success, no compiler output.

```powershell
gcc -Wall -Wextra -c outputs/toy_wrapper.c -o outputs/toy_wrapper.o
```

Result: success, no compiler output.

## Python syntax check

```powershell
python -m py_compile ts_playground.py
```

Result: success, no output.
