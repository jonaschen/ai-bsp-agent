---
scope: kernel_pathologist
trigger: kernel panic, ESR_EL1, SError, Data Abort, Instruction Abort, cache coherency, oops
skill: decode_esr_el1, check_cache_coherency_panic
---

# AArch64 Exception Architecture & Kernel Panic Diagnosis

## Overview

AArch64 exceptions are classified by the **ESR_EL1** (Exception Syndrome Register,
Exception Level 1) register, which is printed by the Linux kernel in every panic/oops:

```
ESR_EL1 = 0x96000045
```

Reading ESR_EL1 is the first step in every kernel panic diagnosis. It tells you
**what kind of fault occurred** before you look at the program counter or call trace.

---

## ESR_EL1 Field Layout

```
 63      32 31    26 25 24                0
 ┌─────────┬────────┬──┬──────────────────┐
 │  ISS2   │   EC   │IL│       ISS        │
 │(AArch64)│ 6 bits │1b│    25 bits       │
 └─────────┴────────┴──┴──────────────────┘
```

| Field | Bits | Description |
|---|---|---|
| EC | [31:26] | Exception Class — identifies the fault type |
| IL | [25] | Instruction Length: 1 = 32-bit instruction, 0 = 16-bit |
| ISS | [24:0] | Instruction Specific Syndrome — fault details (EC-dependent) |

---

## Exception Class (EC) Quick Reference

| EC (hex) | Name | Common Cause |
|---|---|---|
| 0x00 | Unknown | Undefined instruction or firmware error |
| 0x15 | SVC (AArch64) | System call — not a fault |
| 0x20 | Instruction Abort (lower EL) | User-space instruction fetch from unmapped address |
| 0x21 | Instruction Abort (current EL) | Kernel instruction fetch from unmapped/corrupt address |
| 0x22 | PC alignment fault | PC not 4-byte aligned |
| 0x24 | Data Abort (lower EL) | User-space load/store to unmapped or protected address |
| 0x25 | Data Abort (current EL) | Kernel load/store to unmapped or protected address |
| 0x26 | SP alignment fault | Stack pointer misaligned |
| 0x2F | **SError Interrupt** | Hardware error — cache coherency, ECC, or bus fault |
| 0x3C | BRK instruction | Software breakpoint |

---

## Data Abort ISS Decoding (EC = 0x24 or 0x25)

For Data Aborts, the ISS field encodes the fault type:

```
 ISS bit [6]   = WnR   (1 = write fault, 0 = read fault)
 ISS bits [5:0] = DFSC (Data Fault Status Code)
```

### DFSC Quick Reference

| DFSC | Fault Type | Typical Cause |
|---|---|---|
| 0x04–0x07 | Translation fault, level 0–3 | NULL or unmapped pointer dereference |
| 0x09–0x0B | Access flag fault, level 1–3 | Page not marked accessed (unusual in Linux) |
| 0x0D–0x0F | Permission fault, level 1–3 | Write to read-only page, or kernel/user violation |
| 0x10 | Synchronous External abort | Bus error or hardware memory fault |
| 0x18 | Synchronous parity/ECC error | DRAM bit flip |
| 0x21 | Alignment fault | Unaligned memory access |
| 0x30 | TLB conflict abort | TLB shootdown race condition |

### Example: NULL Pointer Read

```
ESR_EL1 = 0x96000005
  EC  = 0x25  → Data Abort (current EL = kernel)
  IL  = 1     → 32-bit instruction
  ISS = 0x05
    WnR  = 0  → read access
    DFSC = 0x05 → Translation fault, level 1
```
Translation fault at level 1 means the page table entry at L1 was not present —
i.e., the virtual address translates to a region that is not mapped, which is the
signature of a NULL or zero-page dereference.

---

## SError Interrupt (EC = 0x2F)

SError (System Error) is an **asynchronous** exception raised by hardware when:
- A cache operation cannot complete (e.g., cannot flush to memory)
- A bus error is detected on an AXI/ACE transaction
- DRAM ECC detects an uncorrectable bit error
- A TrustZone violation is reported by EL3

### Linux Kernel Messages

```
SError Interrupt on CPU N
arm64: taking pending SError interrupt
Kernel panic - not syncing: Asynchronous SError Interrupt
```

### Cache Coherency Failures

The most common SError in Android BSP is a **PoC (Point of Coherency) synchronization
failure** during CPU suspend/resume:

1. CPU N is powered down without fully flushing its L1/L2 caches to the PoC (LLC or DRAM)
2. CPU 0 (or a DMA master) modifies the same memory
3. When CPU N resumes, it reads stale data from its cache
4. The resulting incoherence propagates as an SError or silent data corruption

**Key Linux kernel functions involved:**

| Function | File | Role |
|---|---|---|
| `__flush_dcache_area()` | `arch/arm64/mm/cache.S` | Flush D-cache range to PoC |
| `dcache_by_line_op()` | `arch/arm64/mm/cache.S` | Per-line cache maintenance |
| `cpu_do_suspend()` | `arch/arm64/mm/proc.S` | Save CPU state on suspend |
| `cpu_do_resume()` | `arch/arm64/mm/proc.S` | Restore CPU state on resume |

**Diagnostic checklist:**
1. Is `__flush_dcache_area()` called for all shared memory before CPU powerdown?
2. Is a `DSB SY` barrier issued after the flush and before `WFI`?
3. Does the vendor PSCI implementation correctly coordinate EL3 cache maintenance?
4. Are secondary CPUs brought up with a clean cache state?

---

## Kernel Panic Anatomy

A typical AArch64 kernel panic log contains:

```
Unable to handle kernel NULL pointer dereference at virtual address 0000000000000008
Mem abort info:
  ESR_EL1 = 0x96000005            ← decode this first
  EC = 0x25: DABT (current EL), IL = 32 bits
  SET = 0, FnV = 0
  EA = 0, S1PTW = 0
  FSC = 0x05: level 1 translation fault
Data abort info:
  ISV = 0, ISS = 0x00000005
  CM = 0, WnR = 0
[ffffffc012345678] pgd=0000000040000000, p4d=0000000040000000, pud=0000000000000000
Internal error: Oops: 96000005 [#1] PREEMPT SMP
CPU: 2 PID: 1234 Comm: kworker/u8:2
pc : my_driver_probe+0x3c/0x120 [my_driver]   ← faulting function
lr : platform_drv_probe+0x68/0xc0
Call trace:
 my_driver_probe+0x3c/0x120 [my_driver]
 platform_drv_probe+0x68/0xc0
 ...
```

**Diagnosis steps:**
1. Read `ESR_EL1` → use `decode_esr_el1` skill to classify
2. If `EC = 0x2F` → use `check_cache_coherency_panic` skill
3. Read `pc` → identify the faulting function and line
4. For Data Abort: read `Data abort info` → WnR (read/write) and DFSC (fault type)
5. Cross-reference with driver source at the `pc` offset

---

## References

- ARM Architecture Reference Manual for Armv8-A (DDI0487) — Chapter D17 (AArch64 System Registers)
- Linux kernel: `arch/arm64/kernel/traps.c` — `do_serror()`, `arm64_notify_die()`
- Linux kernel: `arch/arm64/kernel/entry.S` — exception vectors
- Linux kernel: `arch/arm64/mm/fault.c` — `do_mem_abort()`
- Android kernel: `arch/arm64/kernel/suspend.c` — CPU suspend/resume
