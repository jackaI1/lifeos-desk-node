/* MPU-6050 driver for the desk node IMU, written against the STM32 HAL.
 *
 * The sample timer runs at IMU_SAMPLE_RATE_HZ and raises an interrupt each period.
 * That interrupt only sets a flag and increments the sequence number. The main loop
 * starts an interrupt-mode I2C read of the 14 data bytes, and the read-complete
 * interrupt decodes them and runs the filter. Sequence gaps show up as dropped samples
 * in the filter, so a bus error costs one sample and is counted, not hidden.
 */
#include "imu_mpu6050_hal.h"

#include <stddef.h>

#define MPU6050_ADDRESS (0x68U << 1)
#define REG_SMPLRT_DIV 0x19U
#define REG_CONFIG 0x1AU
#define REG_GYRO_CONFIG 0x1BU
#define REG_ACCEL_CONFIG 0x1CU
#define REG_ACCEL_XOUT_H 0x3BU
#define REG_PWR_MGMT_1 0x6BU
#define HAL_WAIT_MS 10U

static I2C_HandleTypeDef *i2c_;
static TIM_HandleTypeDef *timer_;
static volatile uint8_t tick_pending_;
static volatile uint8_t read_busy_;
static volatile uint32_t next_seq_;
static volatile uint32_t bus_errors_;
static uint8_t raw_[14];
static uint32_t read_seq_;
static imu_state_t state_;
static imu_out_t latest_;
static uint8_t have_latest_;

static HAL_StatusTypeDef write_register(uint8_t reg, uint8_t value) {
    return HAL_I2C_Mem_Write(i2c_, MPU6050_ADDRESS, reg, I2C_MEMADD_SIZE_8BIT, &value, 1,
                             HAL_WAIT_MS);
}

static int16_t be16(const uint8_t *p) {
    return (int16_t)(uint16_t)(((uint16_t)p[0] << 8) | p[1]);
}

HAL_StatusTypeDef imu_hal_start(I2C_HandleTypeDef *hi2c, TIM_HandleTypeDef *htim) {
    HAL_StatusTypeDef status;
    i2c_ = hi2c;
    timer_ = htim;
    imu_init(&state_);
    have_latest_ = 0;
    tick_pending_ = 0;
    read_busy_ = 0;
    next_seq_ = 0;
    bus_errors_ = 0;

    /* Wake the sensor from sleep and use the internal oscillator. */
    status = write_register(REG_PWR_MGMT_1, 0x00U);
    if (status != HAL_OK)
        return status;
    /* Gyro low-pass at 44 Hz (CONFIG = 3) with the 1 kHz base rate; divider 9 gives 100 Hz. */
    status = write_register(REG_CONFIG, 0x03U);
    if (status != HAL_OK)
        return status;
    status = write_register(REG_SMPLRT_DIV, 9U);
    if (status != HAL_OK)
        return status;
    /* Full-scale +-250 dps (131 LSB per dps) and +-2 g (16384 LSB per g), matching imu_core. */
    status = write_register(REG_GYRO_CONFIG, 0x00U);
    if (status != HAL_OK)
        return status;
    status = write_register(REG_ACCEL_CONFIG, 0x00U);
    if (status != HAL_OK)
        return status;

    return HAL_TIM_Base_Start_IT(htim);
}

void imu_hal_on_tick(TIM_HandleTypeDef *htim) {
    if (htim != timer_)
        return;
    next_seq_++;
    tick_pending_ = 1;
}

void imu_hal_poll(void) {
    if (!tick_pending_ || read_busy_)
        return;
    tick_pending_ = 0;
    read_seq_ = next_seq_;
    read_busy_ = 1;
    if (HAL_I2C_Mem_Read_IT(i2c_, MPU6050_ADDRESS, REG_ACCEL_XOUT_H, I2C_MEMADD_SIZE_8BIT, raw_,
                            sizeof raw_) != HAL_OK) {
        read_busy_ = 0;
        bus_errors_++;
    }
}

void imu_hal_on_mem_rx_done(I2C_HandleTypeDef *hi2c) {
    imu_sample_t sample;
    if (hi2c != i2c_ || !read_busy_)
        return;
    /* Register order: AX AY AZ, then temperature (skipped), then GX GY GZ. */
    sample.seq = read_seq_;
    sample.ax = be16(&raw_[0]);
    sample.ay = be16(&raw_[2]);
    sample.az = be16(&raw_[4]);
    sample.gx = be16(&raw_[8]);
    sample.gy = be16(&raw_[10]);
    sample.gz = be16(&raw_[12]);
    imu_step(&state_, &sample, &latest_);
    have_latest_ = 1;
    read_busy_ = 0;
}

void imu_hal_on_error(I2C_HandleTypeDef *hi2c) {
    if (hi2c != i2c_)
        return;
    read_busy_ = 0;
    bus_errors_++;
}

const imu_out_t *imu_hal_latest(void) {
    return have_latest_ ? &latest_ : NULL;
}

uint32_t imu_hal_bus_errors(void) {
    return bus_errors_;
}
