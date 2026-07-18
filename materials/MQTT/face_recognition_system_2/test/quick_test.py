import paho.mqtt.client as mqtt
import time
import sys


def on_connect(client, userdata, flags, rc):
    """连接回调"""
    if rc == 0:
        print("✅ 连接成功！")
        print(f"   连接返回码: {rc}")
        print(f"   连接标志: {flags}")
    else:
        print(f"❌ 连接失败，返回码: {rc}")
        print("   0: 连接成功")
        print("   1: 协议版本错误")
        print("   2: 客户端ID无效")
        print("   3: 服务器不可用")
        print("   4: 用户名或密码错误")
        print("   5: 未授权")


def on_disconnect(client, userdata, rc):
    """断开连接回调"""
    print(f"📤 断开连接，返回码: {rc}")


def test_connection(host="localhost", port=1883, username=None, password=None):
    """测试连接"""
    print(f"\n🔗 测试连接到: {host}:{port}")
    print(f"   用户名: {username or '未设置'}")
    print(f"   密码: {'已设置' if password else '未设置'}")

    client_id = f"test_{int(time.time())}"
    client = mqtt.Client(client_id=client_id)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    if username and password:
        client.username_pw_set(username, password)

    try:
        # 设置超时时间
        client.connect(host, port, 10)
        client.loop_start()
        time.sleep(3)
        client.loop_stop()
        client.disconnect()
        return True
    except Exception as e:
        print(f"❌ 连接异常: {e}")
        return False


def test_dashboard():
    """测试Dashboard访问"""
    print("\n🌐 测试Dashboard访问...")
    try:
        import urllib.request
        import base64

        # 使用基本认证
        url = "http://localhost:18083/api/v5/status"
        req = urllib.request.Request(url)

        # EMQX 5.x 默认认证
        credentials = base64.b64encode(b"admin:public").decode()
        req.add_header("Authorization", f"Basic {credentials}")

        response = urllib.request.urlopen(req, timeout=5)
        print("✅ Dashboard 访问成功")
        return True
    except Exception as e:
        print(f"❌ Dashboard 访问失败: {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("EMQX 连接测试工具")
    print("=" * 50)

    # 测试不同连接方式
    print("\n测试1: 匿名连接")
    test_connection("localhost", 1883)

    print("\n测试2: 127.0.0.1连接")
    test_connection("127.0.0.1", 1883)

    print("\n测试3: 使用admin/public连接")
    test_connection("localhost", 1883, "admin", "public")

    # 测试Dashboard
    test_dashboard()

    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)

    input("\n按 Enter 键退出...")