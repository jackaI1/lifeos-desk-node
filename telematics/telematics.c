#include "telematics.h"
#include <math.h>
#include <string.h>
static int hex(char c) {
    if (c>='0'&&c<='9') return c-'0';
    if (c>='A'&&c<='F') return c-'A'+10;
    if (c>='a'&&c<='f') return c-'a'+10;
    return -1;
}
static bool number(const char *text, double *out) {
    if (!text || !*text) return false;
    double value=0, scale=1; bool point=false, digit=false;
    for (size_t i=0;text[i];++i) {
        if (text[i]=='.' && !point) { point=true; continue; }
        if (text[i]<'0'||text[i]>'9') return false;
        digit=true;
        if (point) { scale*=10; value+=(text[i]-'0')/scale; }
        else value=value*10+(text[i]-'0');
        if (value>100000000) return false;
    }
    *out=value;
    return digit && text[strlen(text)-1]!='.';
}
static bool integer(const char *s, unsigned maximum, uint8_t *out) {
    if (!*s) return false;
    unsigned n=0;
    for (size_t i=0;s[i];++i) {
        if (s[i]<'0'||s[i]>'9') return false;
        n=n*10+(unsigned)(s[i]-'0');
        if (n>maximum) return false;
    }
    *out=(uint8_t)n; return true;
}
static bool coordinate(const char *s, const char *hemisphere, bool latitude, double *out) {
    size_t digits=latitude ? 4U:5U;
    if (strlen(s)<digits || (strlen(s)>digits && s[digits]!='.')) return false;
    double raw;
    if (!number(s,&raw)) return false;
    double degrees=floor(raw/100), minutes=raw-degrees*100;
    double limit=latitude ? 90:180;
    if (minutes>=60 || degrees>limit || (degrees==limit && minutes!=0) || strlen(hemisphere)!=1) return false;
    char positive=latitude?'N':'E', negative=latitude?'S':'W';
    if (*hemisphere!=positive && *hemisphere!=negative) return false;
    *out=(degrees+minutes/60)*(*hemisphere==negative ? -1:1); return true;
}
static bool utc(const char *s) {
    double value;
    if (strlen(s)<6 || (strlen(s)>6 && s[6]!='.') || !number(s,&value)) return false;
    unsigned whole=(unsigned)value;
    return whole/10000<24 && whole/100%100<60 && whole%100<60;
}
static bool date(const char *s) {
    if (strlen(s)!=6) return false;
    unsigned values[3]={0};
    for (size_t i=0;i<6;++i) {
        if (s[i]<'0'||s[i]>'9') return false;
        values[i/2]=values[i/2]*10+(unsigned)(s[i]-'0');
    }
    unsigned day=values[0], month=values[1], year=2000+values[2];
    const unsigned days[]={31,28,31,30,31,30,31,31,30,31,30,31};
    return month>=1&&month<=12&&day>=1&&day<=days[month-1]+(month==2&&year%4==0 ? 1U:0U);
}
bool nmea_parse(const char *sentence, size_t length, gps_fix_t *out) {
    if (!sentence || !out || length<10 || length>82 || sentence[0]!='$') return false;
    if (length>=2 && sentence[length-2]=='\r' && sentence[length-1]=='\n') length-=2;
    if (sentence[length-3]!='*' || hex(sentence[length-2])<0 || hex(sentence[length-1])<0) return false;
    uint8_t checksum=0;
    for (size_t i=1;i<length-3;++i) {
        if (sentence[i]<' '||sentence[i]>'~'||sentence[i]=='*') return false;
        checksum^=(uint8_t)sentence[i];
    }
    if (checksum!=(uint8_t)(hex(sentence[length-2])*16+hex(sentence[length-1]))) return false;
    char copy[83]; memcpy(copy,sentence+1,length-4); copy[length-4]=0;
    char *fields[20]; size_t count=1; fields[0]=copy;
    for (size_t i=0;copy[i];++i) {
        if (copy[i]==',') {
            if (count>=20) return false;
            copy[i]=0; fields[count++]=copy+i+1;
        }
    }
    if (strlen(fields[0])!=5 || !((fields[0][0]=='G'&&fields[0][1]=='P') || (fields[0][0]=='G'&&fields[0][1]=='N'))) return false;
    gps_fix_t result={0}; memcpy(result.kind,fields[0]+2,3);
    if (!strcmp(result.kind,"GGA")) {
        double altitude,hdop;
        if (count!=15 || !utc(fields[1]) || !coordinate(fields[2],fields[3],true,&result.latitude) ||
            !coordinate(fields[4],fields[5],false,&result.longitude) || !integer(fields[6],8,&result.fix) || result.fix==0 ||
            !integer(fields[7],99,&result.satellites) || !number(fields[8],&hdop) || !number(fields[9],&altitude) || strcmp(fields[10],"M")) return false;
    } else if (!strcmp(result.kind,"RMC")) {
        double knots,course;
        if (count<12 || count>13 || !utc(fields[1]) || strcmp(fields[2],"A") ||
            !coordinate(fields[3],fields[4],true,&result.latitude) || !coordinate(fields[5],fields[6],false,&result.longitude) ||
            !number(fields[7],&knots) || knots>1000 || !number(fields[8],&course) || course>=360 || !date(fields[9])) return false;
        result.speed_kph=knots*1.852; result.fix=1;
    } else return false;
    *out=result; return true;
}
bool obd_parse(uint32_t id, const uint8_t *data, size_t length, obd_value_t *out) {
    if (!data || !out || length!=8 || id<0x7e8 || id>0x7ef || data[1]!=0x41) return false;
    obd_value_t result={data[2],0};
    if (data[2]==0x0c && data[0]==4) result.value=((unsigned)data[3]*256U+data[4])/4.0;
    else if (data[2]==0x0d && data[0]==3) result.value=data[3];
    else if (data[2]==0x05 && data[0]==3) result.value=(int)data[3]-40;
    else return false;
    *out=result; return true;
}
