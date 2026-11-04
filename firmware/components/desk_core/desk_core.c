#include "desk_core.h"
#include "cJSON.h"
#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

uint8_t desk_crc8(const uint8_t *data, size_t length) {
    uint8_t crc=0xff;
    for (size_t i=0;i<length;++i) {
        crc ^= data[i];
        for (int bit=0;bit<8;++bit)
            crc = (crc & 0x80) ? (uint8_t)((crc<<1)^0x31) : (uint8_t)(crc<<1);
    }
    return crc;
}
bool desk_decode_sht31(const uint8_t raw[6], desk_reading_t *r) {
    if (desk_crc8(raw,2)!=raw[2] || desk_crc8(raw+3,2)!=raw[5]) return false;
    uint32_t t=((uint32_t)raw[0]<<8)|raw[1], h=((uint32_t)raw[3]<<8)|raw[4];
    r->temperature_mc = -45000 + (int32_t)((175000ULL*t+32767)/65535);
    r->humidity_mpermil = (int32_t)((100000ULL*h+32767)/65535);
    return true;
}
bool desk_ring_valid(const desk_ring_t *r) {
    return r->head<DESK_RING_CAPACITY && r->count<=DESK_RING_CAPACITY;
}
void desk_ring_push(desk_ring_t *r, desk_reading_t x) {
    if (r->count==DESK_RING_CAPACITY) {
        r->head=(r->head+1)%DESK_RING_CAPACITY;
        --r->count;
        if (r->dropped<UINT32_MAX) ++r->dropped;
    }
    r->readings[(r->head+r->count)%DESK_RING_CAPACITY]=x;
    ++r->count;
}
const desk_reading_t *desk_ring_at(const desk_ring_t *r,uint32_t offset) {
    return offset<r->count ? &r->readings[(r->head+offset)%DESK_RING_CAPACITY] : NULL;
}
bool desk_ring_pop(desk_ring_t *r,uint32_t expected_sequence) {
    const desk_reading_t *x=desk_ring_at(r,0);
    if (!x || x->sequence!=expected_sequence) return false;
    r->head=(r->head+1)%DESK_RING_CAPACITY; --r->count;
    return true;
}
/* Parse exactly one object, including whitespace, with no ignored tail or NUL escape. */
static cJSON *object(const char *json) {
    if (strlen(json)>2047 || strstr(json,"\\u0000")) return NULL;
    /* cJSON is recursive. Bound nesting before entering it on a small RTOS stack.
       Brackets inside strings (including escaped quotes) do not count. */
    unsigned depth=0; bool quoted=false, escaped=false;
    for (const char *p=json;*p;++p) {
        if (quoted) {
            if (escaped) escaped=false;
            else if (*p=='\\') escaped=true;
            else if (*p=='"') quoted=false;
        } else if (*p=='"') quoted=true;
        else if (*p=='{' || *p=='[') { if (++depth>8) return NULL; }
        else if (*p=='}' || *p==']') { if (!depth) return NULL; --depth; }
    }
    if (quoted || depth) return NULL;
    cJSON *root=cJSON_ParseWithOpts(json,NULL,true);
    if (!cJSON_IsObject(root)) { cJSON_Delete(root); return NULL; }
    /* Duplicate keys are ambiguous: reject them at every object boundary we consume. */
    return root;
}
static const cJSON *unique(const cJSON *root,const char *key) {
    const cJSON *found=NULL, *item=NULL;
    cJSON_ArrayForEach(item,root) {
        if (item->string && !strcmp(item->string,key)) {
            if (found) return NULL;
            found=item;
        }
    }
    return found;
}
static bool copy_text(char *out,size_t capacity,const cJSON *value) {
    if (!cJSON_IsString(value) || !value->valuestring[0] || strlen(value->valuestring)>=capacity) return false;
    strcpy(out,value->valuestring);
    return true;
}
bool desk_parse_event(const char *json,desk_event_t *event) {
    cJSON *root=object(json); if (!root) return false;
    const cJSON *next=unique(root,"next");
    desk_event_t candidate={0}; bool ok=false;
    if (cJSON_IsNull(next)) {
        strcpy(candidate.title,"No upcoming events"); ok=true;
    } else if (cJSON_IsObject(next)) {
        ok=copy_text(candidate.title,sizeof candidate.title,unique(next,"title")) &&
           copy_text(candidate.when,sizeof candidate.when,unique(next,"when")) &&
           copy_text(candidate.kind,sizeof candidate.kind,unique(next,"kind"));
        ok=ok && (!strcmp(candidate.kind,"class") || !strcmp(candidate.kind,"deadline"));
    }
    if (ok) *event=candidate;
    cJSON_Delete(root); return ok;
}
void desk_body_init(desk_body_t *b,char *data,size_t capacity) {
    *b=(desk_body_t){.data=data,.capacity=capacity};
    if (capacity) data[0]=0;
}
bool desk_body_append(desk_body_t *b,const char *data,size_t length) {
    if (b->overflow || b->capacity==0 || length>=b->capacity-b->length || memchr(data,0,length)) {
        b->overflow=true; return false;
    }
    memcpy(b->data+b->length,data,length); b->length+=length; b->data[b->length]=0;
    return true;
}
bool desk_encode_readings(char *out,size_t capacity,const char *device,const char *session,const desk_ring_t *ring) {
    cJSON *root=cJSON_CreateObject();
    if (!root) return false;
    bool ok=cJSON_AddStringToObject(root,"device",device) && cJSON_AddStringToObject(root,"session",session);
    cJSON *array=cJSON_AddArrayToObject(root,"readings");
    ok=ok && array && cJSON_AddNumberToObject(root,"dropped",ring->dropped);
    for (uint32_t i=0;ok && i<ring->count;++i) {
        const desk_reading_t *r=desk_ring_at(ring,i);
        cJSON *item=cJSON_CreateObject();
        if (!item) { ok=false; break; }
        ok=cJSON_AddItemToArray(array,item);
        if (!ok) { cJSON_Delete(item); break; }
        ok=cJSON_AddNumberToObject(item,"sequence",r->sequence) &&
           cJSON_AddNumberToObject(item,"timestamp",(double)r->timestamp) &&
           cJSON_AddNumberToObject(item,"temperature_mc",r->temperature_mc) &&
           cJSON_AddNumberToObject(item,"humidity_mpermil",r->humidity_mpermil);
    }
    ok=ok && capacity<=INT32_MAX && cJSON_PrintPreallocated(root,out,(int)capacity,false);
    cJSON_Delete(root); return ok;
}
bool desk_ack_matches(const char *json,uint32_t count,uint32_t sequence) {
    cJSON *root=object(json); if (!root) return false;
    const cJSON *accepted=unique(root,"accepted"), *last=unique(root,"last_sequence");
    bool ok=cJSON_IsNumber(accepted) && cJSON_IsNumber(last) &&
        accepted->valuedouble==(double)count && last->valuedouble==(double)sequence;
    cJSON_Delete(root); return ok;
}

/* Original compact 5-column uppercase font: each byte is a vertical 7-pixel column. */
static const uint8_t glyphs[][5]={
    {0x3e,0x51,0x49,0x45,0x3e},{0,0x42,0x7f,0x40,0},{0x62,0x51,0x49,0x49,0x46},
    {0x22,0x41,0x49,0x49,0x36},{0x18,0x14,0x12,0x7f,0x10},{0x2f,0x49,0x49,0x49,0x31},
    {0x3e,0x49,0x49,0x49,0x32},{1,0x71,9,5,3},{0x36,0x49,0x49,0x49,0x36},{0x26,0x49,0x49,0x49,0x3e},
    {0x7e,9,9,9,0x7e},{0x7f,0x49,0x49,0x49,0x36},{0x3e,0x41,0x41,0x41,0x22},
    {0x7f,0x41,0x41,0x22,0x1c},{0x7f,0x49,0x49,0x49,0x41},{0x7f,9,9,9,1},
    {0x3e,0x41,0x49,0x49,0x7a},{0x7f,8,8,8,0x7f},{0,0x41,0x7f,0x41,0},
    {0x20,0x40,0x41,0x3f,1},{0x7f,8,0x14,0x22,0x41},{0x7f,0x40,0x40,0x40,0x40},
    {0x7f,2,0x0c,2,0x7f},{0x7f,4,8,0x10,0x7f},{0x3e,0x41,0x41,0x41,0x3e},
    {0x7f,9,9,9,6},{0x3e,0x41,0x51,0x21,0x5e},{0x7f,9,0x19,0x29,0x46},
    {0x26,0x49,0x49,0x49,0x32},{1,1,0x7f,1,1},{0x3f,0x40,0x40,0x40,0x3f},
    {0x1f,0x20,0x40,0x20,0x1f},{0x7f,0x20,0x18,0x20,0x7f},{0x63,0x14,8,0x14,0x63},
    {3,4,0x78,4,3},{0x61,0x51,0x49,0x45,0x43}
};
static void text(uint8_t *frame,unsigned page,const char *str,size_t limit) {
    for (size_t i=0;i<limit && i<21 && str[i];++i) {
        unsigned char c=(unsigned char)str[i]; c=(unsigned char)toupper(c);
        uint8_t special[5]={0}; const uint8_t *g=special;
        if (c>='0' && c<='9') g=glyphs[c-'0'];
        else if (c>='A' && c<='Z') g=glyphs[10+c-'A'];
        else if (c==':') special[2]=0x24;
        else if (c=='.') special[2]=0x40;
        else if (c=='-') memset(special,8,5);
        else if (c=='%') { special[0]=0x63;special[1]=0x13;special[2]=8;special[3]=0x64;special[4]=0x63; }
        else if (c!=' ') { special[1]=2;special[2]=0x59;special[3]=6; }
        memcpy(frame+page*128+i*6,g,5);
    }
}
void desk_render(uint8_t frame[DESK_FRAME_SIZE],const desk_event_t *event,const desk_reading_t *r,bool online,uint32_t dropped) {
    memset(frame,0,DESK_FRAME_SIZE);
    text(frame,0,online?"LIFEOS UPDATED":"LIFEOS OFFLINE",21);
    text(frame,1,event->kind, sizeof event->kind);
    /* Three clipped title rows; renderer never reads beyond the fixed event buffer. */
    size_t length=0; while (length<sizeof event->title && event->title[length]) ++length;
    for (unsigned row=0;row<3;++row) if (length>row*21) text(frame,2+row,event->title+row*21,length-row*21);
    text(frame,5,event->when,sizeof event->when);
    char line[40];
    if (r) {
        /* Signed tenths via integer formatting also handles -0.5 C. */
        int t=r->temperature_mc/100, a=t<0?-t:t;
        snprintf(line,sizeof line,"%s%d.%dC %ld.%ld%%RH",t<0?"-":"",a/10,a%10,
            (long)(r->humidity_mpermil/1000),(long)((r->humidity_mpermil/100)%10));
        text(frame,6,line,21);
    } else text(frame,6,"SENSOR UNAVAILABLE",21);
    snprintf(line,sizeof line,"LOST %lu",(unsigned long)dropped);
    text(frame,7,line,21);
}

bool desk_format_cycle_log(char *out,size_t capacity,const desk_reading_t *reading,
                           uint32_t queued,uint32_t dropped,bool upload_acked) {
    int length;
    if (reading) {
        length=snprintf(out,capacity,
            "desk sample=%lu utc=%lld temp_mc=%ld rh_mpermil=%ld queued=%lu lost=%lu upload=%s\r\n",
            (unsigned long)reading->sequence,(long long)reading->timestamp,
            (long)reading->temperature_mc,(long)reading->humidity_mpermil,
            (unsigned long)queued,(unsigned long)dropped,upload_acked?"acked":"pending");
    } else {
        length=snprintf(out,capacity,"desk sample=unavailable queued=%lu lost=%lu upload=%s\r\n",
            (unsigned long)queued,(unsigned long)dropped,upload_acked?"acked":"pending");
    }
    return length>=0 && (size_t)length<capacity;
}
