import os
import time

linux_logs = {
    "d0_linux_kernel_only.log": """[    0.000000] Booting Linux on physical CPU 0x0000000000 [0x410fd034]
[    0.000000] Linux version 5.15.0-generic (build@server) (gcc (Ubuntu 9.4.0-1ubuntu1~20.04.1) 9.4.0, GNU ld (GNU Binutils for Ubuntu) 2.34) #1 SMP Thu Jan 1 00:00:00 UTC 1970
[    0.000000] Machine model: Generic ARM64 Board
[    0.000000] earlycon: pl11 at MMIO 0x09000000 (options '')
[    0.000000] printk: bootconsole [pl11] enabled
[    1.234567] Freeing unused kernel image (initmem) memory: 1234K
[    1.345678] Run /init as init process
[    1.456789] Starting BusyBox
Welcome to Alpine Linux 3.19
""",
    "d2_qemu_null_pointer.log": """[   12.345678] BUG: kernel NULL pointer dereference, address: 0000000000000018
[   12.345679] #PF: supervisor read access in kernel mode
[   12.345680] #PF: error_code(0x0000) - not-present page
[   12.345681] PGD 0 P4D 0
[   12.345682] Oops: 0000 [#1] PREEMPT SMP NOPTI
[   12.345683] CPU: 0 PID: 123 Comm: kworker/0:1 Not tainted 5.15.0-generic #1
[   12.345684] Hardware name: QEMU Standard PC (i440FX + PIIX, 1996), BIOS 1.16.2-debian-1.16.2-1 04/01/2014
[   12.345685] RIP: 0010:foo_driver_probe+0x44/0x120
[   12.345686] Code: 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90
[   12.345687] RSP: 0018:ffffc90000123cd0 EFLAGS: 00010246
[   12.345688] RAX: 0000000000000000 RBX: ffff888012345600 RCX: 0000000000000000
[   12.345689] RDX: 0000000000000000 RSI: 0000000000000000 RDI: ffff888012345600
[   12.345690] RBP: ffffc90000123d00 R08: 0000000000000000 R09: 0000000000000000
[   12.345691] R10: 0000000000000000 R11: 0000000000000000 R12: ffff888012345600
[   12.345692] R13: 0000000000000000 R14: ffff888012345600 R15: 0000000000000000
[   12.345693] FS:  0000000000000000(0000) GS:ffff88803ec00000(0000) knlGS:0000000000000000
[   12.345694] CS:  0010 DS: 0000 ES: 0000 CR0: 0000000080050033
[   12.345695] CR2: 0000000000000018 CR3: 0000000012345000 CR4: 00000000000406f0
[   12.345696] Call Trace:
[   12.345697]  <TASK>
[   12.345698]  platform_drv_probe+0x54/0xb0
[   12.345699]  really_probe+0xc4/0x310
[   12.345700]  __driver_probe_device+0x7c/0x110
[   12.345701]  driver_probe_device+0x44/0x100
[   12.345702]  __device_attach_driver+0xb8/0x100
[   12.345703]  bus_for_each_drv+0x80/0xe0
[   12.345704]  __device_attach+0xe8/0x160
[   12.345705]  device_initial_probe+0x18/0x20
[   12.345706]  bus_probe_device+0x9c/0xa0
[   12.345707]  device_add+0x3b8/0x810
[   12.345708]  platform_device_add+0x114/0x240
[   12.345709]  platform_device_register_full+0x108/0x180
[   12.345710]  foo_init+0x34/0x1000 [foo_driver]
[   12.345711]  do_one_initcall+0x50/0x280
[   12.345712]  do_init_module+0x58/0x260
[   12.345713]  load_module+0x2128/0x2320
[   12.345714]  __do_sys_finit_module+0xa8/0x110
[   12.345715]  __x64_sys_finit_module+0x18/0x20
[   12.345716]  do_syscall_64+0x38/0xc0
[   12.345717]  entry_SYSCALL_64_after_hwframe+0x44/0xae
[   12.345718] RIP: 0033:0x7fb5bcde1234
[   12.345719] Code: 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90
[   12.345720] RSP: 002b:00007ffc1234bcde EFLAGS: 00000246 ORIG_RAX: 0000000000000139
[   12.345721] RAX: ffffffffffffffda RBX: 0000561234567890 RCX: 00007fb5bcde1234
[   12.345722] RDX: 0000000000000000 RSI: 0000561234567890 RDI: 0000000000000003
[   12.345723] RBP: 0000561234567890 R08: 0000000000000000 R09: 0000000000000000
[   12.345724] R10: 0000000000000003 R11: 0000000000000246 R12: 0000561234567890
[   12.345725] R13: 0000000000000000 R14: 0000000000000000 R15: 0000000000000000
[   12.345726]  </TASK>
""",
}

for filename, content in linux_logs.items():
    with open(f"logs/validation/{filename}", "w") as f:
        f.write(content)

print("Linux logs generated successfully.")
