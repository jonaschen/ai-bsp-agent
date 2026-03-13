---
scope: source_analyst
skills:
  - resolve_oops_symbols
  - compare_device_tree_nodes
  - diff_kernel_configs
  - validate_gpio_pinctrl_conflict
---

# Workspace Analysis Reference

This document is the knowledge base for Phase 8 workspace diagnostic skills.
It covers symbol resolution, DTS diffing, kernel config comparison, and GPIO
conflict detection — all operating on workspace artifacts rather than live logs.

---

## 1. Symbol Resolution (`resolve_oops_symbols`)

### 1.1 addr2line Workflow

`resolve_oops_symbols` calls:

```bash
addr2line -e <vmlinux> -f -C <addr1> <addr2> ...
```

Output is two lines per address:
1. Demangled function name (or `??` if unresolvable)
2. Source file path and line number (or `??:0`)

### 1.2 Prerequisites

| Requirement | Detail |
|---|---|
| `CONFIG_DEBUG_INFO=y` | vmlinux must be built with DWARF debug info |
| Build match | vmlinux must be from the **exact same build** as the crashing kernel |
| addr2line installed | Usually in `binutils` or `gcc-aarch64-linux-gnu` |

### 1.3 Common Failure Causes

| Symptom | Cause | Fix |
|---|---|---|
| All addresses `??` | vmlinux has no debug symbols | Rebuild with `CONFIG_DEBUG_INFO=y` |
| Some addresses `??` | Address is in a `.ko` module | Pass the `.ko` path as vmlinux |
| Wrong function names | vmlinux/kernel mismatch | Match by build ID: `file vmlinux \| grep BuildID` |
| KASLR mismatch | KASLR offsets not applied | Subtract KASLR offset or disable KASLR in build |

### 1.4 Synergy with `extract_kernel_oops_log`

1. Call `extract_kernel_oops_log(dmesg)` → get `call_trace` list
2. Pass `call_trace` addresses to `resolve_oops_symbols(vmlinux, addresses)`
3. First resolved frame in the trace is typically the faulting function

---

## 2. DTS Node Comparison (`compare_device_tree_nodes`)

### 2.1 Property Classification

| Change Type | Example | Risk |
|---|---|---|
| `compatible` modified | `vendor,device-v1` → `vendor,device-v2` | Driver may reject new string |
| `reg` / `ranges` modified | Base address change | Hardware address mismatch → probe failure |
| `status` modified | `okay` → `disabled` | Device silently disabled |
| `clock-names` added/removed | New clock dependency | Driver `devm_clk_get()` returns `-ENOENT` |
| `pinctrl-*` modified | Pin state name change | GPIO / UART pins not configured |
| `interrupts` modified | IRQ line change | Interrupts silently lost |

### 2.2 DTS Naming Conventions

- Node names: `peripheral@base_address` (e.g., `uart@7af0000`)
- Labels: `label: node_name { ... }` — labels used for `phandle` references
- Property names: lowercase with hyphens (`clock-names`, not `clockNames`)
- String properties: `"value"` — quoted
- Integer properties: `<0x1234>` — angle brackets, hex preferred for addresses
- Boolean properties (flags): bare name with no value (e.g., `msi-parent;`)

### 2.3 Debug Commands

```bash
# Decompile the compiled DTB back to DTS
dtc -I dtb -O dts /sys/firmware/fdt > /tmp/current.dts

# Check a node in the running device tree
cat /proc/device-tree/soc/uart@7af0000/status

# List all compatible strings
grep -r "compatible" /proc/device-tree/ 2>/dev/null
```

---

## 3. Kernel Config Diff (`diff_kernel_configs`)

### 3.1 Config Value Semantics

| Value | Meaning |
|---|---|
| `y` | Built into kernel image |
| `m` | Built as loadable module (`.ko`) |
| `n` | Explicitly disabled |
| *(absent / `not set`)* | Not configured (same as `n` for most options) |

### 3.2 High-Risk Config Changes

| Change | Risk |
|---|---|
| `m` → `y` | Feature now built-in; initrd/module-loading dependency may break |
| `y` → `n` or absent | Feature removed; userspace may depend on it |
| `CONFIG_DEBUG_INFO=n` | Loss of DWARF symbols — `resolve_oops_symbols` will fail |
| `CONFIG_MODULES=n` | All `.ko` modules disabled — any `m` option becomes no-op |
| `CONFIG_KALLSYMS=n` | Kernel symbol table removed — call traces lose function names |
| `CONFIG_RANDOMIZE_BASE` added | KASLR enabled — addr2line requires KASLR offset correction |

### 3.3 Propagating Config Changes

```bash
# Apply old config to new kernel tree (preserves explicit choices, fills gaps)
make oldconfig

# Apply old config silently (accept defaults for new symbols)
make olddefconfig

# Verify the config is self-consistent
make listnewconfig
```

---

## 4. GPIO / Pinctrl Conflict Detection (`validate_gpio_pinctrl_conflict`)

### 4.1 GPIO Assignment Patterns

The skill matches any property ending in `gpios` or `gpio`:

```dts
gpios = <&tlmm 4 GPIO_ACTIVE_HIGH>;
cs-gpios = <&tlmm 20 0>;
reset-gpios = <&pm8998_gpios 5 GPIO_ACTIVE_LOW>;
```

Pattern: `[\w-]*gpios? = <&<controller> <pin_num> ...>`

### 4.2 Conflict Types Detected

| Conflict Type | Example | Effect |
|---|---|---|
| Cross-node, same pin | GPIO 4 in `uart` node AND `spi` node | Both drivers request the same pin — second request fails with `-EBUSY` |
| Intra-node, multiple properties | `gpios` and `cs-gpios` both assign pin 87 | DTS misconfiguration — one assignment is redundant or wrong |

### 4.3 Conflict Resolution

```bash
# Check which driver currently owns a GPIO at runtime
cat /sys/kernel/debug/gpio | grep "gpio-87"

# Check pinctrl state
cat /sys/kernel/debug/pinctrl/pinctrl-maps | grep " 87 "

# gpio_request trace (enable at build time)
echo 1 > /sys/kernel/debug/gpio_trace
```

Resolution steps:
1. Identify the intended owner driver for the conflicted GPIO.
2. Remove `gpios` assignment from the non-owning node.
3. If sharing is intentional, use a `gpio-hog` or `regulator-fixed` node
   controlled by the owning driver.
4. Rebuild DTS and verify with `cat /sys/kernel/debug/gpio`.

---

## 5. Emulator Gaps

| Skill | Gap | Note |
|---|---|---|
| `resolve_oops_symbols` | QEMU virt vmlinux has no vendor BSP debug symbols | Patterns validated via mocked addr2line subprocess |
| `compare_device_tree_nodes` | QEMU virt DTS has no SoC peripheral nodes | Tests use synthetic node fragments |
| `diff_kernel_configs` | QEMU virt `.config` is minimal | Tests use synthetic config strings |
| `validate_gpio_pinctrl_conflict` | QEMU virt has no GPIO controller | Tests use synthetic DTS fragments with `tlmm` controller |
