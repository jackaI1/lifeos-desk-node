#include "desk_ssd1306.h"
bool desk_ssd1306_frame(const uint8_t frame[DESK_FRAME_SIZE],desk_display_write_fn write,void *context) {
    /* Transport-neutral SSD1306 commands. I2C adds control bytes; SPI uses D/C. */
    const uint8_t init[]={0xae,0xd5,0x80,0xa8,0x3f,0xd3,0x00,0x40,0x8d,0x14,
        0x20,0x00,0xa1,0xc8,0xda,0x12,0x81,0x40,0xd9,0xf1,0xdb,0x40,0xa4,0xa6,0x2e,
        0x21,0,127,0x22,0,7};
    const uint8_t on=0xaf;
    return write(context,false,init,sizeof init) &&
           write(context,true,frame,DESK_FRAME_SIZE) && write(context,false,&on,1);
}
