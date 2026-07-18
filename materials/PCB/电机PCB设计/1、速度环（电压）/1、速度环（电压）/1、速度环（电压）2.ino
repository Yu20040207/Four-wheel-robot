#include <SimpleFOC.h>
#define NSLP  7
#define NRST  8
#define DIR  3

// magnetic sensor instance - I2C
MagneticSensorI2C sensor = MagneticSensorI2C(AS5600_I2C);

// 电机参数设置：BLDCMotor(pp, R, KV, L)
// BLDCMotor motor = BLDCMotor(8, 2.5, 50, 0.0025);
BLDCMotor motor = BLDCMotor(8);
BLDCDriver3PWM driver = BLDCDriver3PWM(5, 6, 9, 4);

// velocity set point variable
float target_velocity = 0;
// instantiate the commander
Commander command = Commander(Serial);
void doTarget(char* cmd) { command.scalar(&target_velocity, cmd); }

void setup() {

  // use monitoring with serial 
  Serial.begin(115200);
  
  pinMode(DIR, OUTPUT);  
  digitalWrite(NSLP, HIGH);
  digitalWrite(NRST, HIGH);
  digitalWrite(DIR, LOW);

  // enable more verbose output for debugging
  SimpleFOCDebug::enable(&Serial);

  // initialise magnetic sensor hardware
  sensor.init();
  // link the motor to the sensor
  motor.linkSensor(&sensor);

  // driver config
  // power supply voltage [V]
  driver.voltage_power_supply = 12;
  driver.init();
  // link the motor and the driver
  motor.linkDriver(&driver);

  // set motion control loop to be used
  motor.controller = MotionControlType::velocity;

  // contoller configuration
  // default parameters in defaults.h

  // velocity PI controller parameters
  motor.PID_velocity.P = 0.2f;
  motor.PID_velocity.I = 10;
  motor.PID_velocity.D = 0;
  // default voltage_power_supply
  motor.voltage_limit = 6;
  // jerk control using voltage voltage ramp
  motor.PID_velocity.output_ramp = 1000;

  // velocity low pass filtering
  motor.LPF_velocity.Tf = 0.01f;

  // comment out if not needed
  motor.useMonitoring(Serial);

  // initialize motor
  motor.init();
  // align sensor and start FOC
  motor.initFOC();

  // add target command T
  command.add('T', doTarget, "target velocity");

  Serial.println(F("Motor ready."));
  Serial.println(F("Set the target velocity using serial terminal:"));
  _delay(1000);
}

void loop() {

  motor.loopFOC();

  motor.move(target_velocity);

  command.run();
}
