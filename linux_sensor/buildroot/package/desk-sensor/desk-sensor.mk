DESK_SENSOR_VERSION = 1.0
DESK_SENSOR_SITE = $(BR2_EXTERNAL_DESK_PATH)/..
DESK_SENSOR_SITE_METHOD = local
DESK_SENSOR_LICENSE = GPL-2.0

define DESK_SENSOR_BUILD_CMDS
 $(TARGET_CXX) -std=c++17 -Wall -Wextra -Werror -O2 $(@D)/service.cpp -o $(@D)/desk-sensor-service
endef

define DESK_SENSOR_INSTALL_TARGET_CMDS
 $(INSTALL) -D -m 0755 $(@D)/desk-sensor-service $(TARGET_DIR)/usr/bin/desk-sensor-service
 $(INSTALL) -D -m 0755 $(BR2_EXTERNAL_DESK_PATH)/board/S99desk $(TARGET_DIR)/etc/init.d/S99desk
endef

$(eval $(kernel-module))
$(eval $(generic-package))
