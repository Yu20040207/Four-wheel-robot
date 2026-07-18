@echo off
chcp 65001
title 独立版人脸识别MQTT服务

echo ===============================================
echo    独立版人脸识别MQTT服务
echo    （无OpenCV依赖，完全模拟版本）
echo ===============================================
echo.

echo 检查Python环境...
python --version
echo.

echo 检查必要依赖...
pip list | findstr paho-mqtt
echo.

echo 启动服务...
echo 按 Ctrl+C 停止服务
echo ===============================================
echo.

python standalone_face_recognition.py

pause