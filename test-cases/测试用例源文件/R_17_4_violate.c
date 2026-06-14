// 明显违规：else分支没有return
int test(int x) {
    if (x > 0) {
        return 1;
    }
    // 当x<=0时，走到函数末尾没有return
}