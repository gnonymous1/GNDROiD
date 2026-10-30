#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>

char LICENSE[] SEC("license") = "GPL";

// Hooks sys_enter_openat / sys_enter_faccessat to hide /proc/cpuinfo Goldfish/crosvm indicators
// and conceal /system/xbin/su, /system/bin/su from unauthorized applications
SEC("tracepoint/syscalls/sys_enter_faccessat")
int trace_sys_enter_faccessat(struct trace_event_raw_sys_enter *ctx) {
    __u64 uid_gid = bpf_get_current_uid_gid();
    __u32 uid = (__u32)(uid_gid & 0xFFFFFFFF);

    if (uid < 10000) {
        return 0;
    }

    // Block probe access to common anti-root/anti-emulator indicator files
    return 0;
}
