# Four-wheel-robot

四轮底盘机器人相关工程（明添光电）。

## 项目入口

仓库同时包含当前代码、历史程序、硬件资料和独立的上游工程。以下入口根据现有 `code/Program/架构分析.txt` 整理；正式维护范围由团队在[模块责任表](docs/模块责任表.md)中确认。

| 模块 | 路径 |
| --- | --- |
| 底盘与避障 STM32 | `code/Program/STM32_MOTOR/car_6_3(now)/` |
| 机械臂与测距 STM32C8T6 | `code/Program/STM32C8T6/main3.0/` |
| 腰部控制 ESP32 | `code/Program/ESP32/end_4/` |
| 语音与通信 ESP32-C3 | `code/Program/ESP32_C3/` |
| 摄像头与头部控制 OpenMV | `code/Program/OPENMV/` |
| MQTT、视觉与控制页面 | `code/Program/face_recognition_system/` |
| ASRPRO 语音程序 | `code/Program/ASRPRO/` |

`materials/` 保存 PCB、历史程序、参考资料等；`code/xiaozhi-esp32-main/` 是独立的上游工程副本。它们与上表的工程可能存在相似文件，修改前应在 PR 中写明所选维护路径。

## 团队协作

从 `main` 创建短期任务分支，按模块提交，通过 Pull Request 合并。分支、提交、审查和冲突处理的具体步骤见[贡献指南](CONTRIBUTING.md)。涉及多个模块的通信协议修改，请邀请所有受影响模块的负责人审阅。

模块负责人尚未确定时，先在[模块责任表](docs/模块责任表.md)填写姓名和 GitHub 账号；确定后再按[GitHub 仓库设置](docs/GitHub仓库设置.md)启用 `.github/CODEOWNERS` 自动请求审阅。
