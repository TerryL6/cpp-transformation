#include <stdio.h>

void sink(char *x) {
    printf("%s\n", x);
}

void vuln(char *input) {
    sink(input);
}

int main(int argc, char **argv) {
    if (argc < 2) {
        return 1;
    }

    vuln(argv[1]);
    return 0;
}
