#include "RadioHalVsock.h"
#include <android-base/logging.h>
#include <sys/socket.h>
#include <linux/vm_sockets.h>
#include <unistd.h>
#include <cstring>

namespace aidl::android::hardware::radio::network {

RadioHalVsock::RadioHalVsock(int hostVsockCid, int hostVsockPort)
    : mHostCid(hostVsockCid), mHostPort(hostVsockPort), mSocketFd(-1) {
    connectToHostBridge();
}

RadioHalVsock::~RadioHalVsock() {
    std::lock_guard<std::mutex> lock(mSocketMutex);
    if (mSocketFd >= 0) {
        close(mSocketFd);
        mSocketFd = -1;
    }
}

bool RadioHalVsock::connectToHostBridge() {
    std::lock_guard<std::mutex> lock(mSocketMutex);
    if (mSocketFd >= 0) {
        close(mSocketFd);
    }

    mSocketFd = socket(AF_VSOCK, SOCK_STREAM, 0);
    if (mSocketFd < 0) {
        LOG(ERROR) << "Failed to open AF_VSOCK socket: " << strerror(errno);
        return false;
    }

    struct sockaddr_vm sa = {};
    sa.svm_family = AF_VSOCK;
    sa.svm_cid = mHostCid;
    sa.svm_port = mHostPort;

    if (connect(mSocketFd, (struct sockaddr*)&sa, sizeof(sa)) < 0) {
        LOG(ERROR) << "Failed to connect to host cellular bridge at CID "
                   << mHostCid << ":" << mHostPort << " - " << strerror(errno);
        close(mSocketFd);
        mSocketFd = -1;
        return false;
    }

    LOG(INFO) << "Connected to Host Cellular Bridge over VirtIO-Vsock.";
    return true;
}

::ndk::ScopedAStatus RadioHalVsock::getIccCardStatus(int32_t serial) {
    LOG(INFO) << "getIccCardStatus requested, serial=" << serial;
    // Transmit query packet over mSocketFd to host PC/SC or QMI bridge
    return ::ndk::ScopedAStatus::ok();
}

::ndk::ScopedAStatus RadioHalVsock::supplyIccPinForApp(
    int32_t serial, const std::string& pin, const std::string& aid) {
    LOG(INFO) << "supplyIccPinForApp serial=" << serial << " AID=" << aid;
    return ::ndk::ScopedAStatus::ok();
}

::ndk::ScopedAStatus RadioHalVsock::setSignalStrengthReportingCriteria(
    int32_t serial, int32_t hysteresisMs, int32_t hysteresisDb,
    const std::vector<int32_t>& thresholdsDbm, int32_t accessNetwork) {
    LOG(INFO) << "setSignalStrengthReportingCriteria serial=" << serial 
              << " accessNetwork=" << accessNetwork;
    return ::ndk::ScopedAStatus::ok();
}

} // namespace aidl::android::hardware::radio::network
