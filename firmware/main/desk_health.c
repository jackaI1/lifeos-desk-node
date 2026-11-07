#include "desk_health.h"
#include "lwip/sockets.h"
#include <string.h>
#include <unistd.h>
void desk_health_task(void *argument) {
    EventGroupHandle_t events = (EventGroupHandle_t)argument;
    int server = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (server >= 0) {
        struct sockaddr_in address = {.sin_family = AF_INET,
                                      .sin_port = htons(8092),
                                      .sin_addr = {.s_addr = htonl(INADDR_ANY)}};
        if (bind(server, (struct sockaddr *)&address, sizeof address) == 0 &&
            listen(server, 2) == 0) {
            while (!(xEventGroupGetBits(events) & DESK_HEALTH_STOP)) {
                fd_set set;
                FD_ZERO(&set);
                FD_SET(server, &set);
                struct timeval deadline = {.tv_sec = 0, .tv_usec = 100000};
                if (select(server + 1, &set, NULL, NULL, &deadline) <= 0)
                    continue;
                int client = accept(server, NULL, NULL);
                if (client < 0)
                    continue;
                struct timeval timeout = {.tv_sec = 0, .tv_usec = 200000};
                setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout);
                setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout);
                char data[22] = {0};
                size_t used = 0;
                while (used < 21) {
                    int n = recv(client, data + used, 21 - used, 0);
                    if (n <= 0)
                        break;
                    used += (size_t)n;
                }
                bool valid = used == 21 && !memcmp(data, "DESK/1 PING ", 12) && data[20] == '\n';
                for (unsigned i = 12; valid && i < 20; ++i)
                    valid =
                        (data[i] >= '0' && data[i] <= '9') || (data[i] >= 'a' && data[i] <= 'f');
                if (valid) {
                    memcpy(data + 7, "PONG", 4);
                    send(client, data, 21, 0);
                }
                close(client);
            }
        }
        close(server);
    }
    xEventGroupSetBits(events, DESK_HEALTH_DONE);
    vTaskDelete(NULL);
}
