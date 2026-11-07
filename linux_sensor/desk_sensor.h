#ifndef DESK_SENSOR_UAPI_H
#define DESK_SENSOR_UAPI_H
#include <linux/ioctl.h>
#include <linux/types.h>
/* Register block: six SHT31 wire bytes, held alarm, reserved zero byte. */
struct desk_registers { __u8 raw[6]; __u8 alarm; __u8 reserved; };
#define DESK_GET _IOR('D', 1, struct desk_registers)
#define DESK_INJECT _IOW('D', 2, struct desk_registers)
#define DESK_CLEAR _IO('D', 3)
#endif
