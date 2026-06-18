#include <stdio.h>

void sink(const char *s) {
    puts(s);
}

void demo(const char *input) {
    sink(input);
}

int main(void) {
    demo("hello");
    return 0;
}
