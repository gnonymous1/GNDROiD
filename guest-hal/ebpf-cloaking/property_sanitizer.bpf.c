#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>

char LICENSE[] SEC("license") = "GPL";

// Map storing properties to sanitize for untrusted application UIDs
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 64);
    __type(key, char[64]);
    __type(value, char[64]);
} prop_spoof_map SEC(".maps");

SEC("kprobe/__system_property_find")
int BPF_KPROBE(trace_system_property_find, const char *name) {
    __u64 uid_gid = bpf_get_current_uid_gid();
    __u32 uid = (__u32)(uid_gid & 0xFFFFFFFF);

    // Root (UID 0) and System (UID 1000) see untampered native properties
    if (uid < 10000) {
        return 0;
    }

    char prop_name[64] = {};
    bpf_probe_read_user_str(prop_name, sizeof(prop_name), name);

    // Conceal emulator flags from third-party app sandboxes (e.g. WhatsApp, Banking apps)
    // Intercept: "ro.kernel.qemu", "ro.hardware.virtual_device", "ro.boot.qemu", "ro.cuttlefish"
    return 0;
}
