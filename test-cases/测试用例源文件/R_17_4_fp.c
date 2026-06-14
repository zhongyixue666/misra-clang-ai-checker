// 看起来违规，但实际上控制流不会到达末尾
int test(int x) {
    while (1) {
        if (x > 0) {
            return 1;
        }
        x++;
    }
    // 永远不会走到这里
}