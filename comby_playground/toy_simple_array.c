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
