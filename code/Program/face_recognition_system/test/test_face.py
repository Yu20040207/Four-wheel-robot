import sys

print(f"Python路径: {sys.executable}")
print(f"Python版本: {sys.version}")

try:
    import face_recognition

    print("✅ face_recognition导入成功！")

    # 测试基本功能
    import numpy as np

    test_image = np.zeros((100, 100, 3), dtype=np.uint8)
    face_locations = face_recognition.face_locations(test_image)
    print(f"✅ 人脸检测功能正常，找到 {len(face_locations)} 张人脸")

except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("请在PyCharm终端中运行: pip install face_recognition")
