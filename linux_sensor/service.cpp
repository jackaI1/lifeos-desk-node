#include "desk_sensor.h"
#include <array>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <stdexcept>
#include <sys/ioctl.h>
#include <unistd.h>
class Device {
    int fd_;
public:
    explicit Device(const char* path):fd_(open(path,O_RDWR|O_CLOEXEC)){if(fd_<0)throw std::runtime_error("open sensor failed");}
    ~Device(){close(fd_);}
    Device(const Device&)=delete;
    desk_registers get(){desk_registers data{};if(ioctl(fd_,DESK_GET,&data))throw std::runtime_error("GET failed");return data;}
    void inject(const desk_registers& data){if(ioctl(fd_,DESK_INJECT,&data))throw std::runtime_error("INJECT failed");}
    void clear(){if(ioctl(fd_,DESK_CLEAR))throw std::runtime_error("CLEAR failed");}
    void test(){
        auto good=get(); if(good.alarm)throw std::runtime_error("bad initial sample");
        desk_registers from_read{};if(read(fd_,&from_read,sizeof from_read)!=sizeof from_read||memcmp(from_read.raw,good.raw,6))throw std::runtime_error("read/ioctl disagree");
        auto bad=good;bad.raw[2]^=1;inject(bad);if(!get().alarm)throw std::runtime_error("bad CRC not alarmed");
        inject(good);if(!get().alarm)throw std::runtime_error("alarm not held");clear();if(get().alarm)throw std::runtime_error("alarm did not clear");
        if(ioctl(fd_,_IO('D',99))!=-1||errno!=ENOTTY)throw std::runtime_error("unknown ioctl accepted");
        std::cout<<"PASS: I2C, read/ioctl, checksum fault, held alarm, clear and invalid ioctl"<<std::endl;
    }
};
int main(int argc,char** argv){try{Device device(argc>1?argv[1]:"/dev/desk-sensor");device.test();return 0;}catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}}
