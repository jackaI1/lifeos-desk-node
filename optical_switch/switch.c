#define _POSIX_C_SOURCE 200809L
#include "switch.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static bool valid(unsigned p) { return p>=1&&p<=16; }
void switch_init(switch_t *s) { memset(s,0,sizeof *s); }
bool switch_connect(switch_t *s,unsigned a,unsigned b,uint64_t now) {
    if(!valid(a)||!valid(b)||a==b||s->peer[a-1]||s->peer[b-1]||s->fault[a-1]||s->fault[b-1])return false;
    s->peer[a-1]=(uint8_t)b;s->peer[b-1]=(uint8_t)a;
    s->deadline[a-1]=now+200;s->deadline[b-1]=now+200;return true;
}
bool switch_disconnect(switch_t *s,unsigned p) {
    if(!valid(p))return false;
    unsigned other=s->peer[p-1]; s->peer[p-1]=s->fault[p-1]=0;s->deadline[p-1]=0;
    if(other){s->peer[other-1]=s->fault[other-1]=0;s->deadline[other-1]=0;}return true;
}
bool switch_ack(switch_t *s,unsigned p) {
    if(!valid(p)||!s->peer[p-1]||s->fault[p-1])return false;
    s->deadline[p-1]=0;return true;
}
bool switch_tick(switch_t *s,uint64_t now) {
    bool changed=false;
    for(unsigned i=0;i<16;++i) if(s->deadline[i]&&now>=s->deadline[i]){s->fault[i]=1;s->deadline[i]=0;changed=true;}
    return changed;
}
static uint8_t crc(const uint8_t *data,size_t size) {
    uint8_t v=0;for(size_t i=0;i<size;++i){v^=data[i];for(unsigned b=0;b<8;++b)v=(uint8_t)((v<<1)^((v&128U)?0x07U:0U));}return v;
}
bool switch_save(const switch_t *s,const char *path) {
    uint8_t data[41]={0};memcpy(data,"DESKSW1",7);memcpy(data+8,s->peer,16);memcpy(data+24,s->fault,16);data[40]=crc(data,40);
    char tmp[1024];if(snprintf(tmp,sizeof tmp,"%s.XXXXXX",path)>=(int)sizeof tmp)return false;
    int fd=mkstemp(tmp);if(fd<0)return false;
    bool ok=write(fd,data,sizeof data)==sizeof data && fsync(fd)==0;
    if(close(fd)!=0)ok=false;
    if(ok)ok=rename(tmp,path)==0;
    if(!ok)unlink(tmp);
    return ok;
}
bool switch_load(switch_t *s,const char *path,uint64_t now) {
    uint8_t data[42];FILE *file=fopen(path,"rb");if(!file)return errno==ENOENT;
    size_t n=fread(data,1,sizeof data,file);bool io=ferror(file)==0;fclose(file);
    if(!io||n!=41||memcmp(data,"DESKSW1",8)||crc(data,40)!=data[40])return false;
    switch_t copy;switch_init(&copy);memcpy(copy.peer,data+8,16);memcpy(copy.fault,data+24,16);
    for(unsigned i=0;i<16;++i){unsigned p=copy.peer[i];if(p>16||p==i+1||copy.fault[i]>1||(p&&copy.peer[p-1]!=i+1))return false;
        if(p&&!copy.fault[i])copy.deadline[i]=now+200;}
    *s=copy;return true;
}
bool switch_command(switch_t *s,const char *command,char *out,size_t size,uint64_t now) {
    unsigned a,b;char extra;bool ok=false;
    if(sscanf(command,"CONNECT %u %u %c",&a,&b,&extra)==2)ok=switch_connect(s,a,b,now);
    else if(sscanf(command,"DISCONNECT %u %c",&a,&extra)==1)ok=switch_disconnect(s,a);
    else if(sscanf(command,"ACK %u %c",&a,&extra)==1)ok=switch_ack(s,a);
    else if(sscanf(command,"STATUS %u %c",&a,&extra)==1&&valid(a)) {
        int n=snprintf(out,size,"PORT %u PEER %u FAULT %u\n",a,s->peer[a-1],s->fault[a-1]);return n>0&&(size_t)n<size;
    }
    int n=snprintf(out,size,"%s\n",ok?"OK":"ERR");return n>0&&(size_t)n<size;
}
