import os
import time

android_logs = {
    "d0_android_normal_boot.log": """================================================================
  Android Boot Log — Scenario: normal
  Generated: 2024-03-11 10:20:00
================================================================

-------- KERNEL DMESG --------
[    0.000000] Booting Linux on physical CPU 0x0000000000 [0x410fd034]
[    0.000000] Linux version 5.15.0-generic (build@server) (gcc (Ubuntu 9.4.0-1ubuntu1~20.04.1) 9.4.0, GNU ld (GNU Binutils for Ubuntu) 2.34) #1 SMP Thu Jan 1 00:00:00 UTC 1970
[    0.000000] Machine model: Generic ARM64 Board
[    1.234567] init: init first stage started!
[    2.345678] init: init second stage started!
[    4.567890] android.hardware.health@2.0-service: starting...

-------- LOGCAT (ALL BUFFERS) --------
10-01 12:00:00.000   123   123 I Zygote  : System server process 456 has been created
10-01 12:00:01.000   456   456 I SystemServiceManager: Starting com.android.server.am.ActivityManagerService
10-01 12:00:10.000   456   456 I ActivityManager: ActivityManagerService ready
10-01 12:00:20.000   456   456 I SystemServer: sys.boot_completed=1

-------- BOOT EVENTS --------
10-01 12:00:01.000   456   456 I boot_progress_start: 12000
10-01 12:00:10.000   456   456 I boot_progress_ams_ready: 21000

-------- SELINUX / AVC --------

-------- LAST KMSG (PREVIOUS BOOT) --------
""",
    "d3_std_high_sunreclaim.log": """================================================================
  Android Boot Log — Scenario: slow
  Generated: 2024-03-11 10:20:00
================================================================

-------- KERNEL DMESG --------
[  360.123456] PM: hibernation entry
[  360.234567] PM: Syncing filesystems ... done.
[  360.345678] Freezing user space processes ... (elapsed 0.001 seconds) done.
[  360.456789] OOM killer disabled.
[  360.567890] Freezing remaining freezable tasks ... (elapsed 0.001 seconds) done.
[  360.678901] PM: Error -12 creating hibernation image
[  360.789012] OOM killer enabled.
[  360.890123] Restarting tasks ... done.
[  361.001234] PM: hibernation exit
""",
    "d3_pmic_clean_boot.log": """================================================================
  Android Boot Log — Scenario: normal
  Generated: 2024-03-11 10:20:00
================================================================

-------- KERNEL DMESG --------
[    1.234567] qpnp-regulator: qpnp_regulator_enable: vreg_lcd_vsp: enabled
[    1.345678] qpnp-regulator: qpnp_regulator_enable: vreg_lvs1a: enabled
[    1.456789] rpm_smd_regulator: s1a: enabled
""",
    "d4_android_selinux_avc.log": """================================================================
  Android Boot Log — Scenario: selinux
  Generated: 2024-03-11 10:20:00
================================================================

-------- KERNEL DMESG --------
[    0.000000] Booting Linux on physical CPU 0x0000000000 [0x410fd034]
[    1.234567] init: init first stage started!
[    8.234567] audit: type=1400 audit(1234567890.123:45): avc: denied { read } for pid=1234 comm="zygote" name="maps" dev="proc"
[    9.345678] audit: type=1400 audit(1234567890.234:46): avc: denied { open } for pid=1234 comm="zygote" name="maps" dev="proc"
[   10.456789] audit: type=1400 audit(1234567890.345:47): avc: denied { getattr } for pid=1234 comm="zygote" name="maps" dev="proc"

-------- LOGCAT (ALL BUFFERS) --------
10-01 12:00:00.000  1234  1234 I Zygote  : System server process 456 has been created

-------- BOOT EVENTS --------

-------- SELINUX / AVC --------
[    8.234567] audit: type=1400 audit(1234567890.123:45): avc: denied { read } for pid=1234 comm="zygote" name="maps" dev="proc"
[    9.345678] audit: type=1400 audit(1234567890.234:46): avc: denied { open } for pid=1234 comm="zygote" name="maps" dev="proc"
[   10.456789] audit: type=1400 audit(1234567890.345:47): avc: denied { getattr } for pid=1234 comm="zygote" name="maps" dev="proc"
""",
    "d4_android_slow_boot.log": """================================================================
  Android Boot Log — Scenario: slow
  Generated: 2024-03-11 10:20:00
================================================================

-------- KERNEL DMESG --------
[    0.000000] Booting Linux on physical CPU 0x0000000000 [0x410fd034]
[    1.234567] init: init first stage started!
[   12.543210] mmc0: Timeout waiting for hardware interrupt.
[   12.643210] mmc0: Got data interrupt 0x00000002 even though no data operation was in progress.
[   25.456789] platform regulatory.0: Direct firmware load for regulatory.db failed with error -2
[   25.456790] cfg80211: failed to load regulatory.db

-------- LOGCAT (ALL BUFFERS) --------
10-01 12:00:00.000   123   123 I Zygote  : System server process 456 has been created
10-01 12:02:10.000   456   456 I SystemServer: sys.boot_completed=1

-------- BOOT EVENTS --------
10-01 12:00:01.000   456   456 I boot_progress_start: 12000
10-01 12:02:00.000   456   456 I boot_progress_ams_ready: 131000

-------- SELINUX / AVC --------
""",
}

for filename, content in android_logs.items():
    with open(f"logs/validation/{filename}", "w") as f:
        f.write(content)

# meminfo file for d3_std_high_sunreclaim.log
with open("logs/validation/d3_std_high_sunreclaim.meminfo", "w") as f:
    f.write("""MemTotal:        1024000 kB
MemFree:           10240 kB
MemAvailable:      51200 kB
Buffers:            1024 kB
Cached:            40960 kB
SwapCached:            0 kB
Active:           150000 kB
Inactive:          40000 kB
Active(anon):     100000 kB
Inactive(anon):    30000 kB
Active(file):      50000 kB
Inactive(file):    10000 kB
Unevictable:           0 kB
Mlocked:               0 kB
SwapTotal:       1024000 kB
SwapFree:        1000000 kB
Dirty:                 0 kB
Writeback:             0 kB
AnonPages:        130000 kB
Mapped:            40000 kB
Shmem:             10000 kB
Slab:             200000 kB
SReclaimable:      20000 kB
SUnreclaim:       180000 kB
KernelStack:       10000 kB
PageTables:        20000 kB
NFS_Unstable:          0 kB
Bounce:                0 kB
WritebackTmp:          0 kB
CommitLimit:     2048000 kB
Committed_AS:     300000 kB
VmallocTotal:   34359738367 kB
VmallocUsed:           0 kB
VmallocChunk:          0 kB
Percpu:             1000 kB
HardwareCorrupted:     0 kB
AnonHugePages:         0 kB
ShmemHugePages:        0 kB
ShmemPmdMapped:        0 kB
CmaTotal:              0 kB
CmaFree:               0 kB
HugePages_Total:       0
HugePages_Free:        0
HugePages_Rsvd:        0
HugePages_Surp:        0
Hugepagesize:       2048 kB
Hugetlb:               0 kB
""")

print("Android logs generated successfully.")
