int main() {
    // 隐蔽违规：数字和'l'连在一起，容易漏检
    long tricky1 = 111L; // 111后面跟小写l
    long tricky2 = 0123L; // 八进制+小写l

    return 0;
}