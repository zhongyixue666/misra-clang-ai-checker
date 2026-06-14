// 隐蔽违规：switch没有default分支
int get_value(int code) {
    switch (code) {
    case 1: return 10;
    case 2: return 20;
    case 3: return 30;
        // 当code不是1/2/3时，没有return
    }
}