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
