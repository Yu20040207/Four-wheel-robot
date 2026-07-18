# test_installation.py - 测试包是否能正常导入
import sys

print("=" * 50)
print("测试包导入状态")
print("=" * 50)

try:
    import numpy as np

    print(f"✅ NumPy 导入成功 - 版本: {np.__version__}")
except ImportError as e:
    print(f"❌ NumPy 导入失败: {e}")

try:
    import cv2

    print(f"✅ OpenCV 导入成功 - 版本: {cv2.__version__}")
except ImportError as e:
    print(f"❌ OpenCV 导入失败: {e}")

try:
    import paho.mqtt.client as mqtt

    print("✅ paho-mqtt 导入成功")
except ImportError as e:
    print(f"❌ paho-mqtt 导入失败: {e}")

try:
    from loguru import logger

    print("✅ loguru 导入成功")
except ImportError as e:
    print(f"❌ loguru 导入失败: {e}")

try:
    from PIL import Image

    print("✅ Pillow 导入成功")
except ImportError as e:
    print(f"❌ Pillow 导入失败: {e}")

print("\n" + "=" * 50)
print("测试OpenCV基本功能")
print("=" * 50)

try:
    # 测试OpenCV基本功能
    import cv2
    import numpy as np

    # 创建一个测试图像
    test_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)

    # 测试人脸检测器加载
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    if face_cascade.empty():
        print("⚠️  Haar级联分类器加载失败")
    else:
        print("✅ Haar级联分类器加载成功")

    # 测试图像处理
    gray = cv2.cvtColor(test_image, cv2.COLOR_BGR2GRAY)
    print(f"✅ 图像处理测试通过 - 图像形状: {gray.shape}")

    print("🎉 所有测试通过！OpenCV功能正常")

except Exception as e:
    print(f"❌ OpenCV功能测试失败: {e}")
