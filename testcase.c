#include <stdio.h>
#include <stdlib.h>

struct Box {
    int value;
};

int dataflow_demo(int a, const char *input) {
    int x = a + 1;
    const char *msg = input;
    char *plain_ptr = NULL;

    int left = 1, right = 2;
    int arr[3] = {1, 2, 3};
    volatile int flag = a;
    static int cached = 0;
    struct Box box = {a};

    return x + left + right + arr[0] + flag + cached + box.value
        + (msg != NULL) + (plain_ptr == NULL);
}

void cleanup_demo(char *p) {
    free(p);
}

int main(void) {
    char *p = malloc(16);
    int result = dataflow_demo(3, "hello");
    cleanup_demo(p);
    printf("%d\n", result);
    return 0;
}
