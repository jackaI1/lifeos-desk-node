// SPDX-License-Identifier: GPL-2.0
#include <linux/capability.h>
#include <linux/fs.h>
#include <linux/i2c.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/uaccess.h>
#include "desk_sensor.h"
struct desk_sensor {
    struct i2c_client *client;
    struct miscdevice misc;
    struct mutex lock;
    bool alarm;
};
static u8 crc8(const u8 *data) {
    u8 crc = 0xff;
    int i, b;
    for (i = 0; i < 2; i++) {
        crc ^= data[i];
        for (b = 0; b < 8; b++)
            crc = (crc << 1) ^ ((crc & 0x80) ? 0x31 : 0);
    }
    return crc;
}
static int snapshot(struct desk_sensor *sensor, struct desk_registers *out) {
    int result = i2c_master_recv(sensor->client, out->raw, 6);
    if (result != 6) {
        sensor->alarm = true;
        return result < 0 ? result : -EIO;
    }
    if (crc8(out->raw) != out->raw[2] || crc8(out->raw + 3) != out->raw[5])
        sensor->alarm = true;
    out->alarm = sensor->alarm;
    out->reserved = 0;
    return 0;
}
static struct desk_sensor *from_file(struct file *file) {
    return container_of(file->private_data, struct desk_sensor, misc);
}
static ssize_t desk_read(struct file *file, char __user *buffer, size_t count, loff_t *offset) {
    struct desk_sensor *sensor = from_file(file);
    struct desk_registers data = {0};
    int result;
    if (*offset)
        return 0;
    if (count < sizeof(data))
        return -EINVAL;
    mutex_lock(&sensor->lock);
    result = snapshot(sensor, &data);
    mutex_unlock(&sensor->lock);
    if (result)
        return result;
    if (copy_to_user(buffer, &data, sizeof(data)))
        return -EFAULT;
    *offset += sizeof(data);
    return sizeof(data);
}
static long desk_ioctl(struct file *file, unsigned int cmd, unsigned long arg) {
    struct desk_sensor *sensor = from_file(file);
    struct desk_registers data = {0};
    int result = 0;
    if (cmd != DESK_GET && cmd != DESK_INJECT && cmd != DESK_CLEAR)
        return -ENOTTY;
    if (cmd != DESK_GET && !capable(CAP_SYS_ADMIN))
        return -EPERM;
    if (cmd == DESK_INJECT && copy_from_user(&data, (void __user *)arg, sizeof(data)))
        return -EFAULT;
    mutex_lock(&sensor->lock);
    if (cmd == DESK_CLEAR)
        sensor->alarm = false;
    else {
        if (cmd == DESK_INJECT) {
            result = i2c_master_send(sensor->client, data.raw, 6);
            result = result == 6 ? 0 : result < 0 ? result : -EIO;
        }
        if (!result)
            result = snapshot(sensor, &data);
    }
    mutex_unlock(&sensor->lock);
    if (!result && cmd == DESK_GET && copy_to_user((void __user *)arg, &data, sizeof(data)))
        result = -EFAULT;
    return result;
}
static const struct file_operations desk_fops = {.owner = THIS_MODULE,
                                                 .read = desk_read,
                                                 .unlocked_ioctl = desk_ioctl,
                                                 .compat_ioctl = desk_ioctl,
                                                 .llseek = no_llseek};
static int desk_probe(struct i2c_client *client) {
    struct desk_sensor *sensor = devm_kzalloc(&client->dev, sizeof(*sensor), GFP_KERNEL);
    if (!sensor)
        return -ENOMEM;
    sensor->client = client;
    mutex_init(&sensor->lock);
    sensor->misc.minor = MISC_DYNAMIC_MINOR;
    sensor->misc.name = "desk-sensor";
    sensor->misc.fops = &desk_fops;
    sensor->misc.mode = 0600;
    i2c_set_clientdata(client, sensor);
    return misc_register(&sensor->misc);
}
static void desk_remove(struct i2c_client *client) {
    struct desk_sensor *sensor = i2c_get_clientdata(client);
    misc_deregister(&sensor->misc);
}
static const struct of_device_id desk_match[] = {{.compatible = "lifeos,sht31-sim"}, {}};
MODULE_DEVICE_TABLE(of, desk_match);
static const struct i2c_device_id desk_ids[] = {{"desk-sht31", 0}, {}};
MODULE_DEVICE_TABLE(i2c, desk_ids);
static struct i2c_driver desk_driver = {
    .driver = {.name = "desk-sht31", .of_match_table = desk_match},
    .probe = desk_probe,
    .remove = desk_remove,
    .id_table = desk_ids};
module_i2c_driver(desk_driver);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("LifeOS checked sensor character device with held alarm");
