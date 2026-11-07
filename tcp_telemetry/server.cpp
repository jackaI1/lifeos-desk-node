#include "socket.hpp"
#include "framing.hpp"
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <iostream>
#include <mutex>
#include <thread>
#include <vector>
#include <string>
class Server {
    Socket listener_;
    std::mutex mutex_;
    std::condition_variable work_;
    std::deque<Socket> queue_;
    std::vector<std::thread> workers_;
    bool stopping_ = false;
    uint64_t accepted_ = 0, rejected_ = 0;
    void serve(Socket client) {
        client.timeout(200);
        Decoder decoder;
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
        bool valid = false;
        while (std::chrono::steady_clock::now() < deadline) {
            char input[512];
            int n = recv(client.get(), input, sizeof input, 0);
            if (n <= 0)
                break;
            bool done = false;
            for (int i = 0; i < n; ++i) {
                auto result = decoder.push(static_cast<uint8_t>(input[i]));
                if (result == Decoder::Result::invalid) {
                    done = true;
                    break;
                }
                if (result == Decoder::Result::ready) {
                    auto payload = decoder.payload();
                    // A desk reading is signed millidegrees and unsigned RH/1000.
                    if (payload.size() != 8) {
                        done = true;
                        break;
                    }
                    uint32_t raw = 0, humidity = 0;
                    for (unsigned j = 0; j < 4; ++j) {
                        raw = (raw << 8) | payload[j];
                        humidity = (humidity << 8) | payload[j + 4];
                    }
                    int64_t temperature =
                        raw <= INT32_MAX ? raw : static_cast<int64_t>(raw) - 4294967296LL;
                    if (temperature < -45000 || temperature > 125000 || humidity > 100000) {
                        done = true;
                        break;
                    }
                    auto ack = encode_frame(payload);
                    valid = send_all(client.get(), reinterpret_cast<const char *>(ack.data()),
                                     ack.size());
                    done = true;
                    break; // one bounded transaction per connection
                }
            }
            if (done)
                break;
        }
        std::lock_guard<std::mutex> lock(mutex_);
        if (valid)
            ++accepted_;
        else
            ++rejected_;
    }
    void worker() {
        while (true) {
            Socket client;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                work_.wait(lock, [this] { return stopping_ || !queue_.empty(); });
                if (stopping_ && queue_.empty())
                    return;
                client = std::move(queue_.front());
                queue_.pop_front();
            }
            serve(std::move(client));
        }
    }

  public:
    Server(uint16_t port, unsigned threads) : listener_(socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)) {
        if (!listener_)
            throw std::runtime_error("socket failed");
        sockaddr_in address{};
        address.sin_family = AF_INET;
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        address.sin_port = htons(port);
        if (bind(listener_.get(), reinterpret_cast<sockaddr *>(&address), sizeof address) ||
            listen(listener_.get(), 64))
            throw std::runtime_error("bind/listen failed");
        socket_length size = sizeof address;
        getsockname(listener_.get(), reinterpret_cast<sockaddr *>(&address), &size);
        for (unsigned i = 0; i < threads; ++i)
            workers_.emplace_back([this] { worker(); });
        std::cout << "PORT " << ntohs(address.sin_port) << std::endl;
    }
    ~Server() { stop(); }
    void stop() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            stopping_ = true;
            queue_.clear();
        }
        work_.notify_all();
        for (auto &thread : workers_)
            if (thread.joinable())
                thread.join();
        listener_.reset();
    }
    void run(unsigned duration_ms) {
        auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(duration_ms);
        while (std::chrono::steady_clock::now() < deadline) {
            fd_set set;
            FD_ZERO(&set);
            FD_SET(listener_.get(), &set);
            timeval timeout{0, 50000};
            if (select(static_cast<int>(listener_.get() + 1), &set, nullptr, nullptr, &timeout) <=
                0)
                continue;
            Socket client(accept(listener_.get(), nullptr, nullptr));
            if (!client)
                continue;
            {
                std::lock_guard<std::mutex> lock(mutex_);
                if (queue_.size() < 64)
                    queue_.push_back(std::move(client));
                else
                    ++rejected_;
            }
            work_.notify_one();
        }
        stop();
        std::cout << "accepted=" << accepted_ << " rejected=" << rejected_ << std::endl;
    }
};
int main(int argc, char **argv) {
    try {
        unsigned port = argc > 1 ? static_cast<unsigned>(std::stoul(argv[1])) : 0;
        unsigned duration = argc > 2 ? static_cast<unsigned>(std::stoul(argv[2])) : 10000;
        if (port > 65535 || duration < 100 || duration > 3600000)
            throw std::invalid_argument("port/duration out of range");
        SocketRuntime runtime;
        Server server(static_cast<uint16_t>(port), 4);
        server.run(duration);
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << std::endl;
        return 1;
    }
}
