// 看起来违规，但实际上只有一个出口
int test(int x) {
    if (x > 0) {
        goto exit;
    }
    x = 0;
exit:
    return x; // 所有分支都走到这里
}