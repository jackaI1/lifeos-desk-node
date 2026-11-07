#define _POSIX_C_SOURCE 200809L
#include "switch.h"
#include <arpa/inet.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t running=1;
static void stop(int signal_number) { (void)signal_number;running=0; }
static uint64_t milliseconds(void) { struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000; }
int main(int argc,char **argv) {
    if(argc!=3)return 2;
    char *end=NULL;long port=strtol(argv[1],&end,10);if(!end||*end||port<0||port>65535)return 2;
    switch_t state;switch_init(&state);if(!switch_load(&state,argv[2],milliseconds()))return 3;
    int server=socket(AF_INET,SOCK_STREAM,0);if(server<0)return 4;
    struct sockaddr_in address={.sin_family=AF_INET,.sin_port=htons((uint16_t)port),.sin_addr={.s_addr=htonl(UINT32_C(0x7f000001))}};
    if(bind(server,(struct sockaddr*)&address,sizeof address)||listen(server,16)){close(server);return 5;}
    socklen_t length=sizeof address;getsockname(server,(struct sockaddr*)&address,&length);printf("PORT %u\n",ntohs(address.sin_port));fflush(stdout);
    struct sigaction action={0};action.sa_handler=stop;sigaction(SIGTERM,&action,NULL);sigaction(SIGINT,&action,NULL);signal(SIGPIPE,SIG_IGN);
    int result=0;
    while(running){
        if(switch_tick(&state,milliseconds())&&!switch_save(&state,argv[2])){result=6;break;}
        fd_set set;FD_ZERO(&set);FD_SET(server,&set);struct timeval wait={.tv_sec=0,.tv_usec=50000};
        if(select(server+1,&set,NULL,NULL,&wait)<=0)continue;
        int client=accept(server,NULL,NULL);if(client<0)continue;
        struct timeval timeout={.tv_sec=0,.tv_usec=100000};setsockopt(client,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof timeout);setsockopt(client,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof timeout);
        char input[81]={0};size_t used=0;bool complete=false;
        uint64_t deadline=milliseconds()+300;
        while(used<80&&milliseconds()<deadline){char c;ssize_t n=recv(client,&c,1,0);if(n!=1||c==0)break;if(c=='\n'){complete=true;break;}input[used++]=c;}
        char output[128]="ERR\n";
        if(complete){switch_t previous=state;switch_command(&state,input,output,sizeof output,milliseconds());
            if(memcmp(&previous,&state,sizeof state)&&!switch_save(&state,argv[2])){state=previous;strcpy(output,"ERR storage\n");}}
        (void)send(client,output,strlen(output),0);close(client);
    }
    close(server);return result;
}
