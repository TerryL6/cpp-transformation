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
