import os
import json

synthetic_logs = {
    "d0_mixed_uart_kernel.log": """NOTICE:  BL1: v2.7(release):v2.7
NOTICE:  BL1: Booting BL2
NOTICE:  BL2: v2.7(release):v2.7
NOTICE:  BL2: Booting BL31
NOTICE:  BL31: v2.7(release):v2.7
[    0.000000] Booting Linux on physical CPU 0x0000000000 [0x410fd034]
[    0.000000] Linux version 5.15.0-generic (build@server) (gcc (Ubuntu 9.4.0-1ubuntu1~20.04.1) 9.4.0, GNU ld (GNU Binutils for Ubuntu) 2.34) #1 SMP Thu Jan 1 00:00:00 UTC 1970
[    0.000000] Machine model: Generic ARM64 Board
[    0.000000] earlycon: pl11 at MMIO 0x09000000 (options '')
[    0.000000] printk: bootconsole [pl11] enabled
""",
    "d0_unknown_fragment.log": """Rx Data: 0x45 0x12 0x99
Tx Data: 0x01
Status: OK
Wait for interrupt...
Interrupt received on pin 4.
Rx Data: 0x46 0x13 0x00
Tx Data: 0x02
Status: OK
""",
    "d1_tfa_auth_failure.log": """NOTICE:  BL1: v2.7(release):v2.7
NOTICE:  BL1: Booting BL2
NOTICE:  BL2: v2.7(release):v2.7
NOTICE:  BL2: Booting BL31
ERROR: BL2: Failed to load image id=5
ERROR: Authentication of BL31 image failed
""",
    "d1_uboot_ddr_init_fail.log": """U-Boot 2023.04 (Jan 01 1970 - 00:00:00 +0000)

CPU:   Generic ARM64
Model: Generic Board
DRAM:  ddr training fail
""",
    "d1_tfa_pmic_failure.log": """NOTICE:  BL1: v2.7(release):v2.7
NOTICE:  BL1: Booting BL2
NOTICE:  BL2: v2.7(release):v2.7
NOTICE:  BL2: Booting BL31
NOTICE:  BL31: v2.7(release):v2.7
ERROR: PMIC: regulator not ready
NOTICE: Failed to enable vdd_gpu rail
""",
    "d1_lk_assert_arm32.log": """Welcome to LK
ASSERT FAILED at kernel/thread.c:423
r0 = 0x00000000
r1 = 0x00000001
r2 = 0x00000002
r3 = 0x00000003
r4 = 0x00000004
r5 = 0x00000005
r6 = 0x00000006
r7 = 0x00000007
r8 = 0x00000008
r9 = 0x00000009
r10 = 0x0000000a
r11 = 0x0000000b
r12 = 0x0000000c
r13 = 0x0000000d
r14 = 0x0000000e
r15 = 0x0000000f
""",
    "d1_uboot_panic_aarch64.log": """U-Boot 2023.04 (Jan 01 1970 - 00:00:00 +0000)

CPU:   Generic ARM64
Model: Generic Board
data abort
x0: 0000000000000000 x1: 0000000000000001
x2: 0000000000000002 x3: 0000000000000003
x4: 0000000000000004 x5: 0000000000000005
x6: 0000000000000006 x7: 0000000000000007
x8: 0000000000000008 x9: 0000000000000009
x10: 000000000000000a x11: 000000000000000b
x12: 000000000000000c x13: 000000000000000d
x14: 000000000000000e x15: 000000000000000f
x16: 0000000000000010 x17: 0000000000000011
x18: 0000000000000012 x19: 0000000000000013
x20: 0000000000000014 x21: 0000000000000015
x22: 0000000000000016 x23: 0000000000000017
x24: 0000000000000018 x25: 0000000000000019
x26: 000000000000001a x27: 000000000000001b
x28: 000000000000001c x29: 000000000000001d
x30: 000000000000001e
ELR: 0000000000000123
ESR_EL2: 00000000
resetting ...
""",
    "d2_aarch64_null_ptr.log": """[   12.345678] Unable to handle kernel NULL pointer dereference at virtual address 0000000000000018
[   12.345680] Mem abort info:
[   12.345681]   ESR = 0x96000006
[   12.345682]   EC = 0x25: DABT (current EL), IL = 32 bits
[   12.345683]   SET = 0, FnV = 0
[   12.345684]   EA = 0, S1PTW = 0
[   12.345685] Data abort info:
[   12.345686]   ISV = 0, ISS = 0x00000006
[   12.345687]   CM = 0, WnR = 0
[   12.345688] user pgtable: 4k pages, 48-bit VAs, pgdp=00000001014e3000
[   12.345689] [0000000000000018] pgd=0000000000000000, p4d=0000000000000000
[   12.345690] Internal error: Oops: 96000006 [#1] PREEMPT SMP
[   12.345691] Modules linked in: foo_driver
[   12.345692] CPU: 0 PID: 123 Comm: kworker/0:1 Not tainted 5.15.0-generic #1
[   12.345693] Hardware name: Generic ARM64 Board (DT)
[   12.345694] pstate: 80400005 (Nzcv daif +PAN -UAO -TCO -DIT -SSBS BTYPE=--)
[   12.345695] pc : foo_driver_probe+0x44/0x120 [foo_driver]
[   12.345696] lr : platform_drv_probe+0x54/0xb0
[   12.345697] sp : ffff80001234bcde
[   12.345698] x29: ffff80001234bcde x28: ffff000012345678 x27: ffff800012345678
[   12.345699] x26: ffff000012345678 x25: 0000000000000000 x24: ffff000012345678
[   12.345700] x23: 0000000000000000 x22: ffff000012345678 x21: ffff800012345678
[   12.345701] x20: ffff000012345678 x19: ffff000012345678 x18: 0000000000000000
[   12.345702] x17: 0000000000000000 x16: 0000000000000000 x15: 0000000000000000
[   12.345703] x14: 0000000000000000 x13: 0000000000000000 x12: 0000000000000000
[   12.345704] x11: 0000000000000000 x10: 0000000000000000 x9 : ffff800012345678
[   12.345705] x8 : 0000000000000000 x7 : 0000000000000000 x6 : 0000000000000000
[   12.345706] x5 : 0000000000000000 x4 : 0000000000000000 x3 : 0000000000000000
[   12.345707] x2 : 0000000000000000 x1 : 0000000000000000 x0 : 0000000000000000
[   12.345708] Call trace:
[   12.345709]  foo_driver_probe+0x44/0x120 [foo_driver]
[   12.345710]  platform_drv_probe+0x54/0xb0
[   12.345711]  really_probe+0xc4/0x310
[   12.345712]  __driver_probe_device+0x7c/0x110
[   12.345713]  driver_probe_device+0x44/0x100
[   12.345714]  __device_attach_driver+0xb8/0x100
[   12.345715]  bus_for_each_drv+0x80/0xe0
[   12.345716]  __device_attach+0xe8/0x160
[   12.345717]  device_initial_probe+0x18/0x20
[   12.345718]  bus_probe_device+0x9c/0xa0
[   12.345719]  device_add+0x3b8/0x810
[   12.345720]  platform_device_add+0x114/0x240
[   12.345721]  platform_device_register_full+0x108/0x180
[   12.345722]  foo_init+0x34/0x1000 [foo_driver]
[   12.345723]  do_one_initcall+0x50/0x280
[   12.345724]  do_init_module+0x58/0x260
[   12.345725]  load_module+0x2128/0x2320
[   12.345726]  __do_sys_finit_module+0xa8/0x110
[   12.345727]  __arm64_sys_finit_module+0x24/0x30
[   12.345728]  invoke_syscall+0x48/0x110
[   12.345729]  el0_svc_common.constprop.0+0x48/0xf0
[   12.345730]  do_el0_svc+0x28/0x80
[   12.345731]  el0_svc+0x18/0x50
[   12.345732]  el0t_64_sync_handler+0xa4/0x130
[   12.345733]  el0t_64_sync+0x1a0/0x1a4
""",
    "d2_aarch64_paging_request.log": """[   12.345678] Unable to handle kernel paging request at virtual address ffff800012345678
[   12.345680] Mem abort info:
[   12.345681]   ESR = 0x9600004f
[   12.345682]   EC = 0x25: DABT (current EL), IL = 32 bits
[   12.345683]   SET = 0, FnV = 0
[   12.345684]   EA = 0, S1PTW = 0
[   12.345685] Data abort info:
[   12.345686]   ISV = 0, ISS = 0x0000004f
[   12.345687]   CM = 0, WnR = 0
[   12.345688] swapper pgtable: 4k pages, 48-bit VAs, pgdp=00000000014e3000
[   12.345689] [ffff800012345678] pgd=0000000000000000, p4d=0000000000000000
[   12.345690] Internal error: Oops: 9600004f [#1] PREEMPT SMP
[   12.345691] Modules linked in: foo_driver
[   12.345692] CPU: 0 PID: 123 Comm: kworker/0:1 Not tainted 5.15.0-generic #1
[   12.345693] Hardware name: Generic ARM64 Board (DT)
[   12.345694] pstate: 80400005 (Nzcv daif +PAN -UAO -TCO -DIT -SSBS BTYPE=--)
[   12.345695] pc : foo_driver_read+0x44/0x120 [foo_driver]
[   12.345696] lr : vfs_read+0x54/0xb0
[   12.345697] sp : ffff80001234bcde
[   12.345698] x29: ffff80001234bcde x28: ffff000012345678 x27: ffff800012345678
[   12.345699] x26: ffff000012345678 x25: 0000000000000000 x24: ffff000012345678
[   12.345700] x23: 0000000000000000 x22: ffff000012345678 x21: ffff800012345678
[   12.345701] x20: ffff000012345678 x19: ffff000012345678 x18: 0000000000000000
[   12.345702] x17: 0000000000000000 x16: 0000000000000000 x15: 0000000000000000
[   12.345703] x14: 0000000000000000 x13: 0000000000000000 x12: 0000000000000000
[   12.345704] x11: 0000000000000000 x10: 0000000000000000 x9 : ffff800012345678
[   12.345705] x8 : ffff800012345678 x7 : 0000000000000000 x6 : 0000000000000000
[   12.345706] x5 : 0000000000000000 x4 : 0000000000000000 x3 : 0000000000000000
[   12.345707] x2 : 0000000000000000 x1 : 0000000000000000 x0 : 0000000000000000
[   12.345708] Call trace:
[   12.345709]  foo_driver_read+0x44/0x120 [foo_driver]
[   12.345710]  vfs_read+0x54/0xb0
[   12.345711]  ksys_read+0x64/0xd0
[   12.345712]  __arm64_sys_read+0x18/0x20
[   12.345713]  invoke_syscall+0x48/0x110
[   12.345714]  el0_svc_common.constprop.0+0x48/0xf0
[   12.345715]  do_el0_svc+0x28/0x80
[   12.345716]  el0_svc+0x18/0x50
[   12.345717]  el0t_64_sync_handler+0xa4/0x130
[   12.345718]  el0t_64_sync+0x1a0/0x1a4
""",
    "d2_serror_interrupt.log": """[   12.345678] Internal error: SError Interrupt: 96000210 [#1] PREEMPT SMP
[   12.345679] Modules linked in:
[   12.345680] CPU: 1 PID: 123 Comm: kworker/1:1 Not tainted 5.15.0-generic #1
[   12.345681] Hardware name: Generic ARM64 Board (DT)
[   12.345682] pstate: 80400005 (Nzcv daif +PAN -UAO -TCO -DIT -SSBS BTYPE=--)
[   12.345683] pc : cpu_resume+0x44/0x120
[   12.345684] lr : suspend_finish+0x54/0xb0
[   12.345685] sp : ffff80001234bcde
[   12.345686] x29: ffff80001234bcde x28: ffff000012345678 x27: ffff800012345678
[   12.345687] x26: ffff000012345678 x25: 0000000000000000 x24: ffff000012345678
[   12.345688] x23: 0000000000000000 x22: ffff000012345678 x21: ffff800012345678
[   12.345689] x20: ffff000012345678 x19: ffff000012345678 x18: 0000000000000000
[   12.345690] x17: 0000000000000000 x16: 0000000000000000 x15: 0000000000000000
[   12.345691] x14: 0000000000000000 x13: 0000000000000000 x12: 0000000000000000
[   12.345692] x11: 0000000000000000 x10: 0000000000000000 x9 : ffff800012345678
[   12.345693] x8 : 0000000000000000 x7 : 0000000000000000 x6 : 0000000000000000
[   12.345694] x5 : 0000000000000000 x4 : 0000000000000000 x3 : 0000000000000000
[   12.345695] x2 : 0000000000000000 x1 : 0000000000000000 x0 : 0000000000000000
[   12.345696] Call trace:
[   12.345697]  cpu_resume+0x44/0x120
[   12.345698]  suspend_finish+0x54/0xb0
[   12.345699]  suspend_devices_and_enter+0x184/0x3a0
[   12.345700]  pm_suspend+0x194/0x360
[   12.345701]  state_store+0x80/0x100
[   12.345702]  kobj_attr_store+0x14/0x20
[   12.345703]  sysfs_kf_write+0x3c/0x50
[   12.345704]  kernfs_fop_write_iter+0x11c/0x1b0
[   12.345705]  vfs_write+0x2ec/0x3c0
[   12.345706]  ksys_write+0x64/0xf0
[   12.345707]  __arm64_sys_write+0x18/0x20
[   12.345708]  invoke_syscall+0x48/0x110
[   12.345709]  el0_svc_common.constprop.0+0x48/0xf0
[   12.345710]  do_el0_svc+0x28/0x80
[   12.345711]  el0_svc+0x18/0x50
[   12.345712]  el0t_64_sync_handler+0xa4/0x130
[   12.345713]  el0t_64_sync+0x1a0/0x1a4
""",
    "d2_soft_lockup.log": """[   25.432100] watchdog: BUG: soft lockup - CPU#0 stuck for 22s! [kworker/0:1:123]
[   25.432101] Modules linked in:
[   25.432102] CPU: 0 PID: 123 Comm: kworker/0:1 Not tainted 5.15.0-generic #1
[   25.432103] Hardware name: Generic ARM64 Board (DT)
[   25.432104] pstate: 80400005 (Nzcv daif +PAN -UAO -TCO -DIT -SSBS BTYPE=--)
[   25.432105] pc : delay_tsc+0x34/0x60
[   25.432106] lr : delay_tsc+0x30/0x60
[   25.432107] sp : ffff80001234bcde
[   25.432108] Call trace:
[   25.432109]  delay_tsc+0x34/0x60
[   25.432110]  __const_udelay+0x34/0x40
[   25.432111]  foo_driver_wait+0x44/0x120
[   25.432112]  foo_driver_work+0x54/0xb0
[   25.432113]  process_one_work+0x1c4/0x380
[   25.432114]  worker_thread+0x1cc/0x3a0
[   25.432115]  kthread+0x130/0x140
[   25.432116]  ret_from_fork+0x10/0x20
""",
    "d2_hard_lockup.log": """[   60.123456] Watchdog detected hard LOCKUP on cpu 3
[   60.123457] Modules linked in:
[   60.123458] CPU: 3 PID: 987 Comm: irq/45-audio Not tainted 5.15.0-generic #1
[   60.123459] Hardware name: Generic ARM64 Board (DT)
[   60.123460] pstate: 80400005 (Nzcv daif +PAN -UAO -TCO -DIT -SSBS BTYPE=--)
[   60.123461] pc : delay_tsc+0x34/0x60
[   60.123462] lr : delay_tsc+0x30/0x60
[   60.123463] sp : ffff80001234bcde
[   60.123464] Call trace:
[   60.123465]  delay_tsc+0x34/0x60
[   60.123466]  __const_udelay+0x34/0x40
[   60.123467]  audio_irq_handler+0x44/0x120
[   60.123468]  __handle_irq_event_percpu+0x54/0xb0
[   60.123469]  handle_irq_event+0x34/0x80
[   60.123470]  handle_fasteoi_irq+0x94/0x180
[   60.123471]  __handle_domain_irq+0x74/0xd0
[   60.123472]  gic_handle_irq+0x54/0xa0
[   60.123473]  el1_irq+0xbc/0x140
[   60.123474]  cpuidle_enter_state+0x13c/0x2f0
[   60.123475]  cpuidle_enter+0x34/0x50
[   60.123476]  do_idle+0x21c/0x2a0
[   60.123477]  cpu_startup_entry+0x24/0x30
[   60.123478]  secondary_start_kernel+0x138/0x150
""",
    "d2_rcu_stall.log": """[  120.456789] rcu: INFO: rcu_sched detected stalls on CPUs/tasks:
[  120.456790] rcu:     2-...!: (1 ticks this GP) idle=001/1/0x4000000000000000 softirq=123/123 fqs=0
[  120.456791] rcu:     (detected by 0, t=5252 jiffies, g=123, q=456)
[  120.456792] Task dump for CPU 2:
[  120.456793] task:kworker/2:1     state:R  running task     stack:    0 pid: 456 ppid:     2 flags:0x00000008
[  120.456794] Call trace:
[  120.456795]  __switch_to+0xc4/0x140
[  120.456796]  foo_driver_work+0x54/0xb0
[  120.456797]  process_one_work+0x1c4/0x380
[  120.456798]  worker_thread+0x1cc/0x3a0
[  120.456799]  kthread+0x130/0x140
[  120.456800]  ret_from_fork+0x10/0x20
""",
    "d2_watchdog_serror_combined.log": """[   52.432100] watchdog: BUG: soft lockup - CPU#2 stuck for 22s! [kworker/2:1:456]
[   52.432101] Modules linked in:
[   52.432102] CPU: 2 PID: 456 Comm: kworker/2:1 Not tainted 5.15.0-generic #1
[   52.432103] Hardware name: Generic ARM64 Board (DT)
[   52.432104] pstate: 80400005 (Nzcv daif +PAN -UAO -TCO -DIT -SSBS BTYPE=--)
[   52.432105] pc : delay_tsc+0x34/0x60
[   52.432106] lr : delay_tsc+0x30/0x60
[   52.432107] sp : ffff80001234bcde
[   52.432108] Call trace:
[   52.432109]  delay_tsc+0x34/0x60
[   52.432110]  __const_udelay+0x34/0x40
[   52.432111]  foo_driver_wait+0x44/0x120
[   52.432112]  foo_driver_work+0x54/0xb0
[   52.432113]  process_one_work+0x1c4/0x380
[   52.432114]  worker_thread+0x1cc/0x3a0
[   52.432115]  kthread+0x130/0x140
[   52.432116]  ret_from_fork+0x10/0x20
[   54.123456] Internal error: SError Interrupt: 96000210 [#1] PREEMPT SMP
[   54.123457] Modules linked in:
[   54.123458] CPU: 2 PID: 456 Comm: kworker/2:1 Not tainted 5.15.0-generic #1
[   54.123459] Hardware name: Generic ARM64 Board (DT)
[   54.123460] pstate: 80400005 (Nzcv daif +PAN -UAO -TCO -DIT -SSBS BTYPE=--)
[   54.123461] pc : foo_driver_work+0x44/0x120
[   54.123462] lr : process_one_work+0x54/0xb0
[   54.123463] sp : ffff80001234bcde
[   54.123464] x29: ffff80001234bcde x28: ffff000012345678 x27: ffff800012345678
[   54.123465] x26: ffff000012345678 x25: 0000000000000000 x24: ffff000012345678
[   54.123466] x23: 0000000000000000 x22: ffff000012345678 x21: ffff800012345678
[   54.123467] x20: ffff000012345678 x19: ffff000012345678 x18: 0000000000000000
[   54.123468] x17: 0000000000000000 x16: 0000000000000000 x15: 0000000000000000
[   54.123469] x14: 0000000000000000 x13: 0000000000000000 x12: 0000000000000000
[   54.123470] x11: 0000000000000000 x10: 0000000000000000 x9 : ffff800012345678
[   54.123471] x8 : 0000000000000000 x7 : 0000000000000000 x6 : 0000000000000000
[   54.123472] x5 : 0000000000000000 x4 : 0000000000000000 x3 : 0000000000000000
[   54.123473] x2 : 0000000000000000 x1 : 0000000000000000 x0 : 0000000000000000
[   54.123474] Call trace:
[   54.123475]  foo_driver_work+0x44/0x120
[   54.123476]  process_one_work+0x54/0xb0
[   54.123477]  worker_thread+0x1cc/0x3a0
[   54.123478]  kthread+0x130/0x140
[   54.123479]  ret_from_fork+0x10/0x20
""",
    "d3_std_swap_exhausted.log": """[  360.123456] PM: hibernation entry
[  360.234567] PM: Syncing filesystems ... done.
[  360.345678] Freezing user space processes ... (elapsed 0.001 seconds) done.
[  360.456789] OOM killer disabled.
[  360.567890] Freezing remaining freezable tasks ... (elapsed 0.001 seconds) done.
[  360.678901] PM: Error -12 creating hibernation image
[  360.789012] OOM killer enabled.
[  360.890123] Restarting tasks ... done.
[  361.001234] PM: hibernation exit
""",
    "d3_ufs_probe_fail.log": """[    1.234567] ufshcd-qcom 1d84000.ufshc: ufs_qcom_probe()
[    1.345678] ufshcd-qcom 1d84000.ufshc: ufshcd_probe_hba()
[    4.456789] ufshcd-qcom 1d84000.ufshc: ufshcd_probe_hba: probe of 1d84000.ufshc failed with error -110
[    4.567890] ufshcd-qcom: probe of 1d84000.ufshc failed with error -110
""",
    "d3_ufs_link_startup_fail.log": """[  360.123456] PM: hibernation exit
[  360.234567] ufshcd-qcom 1d84000.ufshc: ufshcd_resume()
[  365.345678] ufshcd-qcom 1d84000.ufshc: ufshcd_link_startup: link startup failed -5
[  365.456789] ufshcd-qcom 1d84000.ufshc: ufshcd_resume failed: -5
[  365.567890] PM: dpm_run_callback(): ufshcd_resume+0x0/0x100 [ufshcd_core] returns -5
[  365.678901] PM: Device 1d84000.ufshc failed to resume async: error -5
""",
    "d3_pmic_ocp_display.log": """[   12.345678] qpnp-regulator: qpnp_regulator_enable: vreg_lcd_vsp: over-current fault
[   12.345679] display-driver: Failed to enable vreg_lcd_vsp, retrying...
[   13.345678] qpnp-regulator: qpnp_regulator_enable: vreg_lcd_vsp: over-current fault
""",
    "d3_pmic_undervoltage_cpu.log": """[    1.234567] rpm_smd_regulator: s1a: Requested voltage 756000 uV is below minimum 800000 uV
[    1.234568] cpufreq: Failed to set voltage for CPU0
""",
    "d4_ambiguous_ufs_kernel.log": """[    1.234567] ufshcd-qcom 1d84000.ufshc: ufs_qcom_probe()
[    1.345678] ufshcd-qcom 1d84000.ufshc: ufshcd_probe_hba()
[    4.456789] ufshcd-qcom 1d84000.ufshc: ufshcd_probe_hba: probe of 1d84000.ufshc failed with error -110
[    4.567890] ufshcd-qcom: probe of 1d84000.ufshc failed with error -110
[   26.432100] watchdog: BUG: soft lockup - CPU#0 stuck for 22s! [kworker/0:1:123]
[   26.432101] Modules linked in:
[   26.432102] CPU: 0 PID: 123 Comm: kworker/0:1 Not tainted 5.15.0-generic #1
[   26.432103] Hardware name: Generic ARM64 Board (DT)
[   26.432104] pstate: 80400005 (Nzcv daif +PAN -UAO -TCO -DIT -SSBS BTYPE=--)
[   26.432105] pc : delay_tsc+0x34/0x60
[   26.432106] lr : delay_tsc+0x30/0x60
[   26.432107] sp : ffff80001234bcde
[   26.432108] Call trace:
[   26.432109]  delay_tsc+0x34/0x60
[   26.432110]  __const_udelay+0x34/0x40
[   26.432111]  ufshcd_wait+0x44/0x120
[   26.432112]  ufshcd_work+0x54/0xb0
[   26.432113]  process_one_work+0x1c4/0x380
[   26.432114]  worker_thread+0x1cc/0x3a0
[   26.432115]  kthread+0x130/0x140
[   26.432116]  ret_from_fork+0x10/0x20
""",
    "d4_early_boot_healthy.log": """NOTICE:  BL1: v2.7(release):v2.7
NOTICE:  BL1: Booting BL2
NOTICE:  BL2: v2.7(release):v2.7
NOTICE:  BL2: Booting BL31
NOTICE:  BL31: v2.7(release):v2.7
NOTICE:  BL31: Booting BL33
U-Boot 2023.04 (Jan 01 1970 - 00:00:00 +0000)

CPU:   Generic ARM64
Model: Generic Board
DRAM:  2 GiB
Hit any key to stop autoboot:  0
"""
}

for filename, content in synthetic_logs.items():
    with open(f"logs/validation/{filename}", "w") as f:
        f.write(content)

# We also need a meminfo file for d3_std_swap_exhausted.log
with open("logs/validation/d3_std_swap_exhausted.meminfo", "w") as f:
    f.write("""MemTotal:        2048000 kB
MemFree:           10240 kB
MemAvailable:      51200 kB
Buffers:            1024 kB
Cached:            40960 kB
SwapCached:            0 kB
Active:          1500000 kB
Inactive:         400000 kB
Active(anon):    1000000 kB
Inactive(anon):   300000 kB
Active(file):     500000 kB
Inactive(file):   100000 kB
Unevictable:           0 kB
Mlocked:               0 kB
SwapTotal:       1024000 kB
SwapFree:              0 kB
Dirty:                 0 kB
Writeback:             0 kB
AnonPages:       1300000 kB
Mapped:           400000 kB
Shmem:             10000 kB
Slab:              50000 kB
SReclaimable:      20000 kB
SUnreclaim:        30000 kB
KernelStack:       10000 kB
PageTables:        20000 kB
NFS_Unstable:          0 kB
Bounce:                0 kB
WritebackTmp:          0 kB
CommitLimit:     2048000 kB
Committed_AS:    3000000 kB
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

print("Synthetic logs generated successfully.")
