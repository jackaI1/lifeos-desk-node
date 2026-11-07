#include <gtest/gtest.h>
#include <array>
#include <cstring>
#include <string>
#include <random>
extern "C" {
#include "desk_core.h"
#include "desk_radio.h"
#include "telematics.h"
#include "alert.h"
}
TEST(Radio, SchemaCrcBoundsAndNotifyRate) {
    uint8_t bytes[16]; desk_radio_reading_t in{12,-1000,50000},out{};
    ASSERT_TRUE(desk_ble_encode(bytes,sizeof bytes,&in));
    ASSERT_TRUE(desk_ble_decode(bytes,sizeof bytes,&out));
    EXPECT_EQ(out.temperature_mc,-1000); EXPECT_EQ(out.sequence,12U);
    EXPECT_EQ(desk_radio_crc(reinterpret_cast<const uint8_t*>("123456789"),9),0x29b1);
    EXPECT_FALSE(desk_ble_encode(bytes,15,&in));
    EXPECT_FALSE(desk_ble_decode(bytes,15,&out)); bytes[5]^=1;
    EXPECT_FALSE(desk_ble_decode(bytes,16,&out));
    uint64_t last=0; bool sent=false;
    EXPECT_TRUE(desk_notify_due(0,&last,&sent)); EXPECT_FALSE(desk_notify_due(999,&last,&sent));
    EXPECT_TRUE(desk_notify_due(1000,&last,&sent)); EXPECT_FALSE(desk_notify_due(1,&last,&sent));
}
TEST(Radio, DroppedConnectionBackoffAndRecovery) {
    desk_wifi_retry_t retry{};
    EXPECT_EQ(desk_wifi_lost(&retry,0),250U);
    EXPECT_FALSE(desk_wifi_due(&retry,249)); EXPECT_TRUE(desk_wifi_due(&retry,250));
    for(unsigned i=0;i<20;++i) EXPECT_LE(desk_wifi_lost(&retry,1000),8000U);
    EXPECT_EQ(retry.attempts,6U); desk_wifi_connected(&retry);
    EXPECT_FALSE(desk_wifi_due(&retry,100000)); EXPECT_EQ(desk_wifi_lost(&retry,0),250U);
}
static std::string sentence(std::string body) {
    unsigned crc=0; for(unsigned char c:body) crc^=c;
    char suffix[4]; std::snprintf(suffix,sizeof suffix,"*%02X",crc);
    return "$"+body+suffix;
}
TEST(Telematics, RecordedGgaAndRmc) {
    gps_fix_t fix{};
    std::string gga="$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47";
    ASSERT_TRUE(nmea_parse(gga.data(),gga.size(),&fix));
    EXPECT_NEAR(fix.latitude,48.1173,1e-6); EXPECT_NEAR(fix.longitude,11.5166667,1e-6); EXPECT_EQ(fix.satellites,8);
    std::string rmc="$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A";
    ASSERT_TRUE(nmea_parse(rmc.data(),rmc.size(),&fix)); EXPECT_NEAR(fix.speed_kph,41.4848,1e-6);
    for(size_t n=0;n<gga.size();++n) EXPECT_FALSE(nmea_parse(gga.data(),n,&fix));
    gga[20]^=1; EXPECT_FALSE(nmea_parse(gga.data(),gga.size(),&fix));
}
TEST(Telematics, RejectMalformedFieldsEvenWithValidChecksum) {
    gps_fix_t fix{};
    for(const auto& body: {"GPGGA,123519,4867.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,",
        "GPGGA,246000,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,",
        "GPGGA,123519,4807.038,X,01131.000,E,1,08,0.9,545.4,M,46.9,M,,",
        "GPGGA,123519,4807.,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,",
        "GPRMC,123519,V,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W",
        "GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,310294,003.1,W"}) {
        auto data=sentence(body); EXPECT_FALSE(nmea_parse(data.data(),data.size(),&fix))<<data;
    }
}
TEST(Telematics, ObdSpeedRpmCoolantAndBadLengths) {
    obd_value_t result{}; uint8_t data[]={3,0x41,0x0d,88,0,0,0,0};
    ASSERT_TRUE(obd_parse(0x7e8,data,8,&result)); EXPECT_EQ(result.value,88);
    data[0]=4; data[2]=0x0c; data[3]=0x1a; data[4]=0xf8;
    ASSERT_TRUE(obd_parse(0x7e8,data,8,&result)); EXPECT_EQ(result.value,1726);
    data[0]=3; data[2]=5; data[3]=123;
    ASSERT_TRUE(obd_parse(0x7ef,data,8,&result)); EXPECT_EQ(result.value,83);
    for(size_t n=0;n<8;++n) EXPECT_FALSE(obd_parse(0x7e8,data,n,&result));
    EXPECT_FALSE(obd_parse(0x7e7,data,8,&result)); data[1]=0x40; EXPECT_FALSE(obd_parse(0x7e8,data,8,&result));
}
TEST(Core, CorruptedSensorAndBoundedBuffers) {
    uint8_t sensor[]={0x66,0x66,0,0x80,0,0}; sensor[2]=desk_crc8(sensor,2); sensor[5]=desk_crc8(sensor+3,2);
    desk_reading_t reading{}; ASSERT_TRUE(desk_decode_sht31(sensor,&reading));
    sensor[5]^=1; EXPECT_FALSE(desk_decode_sht31(sensor,&reading));
    char buffer[5]; desk_body_t body; desk_body_init(&body,buffer,sizeof buffer);
    ASSERT_TRUE(desk_body_append(&body,"1234",4)); EXPECT_FALSE(desk_body_append(&body,"5",1));
    EXPECT_TRUE(body.overflow); EXPECT_EQ(buffer[4],0);
    desk_ring_t ring{}; for(unsigned i=1;i<=70;++i) { reading.sequence=i; desk_ring_push(&ring,reading); }
    EXPECT_EQ(ring.count,64U); EXPECT_EQ(ring.dropped,6U); EXPECT_EQ(desk_ring_at(&ring,0)->sequence,7U);
    EXPECT_FALSE(desk_ring_pop(&ring,1)); EXPECT_TRUE(desk_ring_pop(&ring,7));
}
TEST(Alert, EveryStateEventTransition) {
    const uint8_t table[5][7]={{1,0,0,3,0,0,0},{1,0,2,3,1,1,2},{2,0,2,3,2,2,2},{3,3,3,3,4,3,3},{3,4,4,3,4,4,4}};
    for(uint8_t state=0;state<5;++state) for(uint8_t event=0;event<7;++event) {
        alert_t fsm{}; alert_init(&fsm); fsm.state=state;
        alert_step(&fsm,event,1); EXPECT_EQ(fsm.state,table[state][event])<<int(state)<<":"<<int(event);
    }
}
TEST(Alert, HeldFaultDebounceTimeoutAndRandomReplay) {
    alert_t f{}; alert_init(&f); alert_step(&f,ALERT_ON,0); alert_step(&f,ALERT_TIMEOUT,10);
    EXPECT_EQ(f.state,ALERT_WARNING); alert_step(&f,ALERT_FAULT,20); alert_step(&f,ALERT_CLEAR,30);
    EXPECT_EQ(f.state,ALERT_LATCHED); alert_step(&f,ALERT_IGN_OFF,40); alert_step(&f,ALERT_CLEAR,50);
    alert_step(&f,ALERT_TICK,549); EXPECT_TRUE(alert_alarm(&f)); alert_step(&f,ALERT_TICK,550); EXPECT_EQ(f.state,ALERT_OFF);
    alert_step(&f,ALERT_FAULT,551); alert_step(&f,ALERT_CLEAR,552); alert_step(&f,ALERT_FAULT,553); EXPECT_EQ(f.state,ALERT_LATCHED);
    std::mt19937 random(42); for(uint32_t i=554;i<10554;++i) { alert_step(&f,static_cast<uint8_t>(random()%7),i); ASSERT_LT(f.state,5); if(f.state>=2) ASSERT_TRUE(alert_alarm(&f)); }
    alert_step(&f,ALERT_ON,0); EXPECT_EQ(f.state,ALERT_LATCHED);
}
extern "C" {
#include "replay.h"
}
TEST(Replay, ExactParsingAndLineLimits) {
    uint8_t bytes[6]; EXPECT_TRUE(desk_replay_sensor_bytes("S 666600800000",bytes));
    for(const char* input:{"S 66660080000", "S 666600800000x", "S 66660080000g", "X 666600800000"}) EXPECT_FALSE(desk_replay_sensor_bytes(input,bytes));
    FILE* stream=std::tmpfile(); ASSERT_NE(stream,nullptr);
    std::string overlong(80,'x'); std::fwrite(overlong.data(),1,overlong.size(),stream); std::rewind(stream);
    char out[80]; EXPECT_EQ(desk_replay_read_line(stream,out),-1); std::fclose(stream);
    stream=std::tmpfile(); ASSERT_NE(stream,nullptr); const char embedded[]={'a',0,'b','\n'};
    std::fwrite(embedded,1,sizeof embedded,stream); std::rewind(stream);
    EXPECT_EQ(desk_replay_read_line(stream,out),-1); std::fclose(stream);
}
#include "drivers.hpp"
class FakeI2c final:public desk::I2c {
public:
 desk::Result fault=desk::Result::ok;bool corrupt=false;
 desk::Result transfer(uint8_t address,const uint8_t* tx,size_t txsize,uint8_t* rx,size_t size)override{
  EXPECT_EQ(address,0x44);EXPECT_EQ(txsize,2U);EXPECT_EQ(tx[0],0x24);EXPECT_EQ(size,6U);
  if(fault!=desk::Result::ok)return fault;
  const uint8_t sample[]={0x66,0x66,0x93,0x80,0,0xa2};std::memcpy(rx,sample,6);if(corrupt)rx[2]^=1;return desk::Result::ok;
 }
};
class FakeUart final:public desk::Uart {public:std::string output;size_t fail_after=100;bool byte(uint8_t b)override{if(output.size()>=fail_after)return false;output.push_back(static_cast<char>(b));return true;}};
TEST(Stm32, SharedDriversHandleSensorFaultsAndBoundedUart){
 FakeI2c bus;desk::Sensor sensor(bus);int32_t t=-1;uint32_t h=0;
 ASSERT_EQ(sensor.read(t,h),desk::Result::ok);EXPECT_EQ(t,25000);EXPECT_EQ(h,50001U);
 for(auto fault:{desk::Result::nack,desk::Result::timeout}){bus.fault=fault;EXPECT_EQ(sensor.read(t,h),fault);}
 bus.fault=desk::Result::ok;bus.corrupt=true;EXPECT_EQ(sensor.read(t,h),desk::Result::crc);
 FakeUart uart;desk::Logger log(uart);EXPECT_TRUE(log.text("sample\n"));EXPECT_EQ(uart.output,"sample\n");
 EXPECT_FALSE(log.text("1234",4));uart.fail_after=uart.output.size();EXPECT_FALSE(log.text("x"));
}
