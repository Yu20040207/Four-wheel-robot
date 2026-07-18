#include "bsp.h"

/* ----------- 用户可调参数 ----------- */
#define FILTER_SIZE       5       // 滤波器大小
#define MAX_DISTANCE      250     // 最大测量距离(cm)
#define MEASURE_PERIOD_MS 100     // 测量周期(ms)
#define MEASURE_TIMEOUT_US 30000  // 测量超时时间(us)
/* ----------------------------------- */

// 声明外部变量（在main.c中定义）
extern volatile uint32_t sys_tick;

// 超声波模块配置结构体
typedef struct {
    GPIO_TypeDef* trig_port;      // Trig引脚端口
    uint16_t      trig_pin;       // Trig引脚编号
    uint16_t      echo_pin;       // Echo引脚编号
    uint32_t      exti_line;      // 外部中断线
    uint8_t       exti_port_source; // 外部中断端口源
    uint8_t       exti_pin_source;  // 外部中断引脚源
} UltrasonicModule;

// 超声波模块配置数组
static const UltrasonicModule modules[4] = {
    {GPIOA, GPIO_Pin_0,  GPIO_Pin_1,  EXTI_Line1,  GPIO_PortSourceGPIOA, GPIO_PinSource1},  // 模块1
    {GPIOA, GPIO_Pin_4,  GPIO_Pin_5,  EXTI_Line5,  GPIO_PortSourceGPIOA, GPIO_PinSource5},  // 模块2
    {GPIOA, GPIO_Pin_6,  GPIO_Pin_7,  EXTI_Line7,  GPIO_PortSourceGPIOA, GPIO_PinSource7},  // 模块3
    {GPIOB, GPIO_Pin_9,  GPIO_Pin_8,  EXTI_Line8,  GPIO_PortSourceGPIOB, GPIO_PinSource8}   // 模块4
};

// 传感器状态结构体
typedef struct {
    volatile uint32_t pulse_start;      // 脉冲开始时间
    volatile uint32_t pulse_end;        // 脉冲结束时间
    volatile uint8_t  measurement_done; // 测量完成标志
    volatile uint8_t  measurement_timeout; // 测量超时标志
    uint32_t distance_buffer[FILTER_SIZE]; // 距离缓冲区
    uint8_t  filter_index;              // 滤波器索引
    uint32_t last_distance_cm;          // 最后测量距离(cm)
} SensorState;

// 传感器状态数组
static SensorState sensor_state[4] = {{0}};

// 非阻塞测量状态机状态
static uint8_t measure_state = 0;     // 当前测量状态
static uint8_t current_sensor = 0;    // 当前处理的传感器
static uint32_t measure_start_time = 0; // 测量开始时间

// 新增：超声波控制变量
static uint32_t last_measure_time = 0; // 上一次测量时间
static uint8_t enabled = 0;            // 超声波使能标志

/* -------------- 私有函数声明 -------------- */
static uint32_t CalcDistance(uint32_t start, uint32_t end);
static uint32_t ApplyFilter(uint8_t id, uint32_t raw);
static void FormatDistance(uint32_t d, char *buf, uint8_t *pos);
static int cmp_u32(const void *a, const void *b);
static void Delay_us(uint32_t us);

/* -------------- 接口实现 -------------- */

/**
  * @brief  超声波模块初始化
  * @param  无
  * @retval 无
  */
void Ultrasonic_Init(void)
{
    GPIO_InitTypeDef  GPIO_InitStructure;
    EXTI_InitTypeDef  EXTI_InitStructure;
    NVIC_InitTypeDef  NVIC_InitStructure;
    TIM_TimeBaseInitTypeDef TIM_TimeBaseStructure;
    
    // 初始化结构体
    memset(&GPIO_InitStructure, 0, sizeof(GPIO_InitStructure));
    memset(&EXTI_InitStructure, 0, sizeof(EXTI_InitStructure));
    memset(&NVIC_InitStructure, 0, sizeof(NVIC_InitStructure));
    memset(&TIM_TimeBaseStructure, 0, sizeof(TIM_TimeBaseStructure));

    // 使能GPIO和AFIO时钟
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA | RCC_APB2Periph_GPIOB | 
                          RCC_APB2Periph_AFIO, ENABLE);

    // 配置Trig引脚为推挽输出
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_InitStructure.GPIO_Mode  = GPIO_Mode_Out_PP;
    
    // PA Trig引脚
    GPIO_InitStructure.GPIO_Pin   = GPIO_Pin_0 | GPIO_Pin_4 | GPIO_Pin_6;
    GPIO_Init(GPIOA, &GPIO_InitStructure);
    
    // PB Trig引脚 (PB9)
    GPIO_InitStructure.GPIO_Pin   = GPIO_Pin_9;
    GPIO_Init(GPIOB, &GPIO_InitStructure);

    // 配置Echo引脚为上拉输入（增强抗干扰）
    GPIO_InitStructure.GPIO_Mode  = GPIO_Mode_IPU;
    
    // PA Echo引脚
    GPIO_InitStructure.GPIO_Pin   = GPIO_Pin_1 | GPIO_Pin_5 | GPIO_Pin_7;
    GPIO_Init(GPIOA, &GPIO_InitStructure);
    
    // PB Echo引脚 (PB8)
    GPIO_InitStructure.GPIO_Pin   = GPIO_Pin_8;
    GPIO_Init(GPIOB, &GPIO_InitStructure);

    // 配置外部中断线
    GPIO_EXTILineConfig(GPIO_PortSourceGPIOA, GPIO_PinSource1);
    GPIO_EXTILineConfig(GPIO_PortSourceGPIOA, GPIO_PinSource5);
    GPIO_EXTILineConfig(GPIO_PortSourceGPIOA, GPIO_PinSource7);
    GPIO_EXTILineConfig(GPIO_PortSourceGPIOB, GPIO_PinSource8);

    // 配置外部中断
    EXTI_InitStructure.EXTI_Line    = EXTI_Line1 | EXTI_Line5 | EXTI_Line7 | EXTI_Line8;
    EXTI_InitStructure.EXTI_Mode    = EXTI_Mode_Interrupt;
    EXTI_InitStructure.EXTI_Trigger = EXTI_Trigger_Rising_Falling;
    EXTI_InitStructure.EXTI_LineCmd = ENABLE;
    EXTI_Init(&EXTI_InitStructure);

    // 配置中断优先级为最低
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 15; // 最低抢占优先级
    NVIC_InitStructure.NVIC_IRQChannelSubPriority        = 15; // 最低子优先级
    NVIC_InitStructure.NVIC_IRQChannelCmd                = ENABLE;
    
    // 配置EXTI1中断
    NVIC_InitStructure.NVIC_IRQChannel = EXTI1_IRQn;
    NVIC_Init(&NVIC_InitStructure);
    
    // 配置EXTI9_5中断
    NVIC_InitStructure.NVIC_IRQChannel = EXTI9_5_IRQn;
    NVIC_Init(&NVIC_InitStructure);

    // 初始化定时器2用于时间测量
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2, ENABLE);
    TIM_TimeBaseStructure.TIM_Period = 0xFFFF;
    TIM_TimeBaseStructure.TIM_Prescaler = 72-1;  // 72MHz/72 = 1MHz (1us)
    TIM_TimeBaseStructure.TIM_ClockDivision = 0;
    TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up;
    TIM_TimeBaseInit(TIM2, &TIM_TimeBaseStructure);
    TIM_Cmd(TIM2, ENABLE);
    
    // 重置测量状态
    measure_state = 0;
    current_sensor = 0;
    measure_start_time = 0;
    last_measure_time = 0;
    enabled = 0;
}

/**
  * @brief  设置超声波使能状态
  * @param  status: 1-使能, 0-禁用
  * @retval 无
  */
void Ultrasonic_SetEnable(uint8_t status)
{
    enabled = status;
    // 移除了LED控制代码
}

/**
  * @brief  超声波处理函数（周期性测量）
  * @param  无
  * @retval 无
  */
void Ultrasonic_Process(void)
{
    if (!enabled) return;
    
    uint32_t current_time = sys_tick;
    
    // 1.1 处理超声波测量（非阻塞方式）
    if (Ultrasonic_Measure_NonBlocking()) {
        // 测量完成后更新最后测量时间
        last_measure_time = current_time;
    }
    // 1.2 如果距离上次测量超过100ms且不在测量中，启动新测量
    else if (!Ultrasonic_IsMeasuring() && 
             (current_time - last_measure_time >= MEASURE_PERIOD_MS)) {
        Ultrasonic_Measure_NonBlocking();
    }
}

/**
  * @brief  触发单路超声波
  * @param  id: 传感器ID (0-3)
  * @retval 无
  */
void Ultrasonic_Trigger(uint8_t id)
{
    if(id >= 4) return;
    
    // 重置状态
    sensor_state[id].measurement_done = 0;
    sensor_state[id].measurement_timeout = 0;
    
    // 发送触发脉冲
    GPIO_ResetBits(modules[id].trig_port, modules[id].trig_pin);
    Delay_us(2);
    GPIO_SetBits(modules[id].trig_port, modules[id].trig_pin);
    Delay_us(10);
    GPIO_ResetBits(modules[id].trig_port, modules[id].trig_pin);
}

/**
  * @brief  非阻塞式超声波测量
  * @param  无
  * @retval 1: 测量完成, 0: 测量未完成
  */
uint8_t Ultrasonic_Measure_NonBlocking(void)
{
    switch(measure_state) {
        case 0: // 初始状态 - 触发所有传感器
            // 触发所有传感器
            for(uint8_t id = 0; id < 4; id++) {
                Ultrasonic_Trigger(id);
            }
            measure_state = 1;
            current_sensor = 0;
            measure_start_time = TIM_GetCounter(TIM2);
            break;
            
        case 1: // 等待传感器完成测量
            // 检查当前传感器是否完成测量
            if(sensor_state[current_sensor].measurement_done || 
               sensor_state[current_sensor].measurement_timeout) 
            {
                // 处理测量结果
                if(sensor_state[current_sensor].measurement_done) {
                    uint32_t raw_distance = CalcDistance(
                        sensor_state[current_sensor].pulse_start, 
                        sensor_state[current_sensor].pulse_end
                    );
                    
                    sensor_state[current_sensor].last_distance_cm = ApplyFilter(current_sensor, raw_distance);
                }
                
                // 移动到下一个传感器
                current_sensor++;
                
                // 所有传感器处理完毕
                if(current_sensor >= 4) {
                    measure_state = 2; // 进入发送结果状态
                }
            }
            // 检查超时
            else if((TIM_GetCounter(TIM2) - measure_start_time) > MEASURE_TIMEOUT_US) {
                sensor_state[current_sensor].measurement_timeout = 1;
            }
            break;
            
        case 2: // 发送结果阶段
        {
            char txBuf[32];
            uint8_t pos = 0;
            
            // 格式化所有传感器数据
            for(uint8_t id = 0; id < 4; id++) {
                FormatDistance(sensor_state[id].last_distance_cm, txBuf, &pos);
                if(id < 3) txBuf[pos++] = ',';
            }
            
            // 添加结束符
            txBuf[pos++] = '\r';
            txBuf[pos++] = '\n';
            txBuf[pos] = '\0';
            
            // 通过串口3发送数据
            USART3_SendString(txBuf);
            
            // 重置状态
            measure_state = 0;
            return 1; // 测量完成
        }
    }
    
    return 0; // 测量未完成
}

/**
  * @brief  检查是否正在测量
  * @param  无
  * @retval 1: 正在测量, 0: 空闲
  */
uint8_t Ultrasonic_IsMeasuring(void)
{
    return (measure_state != 0);
}

/**
  * @brief  获取指定超声波传感器最新距离
  * @param  id: 0=左前, 1=正前(捡垃圾用), 2=右前, 3=后
  * @retval 距离(cm)
  */
uint32_t Ultrasonic_GetDistance(uint8_t id)
{
    if (id >= 4) return 0xFFFF;
    return sensor_state[id].last_distance_cm;
}

/**
  * @brief  获取正前方超声波距离（模块2，捡垃圾接近用）
  */
uint32_t Ultrasonic_GetFrontDistance(void)
{
    return Ultrasonic_GetDistance(1);
}

/**
  * @brief  回传最新测量结果
  * @param  无
  * @retval 无
  */
void USART3_SendDistance(void)
{
    char txBuf[32];
    uint8_t pos = 0;
    uint8_t id;
    
    for(id = 0; id < 4; id++) {
        FormatDistance(sensor_state[id].last_distance_cm, txBuf, &pos);
        if(id < 3) txBuf[pos++] = ',';
    }
    
    txBuf[pos++] = '\r';
    txBuf[pos++] = '\n';
    txBuf[pos] = '\0';
    USART3_SendString(txBuf);
}

/* -------------- 私有函数实现 -------------- */

/**
  * @brief  计算距离
  * @param  start: 脉冲开始时间
  * @param  end: 脉冲结束时间
  * @retval 距离(cm)
  */
static uint32_t CalcDistance(uint32_t start, uint32_t end)
{
    // 处理定时器溢出
    uint32_t dur = (end >= start) ? (end - start) : (0xFFFFFFFF - start + end);
    
    // 计算距离: 声速340m/s ≈ 29us/cm，往返除以2 → 58us/cm
    // 使用优化后的整数运算
    uint32_t cm = (dur * 17) / 1000;  // 近似计算
    
    // 限制最大距离
    return (cm > MAX_DISTANCE) ? MAX_DISTANCE : cm;
}

/**
  * @brief  应用滤波器
  * @param  id: 传感器ID
  * @param  raw: 原始距离值
  * @retval 滤波后的距离值
  */
static uint32_t ApplyFilter(uint8_t id, uint32_t raw)
{
    SensorState* state = &sensor_state[id];
    uint32_t temp[FILTER_SIZE];
    uint32_t sum = 0;
    uint32_t median;
    uint8_t cnt = 0;
    uint8_t i;
    
    // 更新滤波缓冲区
    state->distance_buffer[state->filter_index] = raw;
    state->filter_index = (state->filter_index + 1) % FILTER_SIZE;
    
    // 创建临时数组用于排序
    memcpy(temp, state->distance_buffer, sizeof(temp));
    
    // 快速排序
    qsort(temp, FILTER_SIZE, sizeof(uint32_t), cmp_u32);
    
    // 计算中值
    median = temp[FILTER_SIZE / 2];
    
    // 基于中值的均值滤波
    for(i = 0; i < FILTER_SIZE; i++) {
        if(labs((int32_t)temp[i] - (int32_t)median) < 20) {
            sum += temp[i];
            cnt++;
        }
    }
    
    return cnt ? sum / cnt : median;
}

/**
  * @brief  格式化距离数据
  * @param  d: 距离值
  * @param  buf: 输出缓冲区
  * @param  pos: 缓冲区位置指针
  * @retval 无
  */
static void FormatDistance(uint32_t d, char *buf, uint8_t *pos)
{
    if(d == 0xFFFF) {
        // 错误状态显示"ERR"
        buf[(*pos)++] = 'E';
        buf[(*pos)++] = 'R';
        buf[(*pos)++] = 'R';
        return;
    }
    
    // 优化数字转换
    if(d >= 100) {
        buf[(*pos)++] = '0' + d/100;
        d %= 100;
        buf[(*pos)++] = '0' + d/10;
        buf[(*pos)++] = '0' + d%10;
    } else if(d >= 10) {
        buf[(*pos)++] = '0' + d/10;
        buf[(*pos)++] = '0' + d%10;
    } else {
        buf[(*pos)++] = '0' + d;
    }
}

/**
  * @brief  uint32_t比较函数
  * @param  a: 第一个值
  * @param  b: 第二个值
  * @retval 比较结果
  */
static int cmp_u32(const void *a, const void *b)
{
    uint32_t val_a = *(const uint32_t*)a;
    uint32_t val_b = *(const uint32_t*)b;
    
    if(val_a > val_b) return 1;
    if(val_a < val_b) return -1;
    return 0;
}

/**
  * @brief  微秒延时函数
  * @param  us: 延时时间(微秒)
  * @retval 无
  */
static void Delay_us(uint32_t us)
{
    // 根据系统时钟调整此值
    us *= 8;
    while(us--) {
        __nop();  // 空指令延时
    }
}

/* ---------- 中断服务函数 ---------- */

/**
  * @brief  EXTI1中断服务函数
  * @param  无
  * @retval 无
  */
void EXTI1_IRQHandler(void)
{
    if(EXTI_GetITStatus(EXTI_Line1) != RESET) {
        uint32_t now = TIM_GetCounter(TIM2);
        uint8_t pin_state = GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_1);
        
        if(pin_state) {
            sensor_state[0].pulse_start = now;  // 上升沿
        } else {
            sensor_state[0].pulse_end = now;    // 下降沿
            sensor_state[0].measurement_done = 1;
        }
        EXTI_ClearITPendingBit(EXTI_Line1);
    }
}

/**
  * @brief  EXTI9_5中断服务函数
  * @param  无
  * @retval 无
  */
void EXTI9_5_IRQHandler(void)
{
    uint32_t now = TIM_GetCounter(TIM2);
    
    // 处理模块2 (PA5)
    if(EXTI_GetITStatus(EXTI_Line5) != RESET) {
        uint8_t pin_state = GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_5);
        
        if(pin_state) {
            sensor_state[1].pulse_start = now;
        } else {
            sensor_state[1].pulse_end = now;
            sensor_state[1].measurement_done = 1;
        }
        EXTI_ClearITPendingBit(EXTI_Line5);
    }
    
    // 处理模块3 (PA7)
    if(EXTI_GetITStatus(EXTI_Line7) != RESET) {
        uint8_t pin_state = GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_7);
        
        if(pin_state) {
            sensor_state[2].pulse_start = now;
        } else {
            sensor_state[2].pulse_end = now;
            sensor_state[2].measurement_done = 1;
        }
        EXTI_ClearITPendingBit(EXTI_Line7);
    }
    
    // 处理模块4 (PB8)
    if(EXTI_GetITStatus(EXTI_Line8) != RESET) {
        uint8_t pin_state = GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_8);
        
        if(pin_state) {
            sensor_state[3].pulse_start = now;
        } else {
            sensor_state[3].pulse_end = now;
            sensor_state[3].measurement_done = 1;
        }
        EXTI_ClearITPendingBit(EXTI_Line8);
    }
}
