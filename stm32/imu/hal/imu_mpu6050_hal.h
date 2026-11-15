/* STM32 HAL port of the IMU filter: an MPU-6050 on I2C, paced by a timer interrupt. */
#ifndef IMU_MPU6050_HAL_H
#define IMU_MPU6050_HAL_H

#include "stm32f4xx_hal.h"
#include "imu_core.h"

/* Start the sensor and the sample timer. The timer must be configured for IMU_SAMPLE_RATE_HZ. */
HAL_StatusTypeDef imu_hal_start(I2C_HandleTypeDef *hi2c, TIM_HandleTypeDef *htim);

/* Call from HAL_TIM_PeriodElapsedCallback. Each tick raises one sample request. */
void imu_hal_on_tick(TIM_HandleTypeDef *htim);

/* Call from the main loop. Starts an interrupt-mode read when a tick is pending. */
void imu_hal_poll(void);

/* Call from HAL_I2C_MemRxCpltCallback and HAL_I2C_ErrorCallback. */
void imu_hal_on_mem_rx_done(I2C_HandleTypeDef *hi2c);
void imu_hal_on_error(I2C_HandleTypeDef *hi2c);

/* Most recent filter output, or NULL before the first sample. */
const imu_out_t *imu_hal_latest(void);

/* Counts of ticks that could not be read because the bus refused the request. */
uint32_t imu_hal_bus_errors(void);

#endif
