# MISRA Clang AI Checker
基于LLVM/Clang的MISRA C:2012静态检测与AI自动修复工具，实现了**自定义规则开发、静态分析、自动化检测、LLM驱动缺陷修复**全流程。

## ✨ Features
- ✅ 实现3条MISRA C:2012核心安全规则（Rule 7.3/15.5/17.4）
- ✅ 基于Clang Static Analyzer，精准识别违规场景，无误报漏报
- ✅ 对接DeepSeek大模型，实现代码缺陷一键自动修复
- ✅ 自动化测试流水线，支持违规/合规/边界用例批量检测

## 🛠️ Tech Stack
- 静态分析：C++ / LLVM/Clang / CMake
- 自动化工具：Python / nanobot / DeepSeek API
- 平台：Windows

## 🚀 Quick Start
1.  编译集成了自定义规则的 Clang
2.  配置 nanobot 并接入 DeepSeek API
3.  运行自动化检测脚本：
    ```bash
    python nanobot_auto_checker.py --clang-path "path/to/clang.exe" --rule-set MISRA --rule-id 7_3
