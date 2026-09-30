#include "LineFollow.h"
#include "usart2_handler.h"
#include "stdio.h"

/* ======================== 巡线调试参数 ========================
 * 接收后会反转传感器位序，bit0~bit7 对应右侧到左侧。
 * 当前实机逻辑把高电平视为检测到线；若实测相反，只改下面这一项。
 */
#define LINE_SENSOR_ACTIVE_HIGH          1
#define LINE_FORWARD_SPEED               0.42f  /* 居中时前进速度 */
#define LINE_MIN_FORWARD_SPEED           0.16f  /* 大偏差时最低前进速度 */
#define LINE_SPEED_REDUCTION_PER_ERROR   0.035f /* 偏差越大，前进速度下降越多 */
#define LINE_KP                          0.18f  /* 位置误差比例增益 */
#define LINE_KD                          0.10f  /* 抑制左右摆动的微分增益 */
#define LINE_ERROR_FILTER_ALPHA          0.55f  /* 误差低通系数，0~1 */
#define LINE_CENTER_DEADBAND             0.25f  /* 中心死区 */
#define LINE_MAX_TURN                    1.20f  /* 最大角速度 */
#define LINE_TURN_SLEW_LIMIT             0.16f  /* 每帧角速度最大变化量 */
#define LINE_LOST_SEARCH_SPEED           0.12f  /* 短时丢线搜索速度 */
#define LINE_LOST_SEARCH_TURN            0.35f  /* 短时丢线搜索角速度 */
#define LINE_LOST_SEARCH_SAMPLES         8      /* 超过该帧数仍丢线则停车 */
#define LINE_DEBUG_INTERVAL              20     /* 降低调试输出频率 */
/* ============================================================ */

/* 权重放大2倍，bit0最右，bit7最左。 */
static const int8_t sensor_weights[SENSOR_COUNT] = {-7, -5, -3, -1, 1, 3, 5, 7};

static volatile uint8_t sensor_levels = 0;
static volatile uint8_t new_data_available = 0;
static volatile uint8_t sensor_history[3] = {0, 0, 0};
static volatile uint8_t sensor_sample_count = 0;

static float filtered_error = 0.0f;
static float last_error = 0.0f;
static float last_line_error = 0.0f;
static float turn_output = 0.0f;
static uint8_t lost_line_count = 0;
static uint8_t debug_frame_count = 0;

static void Send_AutoMode_Command(void);
static uint8_t Calculate_Checksum(uint8_t *data, uint8_t length);
static void USART2_SendByte(uint8_t data);
static void USART2_SendString(char *str);
static uint8_t reverse_bits(uint8_t n);
static uint8_t majority3(uint8_t a, uint8_t b, uint8_t c);
static float LineFollow_Abs(float value);
static float LineFollow_Clamp(float value, float minimum, float maximum);
static float LineFollow_SlewTurn(float target);
static uint8_t LineFollow_CalculateError(uint8_t line_bits, float *error);

void LineFollow_ResetController(void)
{
    sensor_levels = 0;
    new_data_available = 0;
    sensor_history[0] = 0;
    sensor_history[1] = 0;
    sensor_history[2] = 0;
    sensor_sample_count = 0;
    filtered_error = 0.0f;
    last_error = 0.0f;
    last_line_error = 0.0f;
    turn_output = 0.0f;
    lost_line_count = 0;
    debug_frame_count = 0;

    Move_X = 0.0f;
    Move_Y = 0.0f;
    Move_Z = 0.0f;
}

void LineFollow_Init(void)
{
    sensor_levels = 0;
    new_data_available = 0;
    sensor_history[0] = 0;
    sensor_history[1] = 0;
    sensor_history[2] = 0;
    sensor_sample_count = 0;
    LineFollow_ResetController();

    delay_ms(100);
    Send_AutoMode_Command();
    USART_ITConfig(USART3, USART_IT_RXNE, ENABLE);

    USART2_SendString("Line Follower Sensor Initialized\r\n");
    USART2_SendString("Mode: Weighted PD (Auto Level)\r\n");
}

void LineFollow_Process(void)
{
    uint8_t reversed_sensors;
    uint8_t line_bits;
    float raw_error;
    float derivative;
    float target_turn;
    float forward_speed;
    char buffer[64];

    if (!line_follow_enabled) {
        LineFollow_ResetController();
        return;
    }

    if (!new_data_available) {
        return;
    }
    new_data_available = 0;

    reversed_sensors = reverse_bits(sensor_levels);
#if LINE_SENSOR_ACTIVE_HIGH
    line_bits = reversed_sensors;
#else
    line_bits = (uint8_t)(~reversed_sensors);
#endif

    /* 八路全触发可能是十字线或异常宽线，保持原逻辑：立即停车。 */
    if (line_bits == 0xFF) {
        lost_line_count = 0;
        turn_output = 0.0f;
        Move_X = 0.0f;
        Move_Y = 0.0f;
        Move_Z = 0.0f;
        return;
    }

    if (!LineFollow_CalculateError(line_bits, &raw_error)) {
        if (lost_line_count < 255) {
            lost_line_count++;
        }

        /* 短时丢线按最后偏差方向低速搜索，超时后停车。 */
        if (lost_line_count <= LINE_LOST_SEARCH_SAMPLES &&
            LineFollow_Abs(last_line_error) > 0.01f) {
            target_turn = (last_line_error > 0.0f) ?
                          LINE_LOST_SEARCH_TURN : -LINE_LOST_SEARCH_TURN;
            turn_output = LineFollow_SlewTurn(target_turn);
            Move_X = LINE_LOST_SEARCH_SPEED;
            Move_Y = 0.0f;
            Move_Z = turn_output;
        } else {
            turn_output = 0.0f;
            Move_X = 0.0f;
            Move_Y = 0.0f;
            Move_Z = 0.0f;
        }
        return;
    }

    lost_line_count = 0;

    /* 低通滤波加中心死区，避免线路边缘抖动造成左右反复切换。 */
    filtered_error += LINE_ERROR_FILTER_ALPHA * (raw_error - filtered_error);
    if (LineFollow_Abs(filtered_error) <= LINE_CENTER_DEADBAND) {
        filtered_error = 0.0f;
    }

    derivative = filtered_error - last_error;
    last_error = filtered_error;
    if (LineFollow_Abs(raw_error) > 0.01f) {
        last_line_error = raw_error;
    }

    target_turn = LINE_KP * filtered_error + LINE_KD * derivative;
    target_turn = LineFollow_Clamp(target_turn, -LINE_MAX_TURN, LINE_MAX_TURN);
    turn_output = LineFollow_SlewTurn(target_turn);

    /* 偏差越大越慢，防止高速冲过中心线。 */
    forward_speed = LINE_FORWARD_SPEED -
                    LINE_SPEED_REDUCTION_PER_ERROR * LineFollow_Abs(filtered_error);
    forward_speed = LineFollow_Clamp(forward_speed,
                                     LINE_MIN_FORWARD_SPEED,
                                     LINE_FORWARD_SPEED);

    Move_X = forward_speed;
    Move_Y = 0.0f;
    Move_Z = turn_output;

    /* 调试输出降频，避免115200串口打印阻塞巡线控制。 */
    debug_frame_count++;
    if (debug_frame_count >= LINE_DEBUG_INTERVAL) {
        debug_frame_count = 0;
        sprintf(buffer, "LF bits=%02X err=%d turn=%d speed=%d\r\n",
                line_bits,
                (int)(filtered_error * 100.0f),
                (int)(turn_output * 100.0f),
                (int)(forward_speed * 100.0f));
        USART2_SendString(buffer);
    }
}

static float LineFollow_Abs(float value)
{
    return (value < 0.0f) ? -value : value;
}

static float LineFollow_Clamp(float value, float minimum, float maximum)
{
    if (value < minimum) return minimum;
    if (value > maximum) return maximum;
    return value;
}

static float LineFollow_SlewTurn(float target)
{
    float delta = target - turn_output;
    delta = LineFollow_Clamp(delta, -LINE_TURN_SLEW_LIMIT, LINE_TURN_SLEW_LIMIT);
    return turn_output + delta;
}

static uint8_t LineFollow_CalculateError(uint8_t line_bits, float *error)
{
    int16_t weighted_sum = 0;
    uint8_t active_count = 0;
    uint8_t i;

    if (line_bits == 0x00 || line_bits == 0xFF || error == 0) {
        return 0;
    }

    for (i = 0; i < SENSOR_COUNT; i++) {
        if (line_bits & (1U << i)) {
            weighted_sum += sensor_weights[i];
            active_count++;
        }
    }

    if (active_count == 0) {
        return 0;
    }

    *error = ((float)weighted_sum) / (2.0f * (float)active_count);
    return 1;
}

static void Send_AutoMode_Command(void)
{
    uint8_t config_frame[5];
    char buffer[20];
    uint8_t i;

    config_frame[0] = LINEFOLLOW_HEADER1;
    config_frame[1] = LINEFOLLOW_HEADER2;
    config_frame[2] = 1;
    config_frame[3] = 0;
    config_frame[4] = Calculate_Checksum((uint8_t *)&config_frame[2], 2);

    USART2_SendString("Sending auto mode command: ");
    for (i = 0; i < 5; i++) {
        sprintf(buffer, "%02X ", config_frame[i]);
        USART2_SendString(buffer);
        USART_SendData(USART3, config_frame[i]);
        while (USART_GetFlagStatus(USART3, USART_FLAG_TXE) == RESET);
    }
    USART2_SendString("\r\n");
}

static uint8_t Calculate_Checksum(uint8_t *data, uint8_t length)
{
    uint8_t i;
    uint8_t sum = 0;
    for (i = 0; i < length; i++) {
        sum += data[i];
    }
    return (uint8_t)(~sum);
}

static void USART2_SendByte(uint8_t data)
{
    USART_SendData(USART2, data);
    while (USART_GetFlagStatus(USART2, USART_FLAG_TXE) == RESET);
}

static void USART2_SendString(char *str)
{
    while (*str) {
        USART2_SendByte((uint8_t)*str++);
    }
}

static uint8_t reverse_bits(uint8_t n)
{
    uint8_t rev = 0;
    int i;
    for (i = 0; i < 8; i++) {
        rev <<= 1;
        rev |= (n & 1U);
        n >>= 1;
    }
    return rev;
}

static uint8_t majority3(uint8_t a, uint8_t b, uint8_t c)
{
    return (uint8_t)((a & b) | (a & c) | (b & c));
}

void USART3_IRQHandler(void)
{
    uint8_t received_byte;

    if (USART_GetITStatus(USART3, USART_IT_RXNE) != RESET) {
        received_byte = (uint8_t)USART_ReceiveData(USART3);

        /* 三帧逐位多数滤波，单帧反光或边缘跳变不会立即反向。 */
        sensor_history[2] = sensor_history[1];
        sensor_history[1] = sensor_history[0];
        sensor_history[0] = received_byte;

        if (sensor_sample_count < 3) {
            sensor_sample_count++;
            sensor_levels = received_byte;
        } else {
            sensor_levels = majority3(sensor_history[0],
                                      sensor_history[1],
                                      sensor_history[2]);
        }
        new_data_available = 1;
        USART_ClearITPendingBit(USART3, USART_IT_RXNE);
    }
}
