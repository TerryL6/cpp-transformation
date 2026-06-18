#include <stdio.h>

void sink(const char *s) {
    puts(s);
}

void demo(const char *input) {
    const char *tmp = input;
    sink(tmp);
}

int main(void) {
    demo("hello");
    return 0;
}
