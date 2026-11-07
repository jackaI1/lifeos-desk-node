#ifndef DESK_REPLAY_H
#define DESK_REPLAY_H
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
int desk_replay_read_line(FILE *input, char out[80]);
bool desk_replay_sensor_bytes(const char *line, uint8_t raw[6]);
#endif
