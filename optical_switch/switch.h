#ifndef DESK_OPTICAL_SWITCH_H
#define DESK_OPTICAL_SWITCH_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define SWITCH_PORTS 16
typedef struct { uint8_t peer[16], fault[16]; uint64_t deadline[16]; } switch_t;
void switch_init(switch_t *state);
bool switch_connect(switch_t *state,unsigned a,unsigned b,uint64_t now);
bool switch_disconnect(switch_t *state,unsigned port);
bool switch_ack(switch_t *state,unsigned port);
bool switch_tick(switch_t *state,uint64_t now);
bool switch_save(const switch_t *state,const char *path);
bool switch_load(switch_t *state,const char *path,uint64_t now);
bool switch_command(switch_t *state,const char *command,char *out,size_t size,uint64_t now);
#endif
