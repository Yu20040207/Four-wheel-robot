#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EMQX 连接问题诊断脚本
适用于 Windows 系统
"""

import os
import sys
import socket
import subprocess
import time
import re
import json
import platform
from datetime import datetime
from pathlib import Path


# 颜色输出
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_color(text, color=Colors.WHITE, bold=False):
    """彩色打印"""
    style = Colors.BOLD if bold else ""
    print(f"{style}{color}{text}{Colors.RESET}")


def print_section(title):
    """打印章节标题"""
    print_color(f"\n{title}", Colors.CYAN, True)
    print_color("=" * 60, Colors.CYAN)


def print_status(message, success=True):
    """打印状态信息"""
    if success:
        print_color(f"  ✓ {message}", Colors.GREEN)
    else:
        print_color(f"  ✗ {message}", Colors.RED)


def print_warning(message):
    """打印警告信息"""
    print_color(f"  ⚠ {message}", Colors.YELLOW)


def print_info(message):
    """打印信息"""
    print_color(f"  ℹ {message}", Colors.BLUE)


def check_system_info():
    """检查系统信息"""
    print_section("1. 系统信息检查")

    system = platform.system()
    release = platform.release()
    version = platform.version()
    machine = platform.machine()

    print_info(f"操作系统: {system} {release}")
    print_info(f"系统版本: {version}")
    print_info(f"系统架构: {machine}")
    print_info(f"Python版本: {platform.python_version()}")

    # 检查是否是管理员权限
    try:
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        if is_admin:
            print_status("权限: 管理员权限", True)
        else:
            print_warning("权限: 普通用户权限 (部分功能可能需要管理员权限)")
    except:
        print_warning("无法检查管理员权限")


def check_emqx_service():
    """检查EMQX服务状态"""
    print_section("2. EMQX 服务状态检查")

    service_names = ["emqx", "EMQX", "EMQ X Broker"]
    emqx_service = None
    service_status = "未找到"

    for service_name in service_names:
        try:
            # 使用sc命令查询服务状态
            result = subprocess.run(
                ["sc", "query", service_name],
                capture_output=True,
                text=True,
                encoding='gbk',
                errors='ignore'
            )

            if result.returncode == 0:
                emqx_service = service_name
                # 解析服务状态
                for line in result.stdout.split('\n'):
                    if "STATE" in line.upper():
                        match = re.search(r'STATE\s*:\s*\d+\s*(\w+)', line.upper())
                        if match:
                            service_status = match.group(1)
                            break
                break
        except Exception as e:
            continue

    if emqx_service:
        print_status(f"找到 EMQX 服务: {emqx_service}", True)
        print_info(f"服务状态: {service_status}")

        if "RUNNING" in service_status.upper():
            print_status("服务正在运行", True)
        else:
            print_warning("服务未运行")
            print_info("尝试启动服务...")
            try:
                subprocess.run(["net", "start", emqx_service], check=False)
                time.sleep(3)
                # 重新检查状态
                result = subprocess.run(
                    ["sc", "query", emqx_service],
                    capture_output=True,
                    text=True,
                    encoding='gbk',
                    errors='ignore'
                )
                if "RUNNING" in result.stdout.upper():
                    print_status("服务启动成功", True)
                else:
                    print_status("服务启动失败", False)
            except Exception as e:
                print_status(f"启动失败: {str(e)}", False)
    else:
        print_status("未找到 EMQX 服务", False)
        print_info("请检查 EMQX 是否已安装")


def check_port_usage():
    """检查端口占用情况"""
    print_section("3. 端口占用检查")

    emqx_ports = [
        (1883, "MQTT TCP"),
        (8883, "MQTT SSL"),
        (8083, "MQTT WebSocket"),
        (8084, "MQTT WebSocket SSL"),
        (18083, "Dashboard HTTP"),
        (18084, "Dashboard HTTPS"),
        (4369, "Erlang 节点通信")
    ]

    try:
        # 使用 netstat 命令
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore'
        )

        occupied_ports = []

        for port, desc in emqx_ports:
            # 检查端口是否在 netstat 输出中
            lines = [line for line in result.stdout.split('\n') if f":{port} " in line]

            if lines:
                # 提取进程ID
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        try:
                            # 获取进程名
                            ps_result = subprocess.run(
                                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
                                capture_output=True,
                                text=True,
                                encoding='gbk',
                                errors='ignore'
                            )
                            if ps_result.returncode == 0:
                                lines2 = ps_result.stdout.strip().split('\n')
                                if len(lines2) > 1:
                                    import csv
                                    reader = csv.reader([lines2[1]])
                                    for row in reader:
                                        if len(row) > 0:
                                            process_name = row[0]
                                            break
                                else:
                                    process_name = "未知进程"
                            else:
                                process_name = "未知进程"
                        except:
                            process_name = "未知进程"

                        print_status(f"端口 {port} ({desc}) 被占用", False)
                        print_info(f"    进程: {process_name} (PID: {pid})")
                        occupied_ports.append((port, desc, process_name, pid))
                        break
            else:
                print_status(f"端口 {port} ({desc}) 可用", True)

        return occupied_ports

    except Exception as e:
        print_status(f"端口检查失败: {str(e)}", False)
        return []


def check_network_connectivity():
    """检查网络连通性"""
    print_section("4. 网络连通性测试")

    test_targets = [
        ("127.0.0.1", "本机环回地址"),
        ("localhost", "本地主机"),
        ("0.0.0.0", "所有地址")
    ]

    test_ports = [1883, 18083]

    for address, desc in test_targets:
        print_info(f"测试连接到: {address} ({desc})")

        # Ping测试
        try:
            # Windows ping
            result = subprocess.run(
                ["ping", "-n", "2", address],
                capture_output=True,
                text=True,
                encoding='gbk',
                errors='ignore',
                timeout=5
            )

            if "TTL=" in result.stdout or "往返行程" in result.stdout:
                print_status(f"    Ping 测试通过", True)
            else:
                print_status(f"    Ping 测试失败", False)
        except Exception as e:
            print_status(f"    Ping 测试异常: {str(e)}", False)

        # 端口测试
        for port in test_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)  # 2秒超时

                start_time = time.time()
                result = sock.connect_ex((address, port))
                end_time = time.time()

                if result == 0:
                    print_status(f"    端口 {port} 连接成功 (耗时: {end_time - start_time:.2f}秒)", True)
                    sock.close()
                else:
                    print_status(f"    端口 {port} 连接失败", False)
            except socket.timeout:
                print_status(f"    端口 {port} 连接超时", False)
            except Exception as e:
                print_status(f"    端口 {port} 连接异常: {str(e)}", False)

        print()


def check_firewall():
    """检查防火墙设置"""
    print_section("5. 防火墙规则检查")

    try:
        # 使用 netsh 命令检查防火墙规则
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", "name=all"],
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore',
            timeout=10
        )

        if result.returncode == 0:
            # 查找 EMQX 相关规则
            lines = result.stdout.split('\n')
            emqx_rules = []
            current_rule = {}

            for line in lines:
                line = line.strip()
                if line and ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip()

                    if key == "规则名称":
                        if current_rule:
                            emqx_rules.append(current_rule)
                        current_rule = {"名称": value}
                    elif current_rule:
                        current_rule[key] = value

            if current_rule:
                emqx_rules.append(current_rule)

            # 过滤出 EMQX 相关规则
            emqx_related = []
            for rule in emqx_rules:
                name = rule.get("名称", "")
                if "emqx" in name.lower() or "mqtt" in name.lower():
                    emqx_related.append(rule)

            if emqx_related:
                print_info(f"找到 {len(emqx_related)} 个 EMQX 相关防火墙规则:")
                for rule in emqx_related:
                    enabled = rule.get("已启用", "否")
                    color = Colors.GREEN if enabled == "是" else Colors.YELLOW
                    print_color(f"    - {rule['名称']}: {enabled}", color)

                    # 显示端口信息
                    for key, value in rule.items():
                        if "端口" in key or "Port" in key:
                            print_info(f"      端口: {value}")
            else:
                print_warning("未找到 EMQX 相关防火墙规则")
                print_info("这可能意味着防火墙阻止了 EMQX 的连接")
        else:
            print_warning("无法检查防火墙规则 (可能需要管理员权限)")

    except Exception as e:
        print_warning(f"防火墙检查失败: {str(e)}")


def check_emqx_processes():
    """检查EMQX相关进程"""
    print_section("6. EMQX 进程检查")

    try:
        # 使用 tasklist 命令
        result = subprocess.run(
            ["tasklist", "/FO", "CSV"],
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore'
        )

        if result.returncode == 0:
            import csv
            import io

            # 查找 EMQX/Erlang 相关进程
            emqx_processes = []
            process_names = ["beam.smp", "erl.exe", "emqx", "erlang"]

            csv_data = io.StringIO(result.stdout)
            reader = csv.reader(csv_data)

            for row in reader:
                if len(row) >= 2:
                    process_name = row[0].strip('"')
                    pid = row[1].strip('"')

                    for target_name in process_names:
                        if target_name.lower() in process_name.lower():
                            emqx_processes.append((process_name, pid))
                            break

            if emqx_processes:
                print_status(f"找到 {len(emqx_processes)} 个 EMQX/Erlang 相关进程:", True)
                for process_name, pid in emqx_processes:
                    print_info(f"    {process_name} (PID: {pid})")

                    # 获取内存使用
                    try:
                        import psutil
                        process = psutil.Process(int(pid))
                        memory_mb = process.memory_info().rss / 1024 / 1024
                        print_info(f"        内存使用: {memory_mb:.2f} MB")
                    except:
                        pass
            else:
                print_status("未找到 EMQX/Erlang 相关进程", False)
        else:
            print_status("无法获取进程列表", False)

    except Exception as e:
        print_status(f"进程检查失败: {str(e)}", False)


def check_emqx_files():
    """检查EMQX文件和日志"""
    print_section("7. EMQX 目录和日志检查")

    # 可能的安装路径
    possible_paths = [
        Path("C:/emqx"),
        Path("C:/Program Files/emqx"),
        Path("C:/Program Files (x86)/emqx"),
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "emqx",
        Path(os.environ.get("SystemDrive", "C:")) / "emqx",
    ]

    emqx_path = None
    for path in possible_paths:
        if path.exists():
            emqx_path = path
            break

    if emqx_path:
        print_status(f"找到 EMQX 目录: {emqx_path}", True)

        # 检查日志文件
        log_file = emqx_path / "log" / "emqx.log"
        if log_file.exists():
            print_status("找到日志文件", True)

            try:
                # 读取最后50行日志
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    last_lines = lines[-50:] if len(lines) > 50 else lines

                # 查找错误日志
                error_lines = []
                for line in last_lines:
                    line_lower = line.lower()
                    if any(keyword in line_lower for keyword in
                           ['error', 'failed', 'crash', 'exception', '拒绝', '失败']):
                        error_lines.append(line.strip())

                if error_lines:
                    print_warning(f"发现 {len(error_lines)} 条错误日志:")
                    for error in error_lines[-5:]:  # 显示最后5条
                        print_color(f"    {error}", Colors.RED)
                else:
                    print_status("日志中没有发现明显错误", True)

            except Exception as e:
                print_warning(f"无法读取日志文件: {str(e)}")
        else:
            print_status("未找到日志文件", False)

        # 检查配置文件
        conf_file = emqx_path / "etc" / "emqx.conf"
        if conf_file.exists():
            print_status("找到配置文件", True)

            try:
                with open(conf_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # 查找监听器配置
                import re
                listeners = re.findall(r'listener\..*?=.*', content, re.IGNORECASE)
                if listeners:
                    print_info("监听器配置:")
                    for listener in listeners[:5]:  # 显示前5个
                        if not listener.strip().startswith('#'):
                            print_info(f"    {listener.strip()}")
            except Exception as e:
                print_warning(f"无法读取配置文件: {str(e)}")
        else:
            print_status("未找到配置文件", False)
    else:
        print_status("未找到 EMQX 安装目录", False)

        # 尝试通过注册表查找
        try:
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EMQX")
                install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                print_info(f"通过注册表找到安装路径: {install_path}")
            except:
                pass
        except:
            pass


def check_mqtt_connection():
    """测试MQTT连接"""
    print_section("8. MQTT 连接测试")

    try:
        # 尝试使用 paho-mqtt 测试连接
        try:
            import paho.mqtt.client as mqtt
            has_mqtt_lib = True
        except ImportError:
            has_mqtt_lib = False
            print_warning("未安装 paho-mqtt 库，使用原始socket测试")

        if has_mqtt_lib:
            client = mqtt.Client()
            client.reconnect_delay_set(min_delay=1, max_delay=2)

            connected = False
            try:
                client.connect("localhost", 1883, 5)
                connected = True
                print_status("MQTT 连接测试成功", True)
            except Exception as e:
                print_status(f"MQTT 连接失败: {str(e)}", False)

            if connected:
                client.disconnect()
        else:
            # 使用socket测试
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)

            try:
                sock.connect(("localhost", 1883))
                print_status("MQTT 端口 (1883) 连接成功", True)

                # 发送简单的MQTT连接请求
                connect_packet = bytearray([
                    0x10, 0x13,  # 固定头部
                    0x00, 0x04, 0x4D, 0x51, 0x54, 0x54,  # 协议名 MQTT
                    0x04,  # 协议级别 4
                    0x02,  # 连接标志
                    0x00, 0x3C,  # 保持连接时间
                    0x00, 0x00  # 客户端ID长度
                ])

                sock.send(connect_packet)
                response = sock.recv(1024)

                if response:
                    print_status("MQTT 协议通信正常", True)
                else:
                    print_warning("MQTT 协议无响应")

                sock.close()
            except socket.timeout:
                print_status("MQTT 端口连接超时", False)
            except ConnectionRefusedError:
                print_status("MQTT 端口连接被拒绝", False)
            except Exception as e:
                print_status(f"MQTT 测试异常: {str(e)}", False)

    except Exception as e:
        print_status(f"MQTT 连接测试失败: {str(e)}", False)


def check_system_resources():
    """检查系统资源"""
    print_section("9. 系统资源检查")

    try:
        import psutil

        # 内存使用
        memory = psutil.virtual_memory()
        print_info(f"内存使用: {memory.percent}%")
        print_info(f"可用内存: {memory.available / 1024 / 1024:.0f} MB")

        if memory.percent > 90:
            print_warning("内存使用率过高，可能影响 EMQX 运行")

        # 磁盘空间
        disk = psutil.disk_usage('C:/')
        print_info(f"C盘使用: {disk.percent}%")
        print_info(f"可用空间: {disk.free / 1024 / 1024 / 1024:.1f} GB")

        if disk.percent > 90:
            print_warning("磁盘空间不足，可能影响 EMQX 运行")

        # CPU使用
        cpu_percent = psutil.cpu_percent(interval=1)
        print_info(f"CPU使用: {cpu_percent}%")

    except ImportError:
        print_warning("未安装 psutil 库，跳过资源检查")
    except Exception as e:
        print_warning(f"资源检查失败: {str(e)}")


def generate_summary(occupied_ports):
    """生成诊断摘要"""
    print_section("诊断摘要")

    print_color("【问题分析】", Colors.MAGENTA, True)

    if occupied_ports:
        print_color("⚠ 发现端口冲突:", Colors.YELLOW, True)
        for port, desc, process_name, pid in occupied_ports:
            print_color(f"  端口 {port} ({desc}) 被 {process_name} (PID: {pid}) 占用", Colors.YELLOW)

    print_color("\n【建议解决方案】", Colors.MAGENTA, True)

    if occupied_ports:
        print_color("1. 解决端口冲突:", Colors.CYAN)
        for port, desc, process_name, pid in occupied_ports:
            print_color(f"   结束进程: taskkill /F /PID {pid}", Colors.WHITE)
            print_color(f"   或修改 EMQX 的 {desc} 端口配置", Colors.WHITE)

    print_color("\n2. 重启 EMQX 服务:", Colors.CYAN)
    print_color("   net stop emqx", Colors.WHITE)
    print_color("   net start emqx", Colors.WHITE)

    print_color("\n3. 检查防火墙:", Colors.CYAN)
    print_color("   临时关闭防火墙测试:", Colors.WHITE)
    print_color("   netsh advfirewall set allprofiles state off", Colors.WHITE)
    print_color("   测试后恢复:", Colors.WHITE)
    print_color("   netsh advfirewall set allprofiles state on", Colors.WHITE)

    print_color("\n4. 检查 EMQX 配置:", Colors.CYAN)
    print_color("   查看配置文件: C:\\emqx\\etc\\emqx.conf", Colors.WHITE)
    print_color("   检查监听器配置是否正确", Colors.WHITE)

    print_color("\n5. 查看详细日志:", Colors.CYAN)
    print_color("   type C:\\emqx\\log\\emqx.log | findstr ERROR", Colors.WHITE)

    print_color("\n6. 重新安装 EMQX:", Colors.CYAN)
    print_color("   如果问题持续，考虑备份配置后重新安装", Colors.WHITE)


def save_diagnostic_report():
    """保存诊断报告到文件"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"emqx_diagnostic_report_{timestamp}.txt"

        # 重定向输出到文件
        original_stdout = sys.stdout

        with open(filename, 'w', encoding='utf-8') as f:
            sys.stdout = f

            # 重新运行诊断
            print_color("EMQX 诊断报告", Colors.CYAN, True)
            print_color(f"生成时间: {datetime.now()}", Colors.CYAN)
            print_color("=" * 60, Colors.CYAN)

            check_system_info()
            check_emqx_service()
            check_port_usage()
            check_network_connectivity()
            check_firewall()
            check_emqx_processes()
            check_emqx_files()
            check_mqtt_connection()
            check_system_resources()

            sys.stdout = original_stdout

        print_color(f"\n诊断报告已保存到: {filename}", Colors.GREEN)
        print_color(f"请将此文件发送给技术支持人员", Colors.CYAN)

    except Exception as e:
        print_warning(f"保存报告失败: {str(e)}")


def main():
    """主函数"""
    print_color("\n" + "=" * 60, Colors.CYAN)
    print_color("        EMQX 连接问题诊断工具", Colors.YELLOW, True)
    print_color("=" * 60, Colors.CYAN)
    print_color(f"开始时间: {datetime.now()}\n", Colors.CYAN)

    try:
        # 检查必要的库
        try:
            import psutil
        except ImportError:
            print_warning("未安装 psutil 库，部分功能受限")
            print_info("可以运行: pip install psutil")

        # 执行所有检查
        check_system_info()
        check_emqx_service()
        occupied_ports = check_port_usage()
        check_network_connectivity()
        check_firewall()
        check_emqx_processes()
        check_emqx_files()
        check_mqtt_connection()
        check_system_resources()

        # 生成摘要
        generate_summary(occupied_ports)

        # 保存报告
        save_diagnostic_report()

        print_color("\n" + "=" * 60, Colors.CYAN)
        print_color("        诊断完成", Colors.GREEN, True)
        print_color("=" * 60, Colors.CYAN)

        print_color("\n按 Enter 键退出...", Colors.WHITE)
        input()

    except KeyboardInterrupt:
        print_color("\n\n用户中断诊断", Colors.YELLOW)
    except Exception as e:
        print_color(f"\n诊断过程中出现错误: {str(e)}", Colors.RED)
        import traceback
        traceback.print_exc()
        print_color("\n按 Enter 键退出...", Colors.WHITE)
        input()


if __name__ == "__main__":
    main()