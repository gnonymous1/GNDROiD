#pragma once

#include <aidl/android/hardware/radio/network/BnRadioNetwork.h>
#include <aidl/android/hardware/radio/sim/BnRadioSim.h>
#include <string>
#include <vector>
#include <mutex>

namespace aidl::android::hardware::radio::network {

class RadioHalVsock : public BnRadioNetwork {
public:
    RadioHalVsock(int hostVsockCid, int hostVsockPort);
    virtual ~RadioHalVsock();

    bool connectToHostBridge();
    bool isConnected() const { return mSocketFd >= 0; }

    ::ndk::ScopedAStatus getIccCardStatus(int32_t serial);
    ::ndk::ScopedAStatus supplyIccPinForApp(int32_t serial, const std::string& pin, const std::string& aid);
    ::ndk::ScopedAStatus setSignalStrengthReportingCriteria(
        int32_t serial, int32_t hysteresisMs, int32_t hysteresisDb,
        const std::vector<int32_t>& thresholdsDbm, int32_t accessNetwork);

private:
    int mHostCid;
    int mHostPort;
    int mSocketFd;
    std::mutex mSocketMutex;
};

} // namespace aidl::android::hardware::radio::network
