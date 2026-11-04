#ifndef DESK_SSD1306_H
#define DESK_SSD1306_H
#include "desk_core.h"
typedef bool (*desk_display_write_fn)(void *context,bool data,const uint8_t *bytes,size_t length);
bool desk_ssd1306_frame(const uint8_t frame[DESK_FRAME_SIZE],desk_display_write_fn write,void *context);
#endif
