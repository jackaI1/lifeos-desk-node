#pragma once
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
using socket_handle = SOCKET;
constexpr socket_handle invalid_socket = INVALID_SOCKET;
inline int close_socket(socket_handle s) { return closesocket(s); }
using socket_length = int;
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
using socket_handle = int;
constexpr socket_handle invalid_socket = -1;
inline int close_socket(socket_handle s) { return close(s); }
using socket_length = socklen_t;
#endif
#include <stdexcept>
#include <utility>
class SocketRuntime {
  public:
    SocketRuntime() {
#ifdef _WIN32
        WSADATA data{};
        if (WSAStartup(MAKEWORD(2, 2), &data))
            throw std::runtime_error("WSAStartup failed");
#endif
    }
    ~SocketRuntime() {
#ifdef _WIN32
        WSACleanup();
#endif
    }
};
class Socket {
    socket_handle handle_ = invalid_socket;

  public:
    explicit Socket(socket_handle s = invalid_socket) : handle_(s) {}
    Socket(const Socket &) = delete;
    Socket &operator=(const Socket &) = delete;
    Socket(Socket &&other) noexcept : handle_(std::exchange(other.handle_, invalid_socket)) {}
    Socket &operator=(Socket &&other) noexcept {
        if (this != &other) {
            reset();
            handle_ = std::exchange(other.handle_, invalid_socket);
        }
        return *this;
    }
    ~Socket() { reset(); }
    void reset() {
        if (handle_ != invalid_socket) {
            close_socket(handle_);
            handle_ = invalid_socket;
        }
    }
    socket_handle get() const { return handle_; }
    explicit operator bool() const { return handle_ != invalid_socket; }
    void timeout(unsigned milliseconds) {
#ifdef _WIN32
        DWORD value = milliseconds;
        setsockopt(handle_, SOL_SOCKET, SO_RCVTIMEO, reinterpret_cast<const char *>(&value),
                   sizeof value);
        setsockopt(handle_, SOL_SOCKET, SO_SNDTIMEO, reinterpret_cast<const char *>(&value),
                   sizeof value);
#else
        timeval value{static_cast<long>(milliseconds / 1000),
                      static_cast<int>((milliseconds % 1000) * 1000)};
        setsockopt(handle_, SOL_SOCKET, SO_RCVTIMEO, &value, sizeof value);
        setsockopt(handle_, SOL_SOCKET, SO_SNDTIMEO, &value, sizeof value);
#ifdef SO_NOSIGPIPE
        int yes = 1;
        setsockopt(handle_, SOL_SOCKET, SO_NOSIGPIPE, &yes, sizeof yes);
#endif
#endif
    }
};
inline bool send_all(socket_handle socket, const char *data, size_t size) {
    while (size) {
#ifdef MSG_NOSIGNAL
        int n = static_cast<int>(send(socket, data, size, MSG_NOSIGNAL));
#else
        int n = send(socket, data, static_cast<int>(size), 0);
#endif
        if (n <= 0)
            return false;
        data += n;
        size -= static_cast<size_t>(n);
    }
    return true;
}
