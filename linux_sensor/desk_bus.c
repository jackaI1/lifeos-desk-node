// SPDX-License-Identifier: GPL-2.0
/* Deterministic virtual I2C adapter. DT child binding still uses the real core. */
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
struct desk_bus {
    struct i2c_adapter adapter;
    struct mutex lock;
    u8 raw[6];
};
static int desk_transfer(struct i2c_adapter *adapter, struct i2c_msg *msgs, int count) {
    struct desk_bus *bus = i2c_get_adapdata(adapter);
    int i;
    mutex_lock(&bus->lock);
    for (i = 0; i < count; i++) {
        if (msgs[i].addr != 0x44 || msgs[i].len != 6) {
            mutex_unlock(&bus->lock);
            return -EIO;
        }
        if (msgs[i].flags & I2C_M_RD)
            memcpy(msgs[i].buf, bus->raw, 6);
        else
            memcpy(bus->raw, msgs[i].buf, 6);
    }
    mutex_unlock(&bus->lock);
    return count;
}
static u32 desk_functionality(struct i2c_adapter *adapter) {
    (void)adapter;
    return I2C_FUNC_I2C;
}
static const struct i2c_algorithm desk_algorithm = {.master_xfer = desk_transfer,
                                                    .functionality = desk_functionality};
static int desk_probe(struct platform_device *pdev) {
    static const u8 initial[] = {0x66, 0x66, 0x93, 0x80, 0x00, 0xa2};
    struct desk_bus *bus = devm_kzalloc(&pdev->dev, sizeof(*bus), GFP_KERNEL);
    if (!bus)
        return -ENOMEM;
    mutex_init(&bus->lock);
    memcpy(bus->raw, initial, 6);
    bus->adapter.owner = THIS_MODULE;
    bus->adapter.algo = &desk_algorithm;
    bus->adapter.dev.parent = &pdev->dev;
    bus->adapter.dev.of_node = pdev->dev.of_node;
    strscpy(bus->adapter.name, "LifeOS simulated sensor bus", sizeof(bus->adapter.name));
    i2c_set_adapdata(&bus->adapter, bus);
    platform_set_drvdata(pdev, bus);
    return i2c_add_adapter(&bus->adapter);
}
static int desk_remove(struct platform_device *pdev) {
    struct desk_bus *bus = platform_get_drvdata(pdev);
    i2c_del_adapter(&bus->adapter);
    return 0;
}
static const struct of_device_id desk_match[] = {{.compatible = "lifeos,sim-i2c"}, {}};
MODULE_DEVICE_TABLE(of, desk_match);
static struct platform_driver desk_driver = {
    .probe = desk_probe,
    .remove = desk_remove,
    .driver = {.name = "desk-sim-i2c", .of_match_table = desk_match}};
module_platform_driver(desk_driver);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("LifeOS fault-injectable virtual I2C adapter");
