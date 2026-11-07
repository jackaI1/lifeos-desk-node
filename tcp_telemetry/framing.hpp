#pragma once
#include <cstdint>
#include <vector>
#include <stdexcept>
#include <array>
inline uint32_t frame_crc(const uint8_t* data,size_t length) {
    uint32_t crc=0xffffffffU;
    for(size_t i=0;i<length;++i){crc^=data[i];for(unsigned b=0;b<8;++b)crc=(crc>>1)^((crc&1U)?0xedb88320U:0U);}
    return crc^0xffffffffU;
}
inline std::vector<uint8_t> encode_frame(const std::vector<uint8_t>& payload) {
    if(payload.empty()||payload.size()>4096)throw std::invalid_argument("payload must be 1..4096 bytes");
    std::vector<uint8_t> out{static_cast<uint8_t>(payload.size()>>8),static_cast<uint8_t>(payload.size())};
    out.insert(out.end(),payload.begin(),payload.end());uint32_t crc=frame_crc(out.data(),out.size());
    for(int i=3;i>=0;--i)out.push_back(static_cast<uint8_t>(crc>>(i*8)));
    return out;
}
// Incremental decoder is bounded even when peers send one byte at a time.
class Decoder {
    std::array<uint8_t,4102> buffer_{};
    size_t used_=0,expected_=0;
public:
    enum class Result {more,ready,invalid};
    Result push(uint8_t byte) {
        if(used_>=buffer_.size())return Result::invalid;
        buffer_[used_++]=byte;
        if(used_==2){size_t size=static_cast<size_t>(buffer_[0])*256+buffer_[1];if(!size||size>4096)return Result::invalid;expected_=size+6;}
        if(expected_&&used_==expected_){
            uint32_t received=0;for(size_t i=expected_-4;i<expected_;++i)received=(received<<8)|buffer_[i];
            return received==frame_crc(buffer_.data(),expected_-4)?Result::ready:Result::invalid;
        }
        return Result::more;
    }
    std::vector<uint8_t> payload()const {return {buffer_.begin()+2,buffer_.begin()+static_cast<std::ptrdiff_t>(expected_-4)};}
    void reset(){used_=expected_=0;}
};
