#!/usr/bin/env python3
"""Nanobot 自动化检测脚本 — 用户与 nanobot 之间的中间层。"""

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
from dataclasses import dataclass


@dataclass
class Config:
    """参数与状态容器。"""
    clang_path: str = ""
    rule_set: str = ""
    rule_id: str = ""
    source_file: str = ""
    original_source: str = ""
    expected_result: str = ""
    check_command: str = ""


@dataclass
class CaseInfo:
    """单个测试用例的信息。"""
    name: str           # 用例名称（如 "违规用例 (violate)"）
    source_path: str    # 原始文件绝对路径
    copy_path: str      # 工作副本绝对路径
    expected: str       # 预期结果


def parse_args() -> Config:
    """解析命令行参数，返回填充了 4 个入参的 Config 对象。"""
    parser = argparse.ArgumentParser(description='Nanobot 自动化检测脚本')
    parser.add_argument('--clang-path', required=True, help='clang.exe 绝对路径')
    parser.add_argument('--rule-set', required=True, help='规则集名称')
    parser.add_argument('--rule-id', required=True, help='规则 ID')
    args = parser.parse_args()
    return Config(
        clang_path=args.clang_path,
        rule_set=args.rule_set,
        rule_id=args.rule_id,
    )


def parse_relation_file(relation_path: str, rule_set: str, rule_id: str):
    """解析关联关系文件，按 (rule_set, rule_id) 双条件精确匹配。

    Returns:
        (source_file_name, expected_result) 元组，未找到返回 None
    """
    if not os.path.isfile(relation_path):
        return None
    with open(relation_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('——')
            if len(parts) != 4:
                continue
            rname, rid, source, expected = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
            if rname == rule_set and rid == rule_id:
                return (source, expected)
    return None


def lookup_all_relations(script_dir: str, rule_set: str, rule_id: str) -> list:
    """返回该 rule_id 下所有文件实际存在的关联记录。

    Returns:
        [(source_name, expected_result), ...] 列表
    """
    relation_path = os.path.join(script_dir, '关联关系.txt')
    if not os.path.isfile(relation_path):
        return []
    records = []
    source_dir = os.path.join(script_dir, '用例库', rule_set)
    with open(relation_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('——')
            if len(parts) != 4:
                continue
            rname, rid, source, expected = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
            if rname == rule_set and rid == rule_id:
                source_path = os.path.join(source_dir, source)
                if os.path.isfile(source_path):
                    records.append((source, expected))
    return records
    """查询关联关系中 (rule_set, rule_id) 对应且文件实际存在的记录。

    跳过文件不存在的过期记录，防止重复自动生成。
    Returns:
        (source_file_name, expected_result) 或 None
    """
    relation_path = os.path.join(script_dir, '关联关系.txt')
    if not os.path.isfile(relation_path):
        return None
    with open(relation_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('——')
            if len(parts) != 4:
                continue
            rname, rid, source, expected = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
            if rname == rule_set and rid == rule_id:
                source_dir = os.path.join(script_dir, '用例库', rule_set)
                if os.path.isfile(os.path.join(source_dir, source)):
                    return (source, expected)
    return None


def append_relation(script_dir: str, rule_set: str, rule_id: str,
                    source_name: str, expected_result: str) -> None:
    """向关联关系文件追加一条记录（4 字段格式）。"""
    relation_path = os.path.join(script_dir, '关联关系.txt')
    line = f"{rule_set}——{rule_id}——{source_name}——{expected_result}\n"
    with open(relation_path, 'a', encoding='utf-8') as f:
        f.write(line)


def find_source_file(script_dir: str, rule_set: str, target: str) -> str:
    """在 用例库/{rule_set}/ 子目录中搜索用例源码文件，返回绝对路径。

    Raises:
        FileNotFoundError: 未找到文件
    """
    search_dir = os.path.join(script_dir, '用例库', rule_set)
    target_name = os.path.basename(target)

    if os.path.isdir(search_dir):
        for f in os.listdir(search_dir):
            if f == target_name:
                return os.path.abspath(os.path.join(search_dir, f))

    if os.path.isfile(target):
        return os.path.abspath(target)

    raise FileNotFoundError(f"未找到用例源码文件: {target}，搜索目录: {search_dir}")


def find_source_by_rule_id(script_dir: str, rule_set: str, rule_id: str):
    """在 用例库/{rule_set}/ 中搜索文件名包含 rule_id 的 .cpp 文件。

    Returns:
        匹配文件的绝对路径，或 None
    """
    search_dir = os.path.join(script_dir, '用例库', rule_set)
    if not os.path.isdir(search_dir):
        return None
    for f in os.listdir(search_dir):
        if rule_id in f and f.endswith('.cpp'):
            return os.path.abspath(os.path.join(search_dir, f))
    return None


def read_rule_set_file(script_dir: str, rule_set: str) -> str:
    """读取规则集文件全部内容。

    文件路径: 规则集/{rule_set}规则集.md

    Raises:
        FileNotFoundError: 规则集文件不存在
    """
    file_path = os.path.join(script_dir, '规则集', f'{rule_set}规则集.md')
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"规则集文件不存在: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def make_check_command(clang_path: str, rule_set: str, rule_id: str,
                       source_file: str) -> str:
    """拼装 clang 检测命令，不依赖 Config。"""
    return (
        f'"{clang_path}" '
        f'--analyze '
        f'-Xanalyzer -analyzer-checker={rule_set}.{rule_id} '
        f'-o NUL '
        f'{source_file}'
    )


def build_check_command(config: Config) -> None:
    """拼装 clang 检测命令（兼容旧接口，写入 config.check_command）。"""
    config.check_command = make_check_command(
        config.clang_path, config.rule_set, config.rule_id, config.source_file
    )


def copy_to_workdir(script_dir: str, rule_set: str, original_path: str) -> str:
    """将单个用例文件复制到用例库副本目录，返回副本绝对路径。"""
    copy_dir = os.path.join(script_dir, '用例库副本', rule_set)
    copy_file = os.path.join(copy_dir, os.path.basename(original_path))
    os.makedirs(copy_dir, exist_ok=True)
    if os.path.exists(copy_file):
        os.chmod(copy_file, stat.S_IWRITE)
    shutil.copy2(original_path, copy_file)
    os.chmod(copy_file, stat.S_IWRITE)
    return os.path.abspath(copy_file)


def setup_working_copy(config: Config) -> None:
    """在用例库副本目录中创建副本，结构与用例库一致。

    副本放在脚本同级 用例库副本/ 下，格式为 用例库副本/{rule_set}/{filename}。
    原始文件不会被修改。
    """
    original = config.source_file
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 副本目录结构与用例库一致：用例库副本/{rule_set}/{filename}
    copy_dir = os.path.join(script_dir, '用例库副本', config.rule_set)
    copy_file = os.path.join(copy_dir, os.path.basename(original))
    os.makedirs(copy_dir, exist_ok=True)

    # 如果目标已存在，先移除只读属性
    if os.path.exists(copy_file):
        os.chmod(copy_file, stat.S_IWRITE)

    shutil.copy2(original, copy_file)

    # 确保副本可写
    os.chmod(copy_file, stat.S_IWRITE)

    # 更新 config 指向副本
    config.source_file = os.path.abspath(copy_file)
    build_check_command(config)

    print(f"已创建工作副本: {config.source_file}")


# ===== 指令模板 =====

PROMPT_A1 = (
    "请在命令行中执行以下命令，并将完整的输出结果返回给我：\n"
    "{check_command}"
)

PROMPT_A2 = (
    "请将上面命令的输出与以下预期结果进行语义对比：\n"
    "预期结果：{expected_result}\n"
    "不要求文本完全一致，只要语义相同即可。"
    "例如预期结果为\"报出XXX缺陷\"，实际输出中包含了该规则的告警信息，就算符合预期。\n"
    "注意：你只需要做对比判断，不要执行任何命令，不要排查原因，不要修改文件。"
)

PROMPT_A3 = (
    "根据你上面的对比分析，判定结果是否符合预期？请只回答一个字：是 或 否"
)

PROMPT_A3_RETRY = (
    "请严格只回答一个字：是 或 否。不要输出其他内容。"
)

PROMPT_B1 = (
    "请修复文件 {source_file} 中触发 {rule_label} 规则告警的缺陷。\n"
    "只修复 {rule_label} 规则对应的缺陷，忽略其他规则产生的告警。\n"
    "如果文件本身有语法错误导致无法通过编译，请先修复语法错误确保代码可以正常编译进入静态分析阶段，"
    "然后再处理规则缺陷。修复后必须是一个完整、语法正确的 C 代码文件。\n"
    "修复完成后告诉我。"
)

PROMPT_B2 = (
    "请再次在命令行中执行以下命令，并将完整输出返回给我：\n"
    "{check_command}"
)

PROMPT_B3 = (
    "根据上面的输出，{rule_label} 规则的告警是否仍然被报出？\n"
    "注意：只关注 {rule_label} 规则，忽略其他规则的告警。"
    "你只需要做判断，不要执行任何命令，不要排查原因。"
)

PROMPT_B4 = (
    "根据你上面的分析，{rule_label} 规则的告警是否仍然被报出？"
    "请只回答一个字：是 或 否"
)

PROMPT_B4_RETRY = (
    "请严格只回答一个字：是 或 否。{rule_label} 规则的告警是否仍然被报出？"
)

PROMPT_GEN1 = (
    "请从以下规则集文件内容中，找到规则 {rule_id} 对应的规则描述"
    "（包括该规则的要求、推荐、强制等所有描述内容）。\n"
    "\n"
    "规则集：{rule_set}\n"
    "规则集文件内容：\n"
    "```\n"
    "{file_content}\n"
    "```\n"
    "\n"
    "请只返回该规则的完整描述原文，不要添加额外解释。"
)

PROMPT_GEN2 = (
    "请根据以下规则描述，生成四类 C 语言测试用例代码文件。\n"
    "\n"
    "规则集：{rule_set}\n"
    "规则ID：{rule_id}\n"
    "规则描述：\n"
    "{rule_description}\n"
    "\n"
    "请按以下顺序输出四份代码，每份代码前用标记行标明类型：\n"
    "\n"
    "===VIOLATE===\n"
    "违规用例：代码中包含明显触发该规则缺陷的写法，预期 clang 静态分析应该报出 {rule_set}.{rule_id} 告警。\n"
    "\n"
    "===COMPLY===\n"
    "合规用例：代码遵守该规则，预期 clang 静态分析不应该报出该规则告警。\n"
    "\n"
    "===FN===\n"
    "漏报边界用例：代码实际违反该规则，但因为写法隐蔽（如间接调用、宏展开、typedef 包装等），容易导致静态分析工具漏报。预期应该报出 {rule_set}.{rule_id} 告警。\n"
    "\n"
    "===FP===\n"
    "误报边界用例：代码看似违反该规则但实际语义安全（如看起来重复定义但条件编译互斥、表面相似但作用域不同等），容易导致静态分析工具误报。预期不应该报出 {rule_set}.{rule_id} 告警。\n"
    "\n"
    "所有代码必须满足：\n"
    "1. 语法正确，能够通过 clang 编译进入静态分析阶段\n"
    "2. 只针对 {rule_set}.{rule_id} 规则，不要引入其他规则的违规\n"
    "3. 每份代码只输出纯 C 代码，不要包含除标记行外的任何解释"
)


def extract_multi_code(response: str) -> dict:
    """从 nanobot 响应中按标记行提取多份代码。

    标记格式：===VIOLATE===、===COMPLY===、===FN===、===FP===
    返回: {"violate": code, "comply": code, "fn": code, "fp": code}
    """
    labels = {'VIOLATE': 'violate', 'COMPLY': 'comply', 'FN': 'fn', 'FP': 'fp'}
    result = {}

    # 用标记行分割文本
    parts = re.split(r'^===(VIOLATE|COMPLY|FN|FP)===\s*$', response, flags=re.MULTILINE)

    # parts[0] 是第一个标记之前的内容（丢弃），之后交替出现 label, content
    i = 1
    while i + 1 < len(parts):
        label = parts[i].strip()
        content = parts[i + 1]
        key = labels.get(label)
        if key:
            code = _extract_single_code(content.strip())
            if code:
                result[key] = code
        i += 2

    return result


def _extract_single_code(text: str) -> str:
    """从单段文本中提取纯代码，去除 markdown 代码块标记。"""
    text = text.strip()
    for marker in ('```c', '```cpp', '```c++', '```'):
        if text.startswith(marker):
            start = text.index('\n') + 1 if '\n' in text else len(marker)
            end = text.rfind('```')
            if end > start:
                return text[start:end].strip()
            return text[start:].strip()
    return text


class NanobotInterface:
    """nanobot 进程管理与交互。

    通过 nanobot agent -m 单次消息模式与 AI 智能体通信，
    -s 会话 ID 确保上下文在多次调用间持久化。
    """

    def __init__(self):
        self._session_id = f"auto-checker-{os.getpid()}"

    def start(self) -> None:
        """初始化会话（无需启动持久进程）。"""
        pass

    def close(self) -> None:
        """清理（无需关闭持久进程）。"""
        pass

    def query(self, prompt: str, timeout: float = 300) -> str:
        """通过 -m 单次消息模式向 nanobot 发送指令，实时输出并返回响应。"""
        cmd = ['nanobot', 'agent', '-s', self._session_id, '-m', prompt]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1
        )

        spinner_active = threading.Event()
        spinner_active.set()
        def _spin():
            while spinner_active.is_set():
                for c in '|/-\\':
                    if not spinner_active.is_set():
                        break
                    try:
                        print(f'\r  {c} ', end='', flush=True)
                    except UnicodeEncodeError:
                        pass
                    spinner_active.wait(0.15)

        spinner_thread = threading.Thread(target=_spin, daemon=True)
        spinner_thread.start()

        response_lines = []
        try:
            for line in proc.stdout:
                print('\r' + ' ' * 6 + '\r', end='', flush=True)
                self._safe_print(line)
                response_lines.append(line)
        finally:
            spinner_active.clear()
            spinner_thread.join(timeout=1)
            print('\r' + ' ' * 6 + '\r', end='', flush=True)

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise TimeoutError(f"等待 nanobot 响应超时 ({timeout}s)")

        return self._clean_response(''.join(response_lines))

    @staticmethod
    def _clean_response(text: str) -> str:
        """去除 nanobot 输出中的 logo 前缀行等装饰内容。"""
        lines = text.split('\n')
        cleaned = []
        for line in lines:
            stripped = line.strip()
            # 跳过 nanobot 的 logo 行（以 🐈 开头或包含 nanobot 标识）
            if stripped.startswith('\U0001f408') or stripped in ('', 'nanobot', '🐈 nanobot'):
                continue
            # 跳过 "🐈 nanobot" 变体
            if '\U0001f408' in stripped and 'nanobot' in stripped.lower():
                continue
            cleaned.append(line)
        return '\n'.join(cleaned).strip()

    @staticmethod
    def _safe_print(text: str) -> None:
        """安全打印，处理 Windows 控制台无法显示的 Unicode 字符。"""
        try:
            print(text, end='', flush=True)
        except UnicodeEncodeError:
            filtered = text.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
            print(filtered, end='', flush=True)

    @staticmethod
    def parse_verdict(response: str):
        """解析 A3 追问响应，返回 '是' / '否' / None（不明确时）。"""
        has_yes = '是' in response
        has_no = '否' in response
        if has_yes and not has_no:
            return '是'
        if has_no and not has_yes:
            return '否'
        return None


def main_loop(config: Config, cases: list, bot: NanobotInterface,
              script_dir: str) -> None:
    """主循环：对全部用例执行 检测 → 对比 → 修复。

    cases: list[CaseInfo]
    """
    rule_label = f"{config.rule_set}.{config.rule_id}"

    while True:
        # ===== 阶段 A：对所有用例执行检测 + 语义对比 =====
        all_pass = True
        for case in cases:
            print(f"\n--- {case.name} ---")
            check_cmd = make_check_command(
                config.clang_path, config.rule_set, config.rule_id, case.copy_path
            )
            bot.query(PROMPT_A1.format(check_command=check_cmd))
            bot.query(PROMPT_A2.format(expected_result=case.expected))

            verdict = None
            retries = 0
            while verdict is None and retries < 3:
                response = bot.query(PROMPT_A3 if retries == 0 else PROMPT_A3_RETRY)
                verdict = bot.parse_verdict(response)
                retries += 1

            if verdict == '否':
                print(f"  [X] {case.name} — 不符合预期（预期: {case.expected}）")
                all_pass = False
                break
            else:
                print(f"  [OK] {case.name} — 符合预期")

        if all_pass:
            break  # 全部通过，进入阶段 B

        # ===== 阶段 C：用户干预 =====
        print("\n" + "=" * 50)
        print("检测结果不符合预期，需要修复检测代码（checker）。")
        print("修复完成后输入 Y 重新检测，输入 N 停止：")

        while True:
            try:
                choice = input("> ").strip().upper()
            except (EOFError, KeyboardInterrupt):
                print("\n用户中断，脚本退出。")
                return
            if choice == 'Y':
                # 重建所有工作副本，确保修改后的 checker 在干净环境运行
                for case in cases:
                    case.copy_path = copy_to_workdir(
                        script_dir, config.rule_set, case.source_path
                    )
                    print(f"已重建副本: {case.copy_path}")
                break
            elif choice == 'N':
                print("用户停止，脚本退出。")
                return
            else:
                print("请输入 Y 或 N：")

    # ===== 阶段 B：修复所有用例 =====
    print("\n" + "=" * 50)
    print(f"所有 {len(cases)} 个用例符合预期，开始修复阶段...")

    for case in cases:
        print(f"\n--- 修复 {case.name} ---")
        check_cmd = make_check_command(
            config.clang_path, config.rule_set, config.rule_id, case.copy_path
        )
        while True:
            bot.query(PROMPT_B1.format(
                source_file=case.copy_path,
                rule_label=rule_label
            ))
            bot.query(PROMPT_B2.format(check_command=check_cmd))
            bot.query(PROMPT_B3.format(rule_label=rule_label))

            verdict = None
            retries = 0
            while verdict is None and retries < 3:
                response = bot.query(PROMPT_B4.format(rule_label=rule_label)
                                     if retries == 0
                                     else PROMPT_B4_RETRY.format(rule_label=rule_label))
                verdict = bot.parse_verdict(response)
                retries += 1

            if verdict == '否':
                print(f"  [{case.name}] 修复完成")
                break
            # '是' → 告警仍存在，继续修复

    print("\n" + "=" * 50)
    print(f"全部测试用例修复完成：{rule_label}")


def auto_generate_testcase(script_dir: str, config: Config, bot: NanobotInterface) -> None:
    """自动生成测试用例并更新 Config。

    流程:
        1. 读取规则集文件
        2. 通过 nanobot 提取规则描述
        3. 通过 nanobot 根据描述生成 C 代码
        4. 提取代码，保存到 用例库/{rule_set}/{rule_id}_violate.cpp
        5. 追加关联关系记录
        6. 更新 config.source_file 和 config.expected_result

    Raises:
        FileNotFoundError: 规则集文件不存在
        RuntimeError: nanobot 生成失败
    """
    print("用例文件不存在，触发自动生成测试用例...")

    file_content = read_rule_set_file(script_dir, config.rule_set)
    print(f"已读取规则集文件: {config.rule_set}规则集.md")

    prompt1 = PROMPT_GEN1.format(
        rule_id=config.rule_id,
        rule_set=config.rule_set,
        file_content=file_content
    )
    rule_description = bot.query(prompt1)

    prompt2 = PROMPT_GEN2.format(
        rule_set=config.rule_set,
        rule_id=config.rule_id,
        rule_description=rule_description
    )
    response = bot.query(prompt2)
    code_map = extract_multi_code(response)

    # 四类用例：violate(违规)、comply(合规)、fn(漏报边界)、fp(误报边界)
    case_types = [
        ("violate", f"{config.rule_id}_violate.cpp", f"报出{config.rule_set}.{config.rule_id}缺陷"),
        ("comply",  f"{config.rule_id}_comply.cpp",  f"不应报出{config.rule_set}.{config.rule_id}缺陷"),
        ("fn",      f"{config.rule_id}_fn.cpp",      f"报出{config.rule_set}.{config.rule_id}缺陷"),
        ("fp",      f"{config.rule_id}_fp.cpp",      f"不应报出{config.rule_set}.{config.rule_id}缺陷"),
    ]

    missing = [t[0] for t in case_types if t[0] not in code_map]
    if missing:
        raise RuntimeError(f"nanobot 生成 C 代码不完整，缺少: {', '.join(missing)}")

    source_dir = os.path.join(script_dir, '用例库', config.rule_set)
    os.makedirs(source_dir, exist_ok=True)

    for key, name, expected in case_types:
        source_path = os.path.join(source_dir, name)
        with open(source_path, 'w', encoding='utf-8') as f:
            f.write(code_map[key])
        print(f"已生成测试用例: {source_path}")
        append_relation(script_dir, config.rule_set, config.rule_id, name, expected)
        print(f"已追加关联记录: {config.rule_set}——{config.rule_id}——{name}——{expected}")

    # 主流程使用违规用例
    config.source_file = os.path.abspath(os.path.join(source_dir, f"{config.rule_id}_violate.cpp"))
    config.expected_result = f"报出{config.rule_set}.{config.rule_id}缺陷"


def main() -> None:
    """入口：校验参数、初始化、进入主循环。"""
    config = parse_args()

    # 1. 校验 clang.exe
    if not os.path.isfile(config.clang_path):
        print(f"错误：clang.exe 不存在：{config.clang_path}", file=sys.stderr)
        sys.exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 2. 启动 nanobot（提前启动，自动生成和主循环共用）
    bot = NanobotInterface()
    bot.start()

    try:
        # 3. 解析用例来源
        records = lookup_all_relations(script_dir, config.rule_set, config.rule_id)

        if not records:
            existing = find_source_by_rule_id(script_dir, config.rule_set, config.rule_id)
            if existing:
                # 兜底：有文件无记录，补一条记录
                config.expected_result = f"报出{config.rule_set}.{config.rule_id}缺陷"
                append_relation(script_dir, config.rule_set, config.rule_id,
                              os.path.basename(existing), config.expected_result)
                records = [(os.path.basename(existing), config.expected_result)]
            else:
                auto_generate_testcase(script_dir, config, bot)
                records = lookup_all_relations(script_dir, config.rule_set, config.rule_id)
                if not records:
                    raise RuntimeError("自动生成后仍未找到关联记录")

        # 4. 构建 CaseInfo 列表
        source_dir = os.path.join(script_dir, '用例库', config.rule_set)
        case_names = {
            "_violate": "违规用例 (violate)",
            "_comply":  "合规用例 (comply)",
            "_fn":      "漏报边界 (fn)",
            "_fp":      "误报边界 (fp)",
        }
        cases = []
        for source_name, expected in records:
            source_path = find_source_file(script_dir, config.rule_set, source_name)
            # 根据文件名推断用例名称
            for suffix, label in case_names.items():
                if suffix in source_name:
                    name = label
                    break
            else:
                name = source_name
            # 创建副本
            copy_path = copy_to_workdir(script_dir, config.rule_set, source_path)
            cases.append(CaseInfo(
                name=name, source_path=source_path,
                copy_path=copy_path, expected=expected
            ))

        # 5. 汇总信息
        print(f"规则集: {config.rule_set}")
        print(f"规则 ID: {config.rule_id}")
        for c in cases:
            print(f"  {c.name}: {os.path.basename(c.source_path)} -> {c.expected}")
        print("-" * 50)

        # 6. 进入主循环
        main_loop(config, cases, bot, script_dir)

    except KeyboardInterrupt:
        print("\n用户中断，脚本退出。")
    except TimeoutError as e:
        print(f"\n错误：{e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"\n错误：{e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"\n错误：nanobot 进程异常：{e}", file=sys.stderr)
        sys.exit(1)
    finally:
        bot.close()


if __name__ == '__main__':
    main()
