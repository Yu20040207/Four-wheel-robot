# R1 停止锁存主机回归

本测试用主机 GCC 编译底盘的实际 C 源码，替换 STM32 外设和中断屏蔽操作。测试过程不生成固件、不调用 Keil、不连接开发板，也不烧录。所有中间对象及可执行文件均放入系统临时目录并自动清理；运行前后比较实际源文件和对应模块头文件的 SHA256，测试不写入被测源码。

在底盘 `USER` 目录运行：

```powershell
python -B tests/r1/run_tests.py
```

对完整 staging 镜像运行：

```powershell
python -B tests/r1/run_tests.py --source-root 'C:\Users\zhh\AppData\Local\Temp\r1_stop_work_20261004'
```

可用 `--cc 'C:\msys64\ucrt64\bin\gcc.exe'` 指定编译器，或用重复的 `--case NAME` 仅执行指定用例。`--compile-only` 只编译模块和外设替身，不链接或运行用例。默认的 `--source-root` 是本测试所在的底盘目录；目录必须包含已实现 R1 的完整源码和头文件。

## 实际代码与替身的边界

每个生产 C 文件通过独立包装编译单元直接 `#include`，不复制或重写控制逻辑。实际编译以下八个模块：

1. `HAREWARE/USART2_HANDLER/usart2_handler.c`
2. `HAREWARE/CONTROL/control.c`
3. `BALANCE/CONCTRL/conctrl.c`
4. `HAREWARE/USART_X/usart_x.c`
5. `HAREWARE/LineFollow/LineFollow.c`
6. `HAREWARE/AVOIDANCE/avoidance.c`
7. `HAREWARE/VOICE_CONTROL/voice_control.c`
8. `HAREWARE/MOTOR/motor.c`

用例逐字节调用真实 `USART1/2/3_IRQHandler`，调用真实 `USART2_ProcessData`、`Motor_Control_Update`、`TIM6_IRQHandler` 和 `Avoidance_TIM7_IRQHandler`。PI、故障锁、串口槽及循迹历史的白盒访问器追加在对应实际模块之后，只用于预置和检查其真实状态。每个用例都在独立进程内执行，静态变量不会跨用例残留。

`host_hal.c` 只替代 GPIO/PWM 寄存器、外设库调用、按键、编码器读取和 PRIMASK。主机的轮周长、编码器精度、轴距、轮距及 PID 系数是人工测试值；编码器读取默认返回 0。这些值不代表实车配置，也不能据此判断实际速度、制动距离或校准是否正确。反馈保留用例使用人工哨兵值检查 STOP 不覆盖反馈字段。

延后中断通过 PRIMASK 从 1 恢复为 0 时投递 USART2 字节模拟；指定第几次外层恢复后投递，以覆盖旧命令消费结束和 START 结束时才到达的 STOP。编码器读取及 PWM 使能处还可插入 STOP。本机制验证这些调度点上的 C 状态转换，不能证明真实中断延迟、串口吞吐、优先级或所有硬件时序。

`USER/main.c` 没有编译或执行，主循环的生产者门禁仍须单独检查源码。实际启动初始化、NVIC、真实 TIM7 中断入口派发、USART 电气连接和实车固件版本均未由此测试确认。主机回归通过不等同于 Keil 构建通过或上板测试通过。

## 覆盖的 20 个用例

| 用例 | 检查内容 |
| --- | --- |
| `stop_same_burst` | `S` 后紧跟 `G1`，主循环处理之前也立即关闭输出，旧运动指令不能覆盖 STOP。 |
| `stop_old_enables` | `6/8/A` 位于 STOP 前后同一 burst，停止锁与清理不被旧模式使能绕过。 |
| `stop_all_modes` | 自主避障、循迹、语音与雷达模式标志均被停止清理。 |
| `pending_command_cancelled` | `G1` 已从接收槽取出、尚未更新目标时被 STOP 取消。 |
| `actual_producers_stop` | 实际执行自主直行、倒车、左右侧移、循迹非零速度和语音非零速度，再分别发送 `S/stop`；新 CSV/循迹字节不能复活旧模式，START 仍保持零速度。 |
| `start_requires_consumed_stop` | STOP 清理完成之前的 START 被丢弃；START 后必须另发新的运动指令。 |
| `old_sensors_do_not_resume` | 停止期间的新传感数据和旧模式更新不能恢复运动。 |
| `fresh_modes_require_start` | 停止期间 `6/8/A` 无效；清理并 START 后重新发送才有效。 |
| `disable_is_global_stop` | `7/9/B` 同样锁存全局 STOP。 |
| `ros_cannot_bypass` | ROS 完整帧不能绕过停止；STOP 清除旧半包，START 后的旧后半包不能成帧，新完整帧可运行。 |
| `radar_key_openloop_cannot_bypass` | 停止时真实 TIM6 跳过按键；人为注入雷达模式或请求开环不能产生电机输出。 |
| `direct_outputs_cannot_bypass` | 停止期间直接调用真实 Drive/Set_Pwm 也不能产生输出。 |
| `stop_clears_history_preserves_fault` | 完整串口 `S` 清除 PI、平滑、循迹历史和输入槽，但保留故障锁、四路速度反馈及原始编码器反馈；START 后故障仍阻止 PWM。 |
| `partial_uart2_discarded` | STOP 清理丢弃清理前收到的半条 START。 |
| `fragmented_start_survives_main_loop` | 清理完成后，START 分为 `STA/RT` 或逐字符，跨多次主循环处理仍可完整接收。 |
| `authorization_is_exact` | `STAR$T`、`STARTx`、空格/符号、小写和超长行不能授权；START 后又收到 S 时仍停；S 可单独由 CR 或 LF 结束。 |
| `delayed_stop_during_consume` | 在真实槽消费结束后解除中断屏蔽，延后 STOP 仍压住旧命令。 |
| `delayed_stop_during_start` | 在真实 START 完成后解除中断屏蔽，延后 STOP 仍重新锁停。 |
| `stop_interrupts_control_output` | TIM6 编码器读取处及 Set_Pwm 的 PWM 使能处插入 STOP，最终电气输出保持关闭。 |
| `zero_unknown_not_global_stop` | 普通零速度或未知指令只清目标，不会意外产生全局停止锁。 |

避障侧移测试累计调用真实 TIM7 处理函数 `BACKWARD_TIME_MS` 次，并每 100 次补发 CSV，避免现有 `ULTRASONIC_TIMEOUT_MS` 超时提前结束倒车。枚举 `TURN_LEFT/TURN_RIGHT` 对应源码中的 `Move_Y` 侧移；用例没有把它当成实车原地旋转。

停止锁存在时，检查四路 PWM、方向脚及 STBY 全为 0，同时确认没有在锁存状态使能 PWM。START 后检查速度、目标、PI 和 PWM/方向脚仍为 0；非锁存状态下 STBY 可由现有零 PWM 写入路径拉高，不视为运动。
