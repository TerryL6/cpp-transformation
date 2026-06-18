#include <stdio.h>

void sink(const char *s) {
    puts(s);
}

static void wrapper(const char *x) {
    sink(x);
}

void demo(const char *input) {
    wrapper(input);
}

int main(void) {
    demo("hello");
    return 0;
}
