# fix_numpy_issue.py
import subprocess
import sys
import os


def run_command(cmd, check=True):
    """运行命令并返回结果"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if check and result.returncode != 0:
            print(f"命令执行失败: {cmd}")
            print(f"错误信息: {result.stderr}")
            return False, result.stdout, result.stderr
        return True, result.stdout, result.stderr
    except Exception as e:
        print(f"执行命令时出错: {e}")
        return False, "", str(e)


def check_current_versions():
    """检查当前安装的版本"""
    print("=" * 60)
    print("检查当前环境状态")
    print("=" * 60)

    # 检查Python版本
    success, stdout, stderr = run_command("python --version", check=False)
    if success:
        print(f"Python版本: {stdout.strip()}")

    # 检查pip版本
    success, stdout, stderr = run_command("pip --version", check=False)
    if success:
        print(f"Pip版本: {stdout.strip()}")

    # 检查已安装的包
    packages_to_check = ["numpy", "opencv-python", "paho-mqtt", "loguru", "Pillow"]

    for package in packages_to_check:
        success, stdout, stderr = run_command(f"pip show {package}", check=False)
        if success and package in stdout:
            # 提取版本信息
            for line in stdout.split('\n'):
                if line.startswith('Version:'):
                    version = line.split(':')[1].strip()
                    print(f"{package}: {version}")
                    break
        else:
            print(f"{package}: 未安装")


def fix_compatibility_issue():
    """修复NumPy兼容性问题"""
    print("\n" + "=" * 60)
    print("开始修复NumPy兼容性问题")
    print("=" * 60)

    # 1. 卸载有问题的包
    print("\n1. 卸载不兼容的包...")
    packages_to_uninstall = ["numpy", "opencv-python", "opencv-contrib-python"]

    for package in packages_to_uninstall:
        print(f"正在卸载 {package}...")
        success, stdout, stderr = run_command(f"pip uninstall -y {package}", check=False)
        if success:
            print(f"✅ {package} 卸载完成")
        else:
            print(f"⚠️  {package} 卸载可能失败或未安装")

    # 2. 安装兼容版本
    print("\n2. 安装兼容版本...")
    compatible_packages = [
        "numpy==1.24.3",
        "opencv-python==4.8.1.78",
        "paho-mqtt==1.6.1",
        "loguru==0.7.0",
        "Pillow==10.0.0"
    ]

    for package_spec in compatible_packages:
        print(f"正在安装 {package_spec}...")
        success, stdout, stderr = run_command(f"pip install {package_spec}")
        if success:
            print(f"✅ {package_spec} 安装成功")
        else:
            print(f"❌ {package_spec} 安装失败")
            print(f"错误信息: {stderr}")

    # 3. 测试导入
    print("\n3. 测试包导入...")
    test_imports = [
        ("numpy", "import numpy as np; print(f'NumPy版本: {np.__version__}')"),
        ("opencv-python", "import cv2; print(f'OpenCV版本: {cv2.__version__}')"),
        ("paho-mqtt", "import paho.mqtt.client as mqtt; print('paho-mqtt导入成功')"),
        ("loguru", "from loguru import logger; print('loguru导入成功')"),
        ("Pillow", "from PIL import Image; print('Pillow导入成功')")
    ]

    all_success = True
    for package_name, test_code in test_imports:
        try:
            exec(test_code)
            print(f"✅ {package_name} 导入测试通过")
        except Exception as e:
            print(f"❌ {package_name} 导入测试失败: {e}")
            all_success = False

    return all_success


def create_requirements_file():
    """创建兼容的requirements文件"""
    requirements_content = """# 兼容的依赖版本（解决NumPy 2.x兼容性问题）
numpy==1.24.3
opencv-python==4.8.1.78
paho-mqtt==1.6.1
loguru==0.7.0
Pillow==10.0.0
python-dateutil==2.8.2
"""

    with open("compatible_requirements.txt", "w", encoding="utf-8") as f:
        f.write(requirements_content)

    print("\n✅ 已创建 compatible_requirements.txt 文件")
    return "compatible_requirements.txt"


def main():
    """主函数"""
    print("NumPy 2.x 兼容性问题修复工具")
    print("此工具将解决OpenCV与NumPy 2.x的兼容性问题")

    # 检查当前状态
    check_current_versions()

    # 询问用户是否继续
    response = input("\n是否继续修复？(y/n): ").lower().strip()
    if response not in ['y', 'yes', '是']:
        print("已取消操作")
        return

    # 执行修复
    success = fix_compatibility_issue()

    if success:
        print("\n" + "=" * 60)
        print("✅ 修复成功！")
        print("=" * 60)

        # 创建兼容的requirements文件
        req_file = create_requirements_file()
        print(f"\n后续可以使用以下命令安装依赖:")
        print(f"pip install -r {req_file}")

        print("\n现在可以运行人脸识别MQTT服务了！")
        print("命令: python main.py")
    else:
        print("\n" + "=" * 60)
        print("❌ 修复过程中遇到问题")
        print("=" * 60)
        print("建议尝试以下替代方案:")
        print("1. 创建新的虚拟环境")
        print("2. 使用Docker容器")
        print("3. 使用简化版代码（不依赖OpenCV）")


if __name__ == "__main__":
    main()