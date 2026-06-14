// 明显违规：两个return语句
int test(int x) {
    if (x > 0) {
        return 1; // 提前返回
    }
    return 0; // 第二个返回点
}