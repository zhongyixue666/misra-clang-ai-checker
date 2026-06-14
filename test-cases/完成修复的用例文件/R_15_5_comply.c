// 合规：只有一个return在末尾
int test(int x) {
    int result = 0;
    if (x > 0) {
        result = 1;
    }
    return result; // 唯一出口
}