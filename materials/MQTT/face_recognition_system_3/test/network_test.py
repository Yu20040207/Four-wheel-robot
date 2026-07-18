# 保存为 network_test.py 并运行
import socket
import subprocess
import sys


def test_network():
    target = "192.168.13.225"

    print("=== 网络详细测试 ===")

    # 1. 测试同网段其他设备
    print("\n1. 测试同网段其他设备连通性:")
    for i in range(224, 229):  # 测试 .224 到 .229
        ip = f"192.168.13.{i}"
        if ip == "192.168.13.226":  # 跳过自己
            continue

        try:
            sock = socket.socket()
            sock.settimeout(1)
            result = sock.connect_ex((ip, 22))  # 测试SSH端口
            status = "可达" if result == 0 else "不可达"
            print(f"  {ip}: {status}")
            sock.close()
        except:
            print(f"  {ip}: 测试失败")

    # 2. 测试网关
    print("\n2. 测试网关连通性:")
    sock = socket.socket()
    sock.settimeout(2)
    result = sock.connect_ex(("192.168.13.1", 80))  # 测试网关
    if result == 0:
        print("  ✓ 网关可达")
    else:
        print("  ✗ 网关不可达")
    sock.close()

    # 3. 运行 tracert（Windows的traceroute）
    print("\n3. 路由追踪结果:")
    try:
        result = subprocess.run(
            f"tracert -d -w 1000 {target}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        print(result.stdout[:500])
    except:
        print("  路由追踪失败")

    # 4. 检查 ARP 缓存
    print("\n4. ARP缓存表:")
    try:
        result = subprocess.run(
            "arp -a",
            shell=True,
            capture_output=True,
            text=True
        )
        # 过滤出目标IP相关信息
        for line in result.stdout.split('\n'):
            if target in line or "192.168.13" in line:
                print(f"  {line.strip()}")
    except:
        print("  ARP检查失败")


if __name__ == "__main__":
    test_network()
    input("\n按Enter键退出...")