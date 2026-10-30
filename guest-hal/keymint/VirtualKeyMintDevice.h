#pragma once

#include <aidl/android/hardware/security/keymint/BnKeyMintDevice.h>
#include <aidl/android/hardware/security/keymint/SecurityLevel.h>
#include <string>
#include <vector>

namespace aidl::android::hardware::security::keymint {

class VirtualKeyMintDevice : public BnKeyMintDevice {
public:
    VirtualKeyMintDevice(SecurityLevel securityLevel);
    virtual ~VirtualKeyMintDevice() = default;

    ::ndk::ScopedAStatus getHardwareInfo(KeyMintHardwareInfo* _aidl_return) override;
    ::ndk::ScopedAStatus addRngEntropy(const std::vector<uint8_t>& data) override;
    ::ndk::ScopedAStatus generateKey(
        const std::vector<KeyParameter>& keyParams,
        const std::optional<AttestationKey>& attestationKey,
        KeyCreationResult* creationResult) override;

private:
    SecurityLevel mSecurityLevel;
    std::string mDeviceModel;
    std::string mDeviceFingerprint;
};

} // namespace aidl::android::hardware::security::keymint
