# OpenMV HTTP Video Stream Server with HTTP API
import sensor
import time
import network
import socket
import json

# ===== 配置区域 =====
SSID = "MTCPC"
KEY = "mt12345mt"
HTTP_PORT = 8080

# ===== 全局变量 =====
wlan = None
server_socket = None
frame_count = 0
last_received_face_id = None

def init_camera():
    """初始化摄像头"""
    sensor.reset()
    sensor.set_pixformat(sensor.RGB565)
    sensor.set_framesize(sensor.QVGA)  # 320x240
    sensor.skip_frames(20)
    sensor.set_auto_whitebal(False)
    print("摄像头初始化完成 - 分辨率: {}x{}".format(sensor.width(), sensor.height()))

def connect_wifi_robust():
    """健壮的WiFi连接函数"""
    global wlan

    # 使用WINC1500 WiFi模块
    wlan = network.WINC()

    max_retries = 5
    for attempt in range(max_retries):
        print("\n=== WiFi连接尝试 {}/{} ===".format(attempt + 1, max_retries))

        try:
            # 检查是否已连接
            if wlan.isconnected():
                current_ip = wlan.ifconfig()[0]
                if current_ip != '0.0.0.0':
                    print("已连接到WiFi")
                    print("IP地址:", current_ip)
                    return True
                else:
                    print("检测到无效IP，重新连接...")
                    wlan.disconnect()
                    time.sleep_ms(2000)

            # 连接WiFi
            print("连接WiFi: {}...".format(SSID))
            wlan.connect(SSID, key=KEY, security=wlan.WPA_PSK)

            # 等待连接，最多30秒
            timeout = 30
            connected = False
            while timeout > 0:
                if wlan.isconnected():
                    ip_info = wlan.ifconfig()
                    ip_address = ip_info[0]

                    if ip_address != '0.0.0.0':
                        print("\n✓ WiFi连接成功!")
                        print("IP地址:", ip_address)
                        print("子网掩码:", ip_info[1])
                        print("网关:", ip_info[2])
                        print("DNS:", ip_info[3])
                        return True
                    else:
                        print("获取到无效IP，重新连接...")
                        break

                time.sleep_ms(1000)
                timeout -= 1
                if timeout % 5 == 0:
                    print("等待连接... {}秒".format(timeout))

            print("WiFi连接超时")

        except Exception as e:
            print("WiFi连接错误:", e)

        # 重试前等待
        if attempt < max_retries - 1:
            wait_time = (attempt + 1) * 3
            print("等待{}秒后重试...".format(wait_time))
            time.sleep_ms(wait_time * 1000)

    print("✗ 所有WiFi连接尝试失败")
    return False

def send_http_response(client, code, content_type, content):
    """发送HTTP响应"""
    try:
        response = "HTTP/1.1 {} OK\r\n".format(code)
        response += "Content-Type: {}\r\n".format(content_type)
        response += "Access-Control-Allow-Origin: *\r\n"  # 允许跨域
        response += "Access-Control-Allow-Methods: GET, POST\r\n"

        if isinstance(content, str):
            content = content.encode('utf-8')

        response += "Content-Length: {}\r\n".format(len(content))
        response += "Connection: close\r\n"
        response += "\r\n"

        client.send(response.encode('utf-8'))
        client.send(content)
        return True
    except Exception as e:
        print("发送HTTP响应错误:", e)
        return False

def send_mjpeg_frame(client, jpeg_data):
    """发送单个MJPEG帧"""
    try:
        frame_header = "--frame\r\n"
        frame_header += "Content-Type: image/jpeg\r\n"
        frame_header += "Content-Length: {}\r\n".format(len(jpeg_data))
        frame_header += "\r\n"

        client.send(frame_header.encode())
        client.send(jpeg_data)
        client.send("\r\n".encode())
        return True
    except Exception as e:
        print("发送帧错误:", e)
        return False

def parse_request(data):
    """解析HTTP请求"""
    try:
        lines = data.decode().split('\r\n')
        if not lines:
            return None, None, {}

        first_line = lines[0].split(' ')
        if len(first_line) < 2:
            return None, None, {}

        method = first_line[0]
        path = first_line[1]

        # 解析查询参数
        headers = {}
        body = None
        content_length = 0

        # 解析头部
        for i in range(1, len(lines)):
            line = lines[i]
            if line == '':
                # 空行之后是body
                if len(lines) > i + 1:
                    body = lines[i + 1]
                break
            if ': ' in line:
                key, value = line.split(': ', 1)
                headers[key.lower()] = value
                if key.lower() == 'content-length':
                    content_length = int(value)

        return method, path, headers
    except Exception as e:
        print("解析请求错误:", e)
        return None, None, {}

def handle_face_id(client, data):
    """处理人脸ID请求"""
    global last_received_face_id

    try:
        # 解析JSON数据
        if data:
            try:
                face_data = json.loads(data)
                face_id = face_data.get('face_id')

                if face_id is not None:
                    # 避免重复处理相同的人脸ID
                    if last_received_face_id != face_id:
                        last_received_face_id = face_id
                        print("=" * 50)
                        print("收到人脸ID: {}".format(face_id))
                        print("时间: {}".format(time.localtime()))
                        print("=" * 50)

                        # 处理人脸检测
                        handle_face_detected(face_id)

                        response = {"status": "success", "message": "人脸ID接收成功", "face_id": face_id}
                        send_http_response(client, 200, "application/json", json.dumps(response))
                    else:
                        response = {"status": "success", "message": "重复的人脸ID，已忽略", "face_id": face_id}
                        send_http_response(client, 200, "application/json", json.dumps(response))
                else:
                    response = {"status": "error", "message": "缺少face_id参数"}
                    send_http_response(client, 400, "application/json", json.dumps(response))

            except ValueError:
                response = {"status": "error", "message": "无效的JSON数据"}
                send_http_response(client, 400, "application/json", json.dumps(response))
        else:
            response = {"status": "error", "message": "请求体为空"}
            send_http_response(client, 400, "application/json", json.dumps(response))

    except Exception as e:
        print("处理人脸ID请求错误:", e)
        response = {"status": "error", "message": "服务器内部错误"}
        send_http_response(client, 500, "application/json", json.dumps(response))

def handle_face_detected(face_id):
    """处理检测到的人脸"""
    try:
        face_num = int(face_id)
        print("执行人脸 {} 对应的操作".format(face_num))

        # 根据人脸ID执行不同的操作
        if face_num == 1:
            print("🎉 欢迎用户1！")
            # 执行操作1，比如点亮LED等
        elif face_num == 2:
            print("🎉 欢迎用户2！")
            # 执行操作2
        elif face_num == 3:
            print("🎉 欢迎用户3！")
            # 执行操作3
        else:
            print("👤 未知用户: {}".format(face_num))

    except ValueError:
        print("无效的人脸ID格式: {}".format(face_id))

def handle_root(client, client_ip):
    """处理根路径请求"""
    ip_address = wlan.ifconfig()[0]

    html = """<!DOCTYPE html>
<html>
<head>
    <title>OpenMV实时画面</title>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial; text-align: center; margin: 20px; }
        .container { max-width: 400px; margin: 0 auto; }
        .status { background: #f0f0f0; padding: 10px; margin: 10px 0; border-radius: 5px; }
        .api-status { color: #666; font-size: 14px; margin-top: 10px; }
        .face-id { background: #e8f5e8; padding: 10px; margin: 10px 0; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>OpenMV实时画面</h1>
        <div class="status">
            <div>IP: """ + ip_address + """:""" + str(HTTP_PORT) + """</div>
            <div>API状态: <span id="apiStatus">运行中</span></div>
        </div>
        <img id="video" src="/video" width="320" height="240" alt="视频流">
        <div class="face-id">
            <h3>人脸ID接收API</h3>
            <p>端点: POST /face_id</p>
            <p>参数: {"face_id": 数字}</p>
            <div id="lastFaceId">最后收到的人脸ID: 无</div>
        </div>
    </div>

    <script>
        // 更新最后收到的人脸ID
        function updateLastFaceId() {
            // 这里可以通过轮询 /status 端点来更新
        }
        setInterval(updateLastFaceId, 3000);
    </script>
</body>
</html>"""

    send_http_response(client, 200, "text/html", html)
    print("已发送HTML页面到客户端 {}".format(client_ip))

def handle_favicon(client, client_ip):
    """处理favicon请求"""
    send_http_response(client, 404, "text/plain", "Not Found")

def handle_status(client, client_ip):
    """处理状态请求"""
    global last_received_face_id

    status_info = {
        "status": "online",
        "frame_count": frame_count,
        "resolution": "{}x{}".format(sensor.width(), sensor.height()),
        "last_face_id": last_received_face_id,
        "api_endpoints": [
            {"method": "GET", "path": "/", "description": "主页"},
            {"method": "GET", "path": "/video", "description": "视频流"},
            {"method": "POST", "path": "/face_id", "description": "接收人脸ID"},
            {"method": "GET", "path": "/status", "description": "状态信息"}
        ]
    }

    send_http_response(client, 200, "application/json", json.dumps(status_info))

def handle_video(client, client_ip):
    """处理视频流请求"""
    global frame_count

    print("开始视频流传输到客户端: {}".format(client_ip))

    # 发送MJPEG流头
    try:
        header = "HTTP/1.1 200 OK\r\n"
        header += "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
        header += "Connection: close\r\n"
        header += "Cache-Control: no-cache\r\n"
        header += "Access-Control-Allow-Origin: *\r\n"
        header += "\r\n"
        client.send(header.encode())
    except Exception as e:
        print("发送视频头错误:", e)
        return

    clock = time.clock()
    frames_sent = 0
    first_frame_sent = False

    try:
        while True:
            clock.tick()

            # 捕获图像
            img = sensor.snapshot()

            # 压缩为JPEG
            jpeg = img.compress(quality=80)

            # 检查JPEG数据是否有效
            if len(jpeg) < 100:
                continue

            # 发送帧
            if send_mjpeg_frame(client, jpeg):
                frame_count += 1
                frames_sent += 1

                # 第一帧发送成功后立即打印状态
                if not first_frame_sent:
                    print("✓ 第一帧已发送到客户端 {} (大小: {} bytes)".format(client_ip, len(jpeg)))
                    first_frame_sent = True
            else:
                print("发送帧失败，客户端可能已断开")
                break

            # 每5秒输出一次状态
            current_time = time.ticks_ms()
            if time.ticks_diff(current_time, time.ticks_ms()) > 5000:
                fps = clock.fps()
                print("客户端 {}: 已发送 {} 帧, {:.1f} FPS".format(client_ip, frames_sent, fps))

            # 控制帧率
            time.sleep_ms(100)

            # 非阻塞检查客户端是否断开
            try:
                client.setblocking(False)
                data = client.recv(1)
                if not data:
                    break
            except:
                pass
            finally:
                client.setblocking(True)

    except Exception as e:
        print("视频流错误:", e)

    print("客户端 {} 断开，共发送 {} 帧".format(client_ip, frames_sent))

def main():
    """主函数"""
    global server_socket, frame_count

    print("=== OpenMV HTTP视频流服务器 ===")
    print("WiFi网络: {}".format(SSID))
    print("HTTP端口: {}".format(HTTP_PORT))
    print("API端点:")
    print("  GET  /              - 主页")
    print("  GET  /video         - 视频流")
    print("  POST /face_id       - 接收人脸ID")
    print("  GET  /status        - 状态信息")

    # 初始化硬件
    init_camera()

    # 连接WiFi
    if not connect_wifi_robust():
        print("无法连接WiFi，程序退出")
        return

    # 创建服务器socket
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_address = ('0.0.0.0', HTTP_PORT)
        server_socket.bind(server_address)
        server_socket.listen(3)
        server_socket.setblocking(False)
        print("✓ HTTP服务器启动成功")
        print("📱 请用浏览器访问: http://{}:{}".format(wlan.ifconfig()[0], HTTP_PORT))
        print("⏳ 等待客户端连接...")
    except Exception as e:
        print("✗ 启动服务器失败:", e)
        return

    frame_count = 0

    # 主循环
    while True:
        try:
            # 接受HTTP连接（非阻塞）
            try:
                client, addr = server_socket.accept()
                client_ip = addr[0]
                print("\n📞 新客户端连接: {}".format(client_ip))

                # 接收请求
                data = client.recv(4096)  # 增加缓冲区大小以处理POST请求
                if not data:
                    client.close()
                    continue

                # 解析请求
                method, path, headers = parse_request(data)
                print("请求: {} {}".format(method, path if path else "unknown"))

                if method == "GET":
                    if path == "/" or path == "/index.html":
                        handle_root(client, client_ip)
                    elif path.startswith("/video"):
                        handle_video(client, client_ip)
                    elif path == "/favicon.ico":
                        handle_favicon(client, client_ip)
                    elif path == "/status":
                        handle_status(client, client_ip)
                    else:
                        # 重定向到主页
                        send_http_response(client, 302, "text/plain", "")
                        client.send("Location: /\r\n\r\n".encode())

                elif method == "POST":
                    if path == "/face_id":
                        # 提取POST数据
                        content_length = headers.get('content-length', 0)
                        body = ""
                        if content_length > 0:
                            # 这里简化处理，实际应该根据content_length读取完整body
                            lines = data.decode().split('\r\n')
                            for i in range(len(lines)):
                                if lines[i] == '' and i + 1 < len(lines):
                                    body = lines[i + 1]
                                    break
                        handle_face_id(client, body)
                    else:
                        send_http_response(client, 404, "application/json", json.dumps({"status": "error", "message": "端点不存在"}))
                else:
                    send_http_response(client, 405, "text/plain", "Method Not Allowed")

                client.close()
                print("客户端 {} 断开连接".format(client_ip))

            except OSError:
                # 没有客户端连接是正常的，继续循环
                pass

        except Exception as e:
            print("服务器错误:", e)
            try:
                if client:
                    client.close()
            except:
                pass
            time.sleep_ms(100)

        # 短暂延时，避免过度占用CPU
        time.sleep_ms(10)

# 启动程序
try:
    main()
except KeyboardInterrupt:
    print("\n程序被用户中断")
except Exception as e:
    print("程序错误:", e)
finally:
    if server_socket:
        server_socket.close()
    print("服务器关闭")
