"""
EMQX 连接问题排查脚本 (Windows版本)
使用方法: python emqx_diagnose.py
"""
import os
import sys
import socket
import subprocess
import time
import json
from datetime import datetime


def run_cmd(cmd, timeout=10):
    """运行命令并返回输出"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='utf-8',
            errors='ignore'
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "命令执行超时"
    except Exception as e:
        return -1, "", str(e)


def print_header(title):
    """打印标题"""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)


def print_result(success, message):
    """打印检查结果"""
    icon = "✅" if success else "❌"
    print(f"{icon} {message}")


def check_ping(host):
    """检查是否能 ping 通目标主机"""
    print_header("1. 网络连通性检查")

    try:
        # Windows ping 命令使用 -n 指定次数
        cmd = f"ping -n 3 -w 3000 {host}"
        code, stdout, stderr = run_cmd(cmd)

        if code == 0 and "TTL=" in stdout:
            # 从输出中提取延迟信息
            lines = stdout.split('\n')
            for line in lines:
                if "平均" in line or "Average" in line:
                    print_result(True, f"可以 ping 通 {host}")
                    print(f"   详情: {line.strip()}")
                    return True
            print_result(True, f"可以 ping 通 {host}")
            return True
        else:
            print_result(False, f"无法 ping 通 {host}")
            print(f"   命令: {cmd}")
            if stderr:
                print(f"   错误: {stderr}")
            return False
    except Exception as e:
        print_result(False, f"Ping 检查失败: {e}")
        return False


def check_port(host, port):
    """检查端口是否开放"""
    print_header("2. 端口连通性检查")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)

    try:
        result = sock.connect_ex((host, port))
        if result == 0:
            print_result(True, f"端口 {port} 开放 ({host}:{port})")

            # 尝试读取横幅（如果有）
            try:
                sock.settimeout(2)
                banner = sock.recv(1024)
                if banner:
                    print(f"   端口横幅: {banner[:100]}...")
            except:
                pass

            sock.close()
            return True
        else:
            error_msg = socket.errorTab.get(result, f"错误码: {result}")
            print_result(False, f"端口 {port} 关闭 ({host}:{port})")
            print(f"   原因: {error_msg}")
            return False
    except socket.timeout:
        print_result(False, f"连接端口 {port} 超时")
        return False
    except Exception as e:
        print_result(False, f"端口检查异常: {e}")
        return False
    finally:
        sock.close()


def check_firewall(port):
    """检查 Windows 防火墙设置"""
    print_header("3. Windows 防火墙检查")

    try:
        # 检查防火墙状态
        cmd = 'netsh advfirewall show allprofiles state'
        code, stdout, stderr = run_cmd(cmd)

        if code == 0:
            if "ON" in stdout:
                print("⚠️  Windows 防火墙已启用")

                # 检查是否有入站规则
                cmd = f'netsh advfirewall firewall show rule name=all dir=in | findstr "{port}"'
                code, stdout, stderr = run_cmd(cmd)

                if code == 0 and str(port) in stdout:
                    print_result(True, f"找到端口 {port} 的入站规则")
                else:
                    print_result(False, f"未找到端口 {port} 的入站规则")
                    print("   建议: 添加防火墙规则允许端口 1883")
                    print(
                        "   命令: netsh advfirewall firewall add rule name=\"MQTT 1883\" dir=in action=allow protocol=TCP localport=1883")
            else:
                print_result(True, "Windows 防火墙已关闭")
        else:
            print("⚠️  无法检查防火墙状态")
    except Exception as e:
        print(f"   防火墙检查异常: {e}")


def check_dns(host):
    """检查 DNS 解析"""
    print_header("4. DNS 解析检查")

    try:
        ip = socket.gethostbyname(host)
        print_result(True, f"DNS 解析成功: {host} -> {ip}")

        # 尝试反向解析
        try:
            hostname = socket.gethostbyaddr(ip)[0]
            print(f"   反向解析: {ip} -> {hostname}")
        except:
            print(f"   反向解析: 无法解析 {ip}")

        return ip
    except socket.gaierror:
        print_result(False, f"DNS 解析失败: {host}")
        print("   可能原因: 主机名不存在或网络配置问题")
        return None
    except Exception as e:
        print_result(False, f"DNS 检查异常: {e}")
        return None


def check_hosts_file(host):
    """检查 hosts 文件中的配置"""
    print_header("5. Hosts 文件检查")

    hosts_path = r"C:\Windows\System32\drivers\etc\hosts"

    try:
        with open(hosts_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        lines = content.split('\n')
        found = False
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and host in line:
                print(f"⚠️  在 hosts 文件中找到: {line}")
                found = True

        if not found:
            print("✅ Hosts 文件中未找到相关配置")
        return found
    except Exception as e:
        print(f"⚠️  无法读取 hosts 文件: {e}")
        return False


def check_proxy_settings():
    """检查代理设置"""
    print_header("6. 代理设置检查")

    # 检查环境变量
    proxies = []
    for var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
        if var in os.environ:
            proxies.append(f"{var}={os.environ[var]}")

    if proxies:
        print("⚠️  检测到代理设置:")
        for proxy in proxies:
            print(f"   {proxy}")
        print("   注意: 代理可能影响本地网络连接")
        return True
    else:
        print("✅ 未检测到代理设置")
        return False


def check_python_mqtt_lib():
    """检查 Python MQTT 库"""
    print_header("7. Python 环境检查")

    try:
        import paho.mqtt.client as mqtt
        version = mqtt.__version__ if hasattr(mqtt, '__version__') else '未知'
        print_result(True, f"paho-mqtt 已安装 (版本: {version})")
        return True
    except ImportError:
        print_result(False, "paho-mqtt 未安装")
        print("   安装命令: pip install paho-mqtt")
        return False


def test_mqtt_connection(host, port, username=None, password=None):
    """测试 MQTT 连接"""
    print_header("8. MQTT 连接测试")

    try:
        import paho.mqtt.client as mqtt

        client = mqtt.Client()
        client.on_connect = lambda client, userdata, flags, rc: mqtt_on_connect(client, userdata, flags, rc)
        client.on_log = lambda client, userdata, level, buf: mqtt_on_log(client, userdata, level, buf)

        # 设置连接参数
        if username:
            client.username_pw_set(username, password)

        client.connect_async(host, port, 60)
        client.loop_start()

        # 等待连接结果
        for i in range(10):
            if hasattr(client, '_connected'):
                break
            time.sleep(0.5)

        client.loop_stop()

        if getattr(client, '_connected', False):
            print_result(True, "MQTT 连接成功!")
            return_code = getattr(client, '_return_code', 0)

            # 尝试订阅测试主题
            try:
                result, mid = client.subscribe("$SYS/#", 0)
                print(f"   测试订阅: 结果={result}, MID={mid}")
            except:
                pass

            client.disconnect()
            return True
        else:
            rc = getattr(client, '_return_code', -1)
            print_result(False, f"MQTT 连接失败 (返回码: {rc})")

            # 解释返回码
            rc_descriptions = {
                0: "连接成功",
                1: "协议版本错误",
                2: "客户端标识无效",
                3: "服务器不可用",
                4: "用户名或密码错误",
                5: "未授权",
                6: "意外错误"
            }

            if rc in rc_descriptions:
                print(f"   原因: {rc_descriptions[rc]}")

                if rc == 4:
                    print("   建议: 检查用户名和密码是否正确")
                elif rc == 5:
                    print("   建议: 检查用户是否有访问权限")

            return False

    except ImportError:
        print("❌ 无法导入 paho-mqtt 库")
        return False
    except Exception as e:
        print_result(False, f"MQTT 测试异常: {e}")
        return False


def mqtt_on_connect(client, userdata, flags, rc):
    """MQTT 连接回调"""
    client._connected = True
    client._return_code = rc


def mqtt_on_log(client, userdata, level, buf):
    """MQTT 日志回调"""
    print(f"   MQTT 日志: {buf}")


def check_network_interface():
    """检查网络接口"""
    print_header("9. 网络接口检查")

    try:
        cmd = "ipconfig /all"
        code, stdout, stderr = run_cmd(cmd)

        if code == 0:
            lines = stdout.split('\n')
            for i, line in enumerate(lines):
                if "IPv4 地址" in line or "IPv4 Address" in line:
                    ip_line = line.strip()
                    # 获取下一行通常是子网掩码
                    if i + 1 < len(lines):
                        subnet_line = lines[i + 1].strip()
                        print(f"   {ip_line}")
                        print(f"   {subnet_line}")
                    else:
                        print(f"   {ip_line}")
            print("✅ 网络接口检查完成")
        else:
            print("⚠️  无法获取网络接口信息")
    except Exception as e:
        print(f"⚠️  网络接口检查异常: {e}")


def check_route_table(host):
    """检查路由表"""
    print_header("10. 路由表检查")

    try:
        cmd = "route print"
        code, stdout, stderr = run_cmd(cmd)

        if code == 0:
            lines = stdout.split('\n')

            # 查找默认路由
            default_route_found = False
            for line in lines:
                if "0.0.0.0" in line and "0.0.0.0" in line:
                    parts = [p for p in line.split(' ') if p]
                    if len(parts) >= 3:
                        print(f"   默认路由: 网关={parts[2]}, 接口={parts[3] if len(parts) > 3 else 'N/A'}")
                        default_route_found = True
                        break

            if not default_route_found:
                print("⚠️  未找到默认路由")

        else:
            print("⚠️  无法获取路由表")
    except Exception as e:
        print(f"⚠️  路由表检查异常: {e}")


def check_emqx_status(host, port):
    """检查 EMQX 服务状态（通过 HTTP API）"""
    print_header("11. EMQX 服务状态检查")

    try:
        import urllib.request
        import urllib.error

        # EMQX Dashboard 通常是 18083 端口
        dashboard_url = f"http://{host}:18083/api/v5/nodes"

        try:
            req = urllib.request.Request(dashboard_url)
            req.add_header('Accept', 'application/json')

            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = response.read().decode('utf-8')
                    try:
                        nodes = json.loads(data)
                        if nodes and len(nodes) > 0:
                            node = nodes[0]
                            print_result(True, "EMQX Dashboard 可访问")
                            print(f"   节点: {node.get('node', '未知')}")
                            print(f"   版本: {node.get('version', '未知')}")
                            print(f"   运行时间: {node.get('uptime', '未知')}")
                            return True
                    except:
                        print_result(True, "EMQX Dashboard 可访问")
                        return True
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print("⚠️  EMQX Dashboard 需要认证")
            else:
                print(f"⚠️  EMQX Dashboard 返回 HTTP {e.code}")
        except Exception:
            print("⚠️  无法访问 EMQX Dashboard (可能未启用或端口不同)")

        print("   注意: 这仅检查 Dashboard，不影响 MQTT 连接")
        return False
    except Exception as e:
        print(f"⚠️  EMQX 状态检查异常: {e}")
        return False


def generate_summary(results):
    """生成问题总结"""
    print_header("🔍 问题诊断总结")

    issues = []
    recommendations = []

    # 分析结果
    if not results.get('ping', False):
        issues.append("网络不通，无法 ping 通目标主机")
        recommendations.append("1. 检查目标主机是否开机")
        recommendations.append("2. 检查网络连接和VPN设置")
        recommendations.append("3. 确认目标IP地址是否正确")

    if not results.get('port', False):
        issues.append("目标端口无法访问")
        recommendations.append("1. 检查EMQX服务是否正在运行")
        recommendations.append("2. 检查防火墙是否阻止了1883端口")
        recommendations.append("3. 检查EMQX配置中监听地址是否为0.0.0.0")

    if not results.get('mqtt', False):
        issues.append("MQTT连接失败")
        if results.get('ping', False) and results.get('port', False):
            recommendations.append("1. 检查MQTT认证信息（用户名/密码）")
            recommendations.append("2. 检查EMQX客户端认证配置")
            recommendations.append("3. 尝试其他MQTT端口（如8883、8083）")

    if results.get('firewall_issue', False):
        issues.append("防火墙可能阻止了连接")
        recommendations.append("1. 临时关闭防火墙测试")
        recommendations.append("2. 添加防火墙入站规则允许1883端口")

    if results.get('proxy', False):
        issues.append("检测到代理设置，可能影响连接")
        recommendations.append("1. 临时关闭代理设置")
        recommendations.append("2. 将EMQX服务器IP添加到代理例外列表")

    # 输出总结
    if issues:
        print("❌ 发现以下问题:")
        for issue in issues:
            print(f"   • {issue}")

        print("\n💡 建议解决方案:")
        for rec in recommendations:
            print(f"   {rec}")

        print("\n🛠️  快速修复命令:")
        print("   1. 添加防火墙规则:")
        print('      netsh advfirewall firewall add rule name="MQTT" dir=in action=allow protocol=TCP localport=1883')
        print("   2. 临时测试（关闭防火墙）:")
        print("      netsh advfirewall set allprofiles state off")
        print("   3. 检查EMQX服务状态:")
        print("      ssh 到EMQX服务器执行: systemctl status emqx")
    else:
        print("✅ 所有检查通过，请检查其他配置问题")
        print("\n💡 如果仍然无法连接，请检查:")
        print("   1. EMQX服务器上的认证配置")
        print("   2. 客户端代码中的连接参数")
        print("   3. 网络设备（路由器、交换机）的ACL规则")


def main():
    """主函数"""
    print("=" * 80)
    print("EMQX 连接问题诊断工具 (Windows版本)")
    print("=" * 80)

    # 获取目标信息
    target_host = input("请输入 EMQX 服务器地址 [默认: 192.168.13.225]: ").strip()
    if not target_host:
        target_host = "192.168.13.225"

    target_port = input("请输入 EMQX 端口 [默认: 1883]: ").strip()
    if not target_port:
        target_port = 1883
    else:
        target_port = int(target_port)

    use_auth = input("是否使用认证? (y/n) [默认: n]: ").strip().lower()
    username = None
    password = None

    if use_auth == 'y':
        username = input("用户名: ").strip()
        password = input("密码: ").strip()

    print(f"\n开始诊断 {target_host}:{target_port} ...")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 执行各项检查
    results = {}

    results['ping'] = check_ping(target_host)
    results['dns_ip'] = check_dns(target_host)
    results['port'] = check_port(target_host, target_port)
    check_firewall(target_port)
    check_hosts_file(target_host)
    results['proxy'] = check_proxy_settings()
    results['python_lib'] = check_python_mqtt_lib()
    check_network_interface()
    check_route_table(target_host)
    check_emqx_status(target_host, target_port)

    # 最后进行MQTT连接测试
    results['mqtt'] = test_mqtt_connection(target_host, target_port, username, password)

    # 生成总结
    generate_summary(results)

    print("\n" + "=" * 80)
    print("诊断完成!")
    print("=" * 80)

    # 保存结果到文件
    try:
        with open(f"emqx_diagnose_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", 'w', encoding='utf-8') as f:
            f.write(f"EMQX 诊断报告 - {datetime.now()}\n")
            f.write(f"目标: {target_host}:{target_port}\n")
            f.write(f"结果: {'成功' if results.get('mqtt', False) else '失败'}\n")
            f.write("\n详细信息请查看控制台输出。\n")
        print(f"结果已保存到: emqx_diagnose_*.txt")
    except:
        pass


if __name__ == "__main__":
    try:
        main()
        input("\n按 Enter 键退出...")
    except KeyboardInterrupt:
        print("\n\n诊断被用户中断")
    except Exception as e:
        print(f"\n❌ 诊断过程中发生错误: {e}")
        input("\n按 Enter 键退出...")