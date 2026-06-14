// 隐蔽违规：循环中的return
int find(int arr[], int len, int target) {
    for (int i = 0; i < len; i++) {
        if (arr[i] == target) {
            return i; // 循环内提前返回
        }
    }
    return -1;
}