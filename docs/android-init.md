---
scope: android_init_advisor
skills:
  - analyze_selinux_denial
  - check_android_init_rc
---

# Android Init Domain Reference

This document is the knowledge base for the `android_init_advisor` specialist.
It covers SELinux type enforcement and Android init.rc service lifecycle —
the two primary failure modes that trigger this route.

---

## 1. SELinux Type Enforcement (AVC Denials)

### 1.1 Log Format

SELinux denial messages appear as `type=1400 audit(...)` lines in both
dmesg and logcat:

**dmesg format:**
```
[  128.521504] type=1400 audit(1773227155.624:8): avc: denied { syslog_read }
    for comm="dmesg" scontext=u:r:shell:s0 tcontext=u:r:kernel:s0
    tclass=system permissive=0
```

**logcat format (via auditd):**
```
03-11 11:03:56.284   189   189 I auditd  : type=1400 audit(0.0:4):
    avc: denied { execute_no_trans } for comm="init"
    path="/vendor/bin/toybox_vendor" dev="dm-4" ino=222
    scontext=u:r:init:s0 tcontext=u:object_r:vendor_toolbox_exec:s0
    tclass=file permissive=0 bug=b/183668221
```

### 1.2 Key Fields

| Field | Meaning |
|---|---|
| `{ permission }` | The denied operation (e.g. `read`, `write`, `execute_no_trans`, `syslog_read`) |
| `comm="X"` | Process name (truncated to 15 chars by the kernel) |
| `scontext` | Subject (process) security context: `u:r:<domain>:<sensitivity>` |
| `tcontext` | Target (object) security context: `u:object_r:<type>:<sensitivity>` |
| `tclass` | Object class (e.g. `file`, `chr_file`, `system`, `netlink_socket`) |
| `permissive=0` | **Enforcing** — access was blocked |
| `permissive=1` | **Permissive** — access was logged but not blocked |

### 1.3 Common Denial Patterns

| Denial | scontext domain | tcontext type | tclass | Typical Cause |
|---|---|---|---|---|
| `syslog_read` | `shell` | `kernel` | `system` | ADB shell reading dmesg on a locked-down build |
| `execute_no_trans` | `init` | `vendor_toolbox_exec` | `file` | Init running vendor binary without domain transition |
| `read` | `untrusted_app` | `proc_net` | `file` | App reading `/proc/net/*` (privacy feature block) |
| `write` | `logd` | `kmsg_device` | `chr_file` | logd writing to `/dev/kmsg` — policy gap |

### 1.4 Remediation Workflow

1. **Identify enforcement vs. permissive.** Only `permissive=0` denials block
   real functionality. `permissive=1` lines are informational (SELinux running
   in permissive mode for that domain).

2. **Use `audit2allow` to draft a policy fix:**
   ```bash
   # From a dmesg capture on the device:
   adb shell dmesg | grep "avc: denied" | audit2allow -p out/target/product/<device>/root/sepolicy
   ```

3. **Locate the sepolicy source.** For AOSP-based devices:
   - System domains: `system/sepolicy/private/`, `system/sepolicy/public/`
   - Vendor domains: `device/<vendor>/<device>/sepolicy/`

4. **Add the missing `allow` rule** to the correct `.te` file and rebuild
   the sepolicy binary.

5. **If the denial looks intentional** (e.g., an untrusted app trying to access
   kernel memory), do not add a rule — investigate the calling code instead.

---

## 2. Android Init.rc Service Lifecycle

### 2.1 Key Init Log Patterns

**Service start:**
```
init: starting service 'zygote'...
```

**Explicit command failure:**
```
init: Command 'start zygote_secondary' action=ro.crypto.state=encrypted && \
    ro.crypto.type=file && zygote-start (/system/etc/init/hw/init.rc:1062) \
    took 0ms and failed: service zygote_secondary not found
```

**Property expansion failure:**
```
init: Command 'symlink /sys/fs/f2fs/${dev.mnt.dev.data} /dev/sys/fs/by-name/userdata' \
    action=boot (/system/etc/init/hw/init.rc:1092) took 0ms and failed: \
    property 'dev.mnt.dev.data' doesn't exist while expanding ...
```

**Service non-zero exit:**
```
init: Service 'vendor.camera-provider-2-4' (pid 500) exited with status 1
```

### 2.2 Command Failure Types

| Failure reason | Root cause | Fix |
|---|---|---|
| `service <name> not found` | Service declared in a vendor rc file not present in the build | Add the service definition to the appropriate `*.rc` file |
| `property 'X' doesn't exist` | Action trigger fires before the property is set | Reorder triggers or add a `wait_for_property` statement |
| `Could not open file ...` | File path doesn't exist on the target filesystem | Verify partition mounting order and file placement |
| `exec ... failed` (errno) | Binary missing or not executable | Check file system permissions and SELinux context |

### 2.3 Service Lifecycle States

| State | Init log line | Meaning |
|---|---|---|
| Starting | `init: starting service 'X'...` | Normal — init is forking the process |
| Running (one-shot) | `init: SVC_EXEC service 'X' ... started; waiting...` | One-shot exec service — init blocks until completion |
| Exited (clean) | `exited with status 0 waiting took N seconds` | Normal completion |
| Crashed | `exited with status N` (N ≠ 0) | Service crashed — check logcat for stderr |
| Restarting | `init: Sending signal 9 to service 'X'` | Init killed a stale PID group before restart |
| Disabled | `service 'X' requested start, but it is already running` | Service is persistent and already alive |

### 2.4 Common Boot Failures

**zygote_secondary not found:**
Seen on single-ABI builds where the init.rc references a secondary Zygote
(used for 32-bit app support). Not fatal if the device is 64-bit only.

**dev.mnt.dev.data property missing:**
The `f2fs` symlink action in `init.rc` fires before `vold` has mounted the
data partition and set `dev.mnt.dev.data`. Not fatal on AVD/QEMU but
indicates a race on real hardware. Fix: add `on property:dev.mnt.dev.data=*`
guard around the symlink commands.

**vendor HAL crash (exit status 1):**
Camera, DRM, audio HALs exiting with status 1 at boot typically indicate a
missing shared library, an incompatible HAL interface version, or a missing
hardware peripheral. Check logcat for the HAL's dlerror or hwbinder abort.

---

## 3. Triage Decision Tree

```
Android log detected (kernel timestamps + init/SELinux markers)
│
├── AVC denial lines present?
│   ├── Yes, permissive=0 → analyze_selinux_denial → check enforcing denials
│   └── Yes, permissive=1 only → informational; may still run check_android_init_rc
│
└── init.rc failure lines present?
    ├── "Command ... failed" → check_android_init_rc → review rc_file:rc_line
    └── "Service ... exited with status N" → check_android_init_rc → check logcat
```

---

## 4. Emulator Gaps (requires real hardware)

| Pattern | Gap | Affected skill |
|---|---|---|
| Product-specific init.rc service definitions | AVD init.rc differs from production devices | `check_android_init_rc` |
| Vendor-specific SELinux domains | AVD uses AOSP domains; vendor domains differ | `analyze_selinux_denial` |
| HAL crash due to missing hardware | AVD stubs all HALs successfully | `check_android_init_rc` |
| Qualcomm / MediaTek vendor init scripts | Not present in AOSP AVD | `check_android_init_rc` |

Use `validate_skill_extension` + `suggest_pattern_improvement` to extend
pattern coverage for real hardware init failures.
