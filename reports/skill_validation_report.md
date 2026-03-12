  ✅ LOG-001 [segment_boot_log]
  ✅ LOG-002 [segment_boot_log]
  ✅ LOG-003 [segment_boot_log]
  ✅ LOG-004 [segment_boot_log]
  ✅ LOG-005 [parse_early_boot_uart_log]
  ✅ LOG-006 [parse_early_boot_uart_log]
  ✅ LOG-007 [parse_early_boot_uart_log]
  ✅ LOG-008 [analyze_lk_panic]
  ✅ LOG-009 [analyze_lk_panic]
  ✅ LOG-010 [extract_kernel_oops_log]
  ✅ LOG-011 [extract_kernel_oops_log]
  ✅ LOG-012 [extract_kernel_oops_log]
  ✅ LOG-013 [decode_esr_el1 + check_cache_coherency_panic]
  ✅ LOG-014 [analyze_watchdog_timeout]
  ✅ LOG-015 [analyze_watchdog_timeout]
  ✅ LOG-016 [analyze_watchdog_timeout]
  ✅ LOG-017 [analyze_watchdog_timeout + decode_esr_el1]
  ✅ LOG-018 [analyze_std_hibernation_error]
  ✅ LOG-019 [analyze_std_hibernation_error]
  ✅ LOG-020 [check_vendor_boot_ufs_driver]
  ✅ LOG-021 [check_vendor_boot_ufs_driver]
  ✅ LOG-022 [check_pmic_rail_voltage]
  ✅ LOG-023 [check_pmic_rail_voltage]
  ✅ LOG-024 [check_pmic_rail_voltage (negative)]
  ✅ LOG-025 [segment_boot_log]
  ✅ LOG-026 [segment_boot_log + parse_early_boot_uart_log]
  ✅ LOG-027 [segment_boot_log]
  ✅ LOG-028 [segment_boot_log]

<!-- JSON report written to logs/validation/skill_validation_report.json -->
# BSP Skill Validation Report

Validated 28 log entries against 28 skill runs.

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | 28 |
| ⚠️  PARTIAL | 0 |
| ❌ FAIL | 0 |
| 💥 ERROR | 0 |

## Results

| ID | File | Skill | Status | Details |
|---|---|---|---|---|
| LOG-001 | `d0_android_normal_boot.log` | `segment_boot_log` | ✅ PASS | All checks passed |
| LOG-002 | `d0_linux_kernel_only.log` | `segment_boot_log` | ✅ PASS | All checks passed |
| LOG-003 | `d0_mixed_uart_kernel.log` | `segment_boot_log` | ✅ PASS | All checks passed |
| LOG-004 | `d0_unknown_fragment.log` | `segment_boot_log` | ✅ PASS | All checks passed |
| LOG-005 | `d1_tfa_auth_failure.log` | `parse_early_boot_uart_log` | ✅ PASS | All checks passed |
| LOG-006 | `d1_lk_ddr_init_fail.log` | `parse_early_boot_uart_log` | ✅ PASS | All checks passed |
| LOG-007 | `d1_tfa_pmic_failure.log` | `parse_early_boot_uart_log` | ✅ PASS | All checks passed |
| LOG-008 | `d1_lk_assert_arm32.log` | `analyze_lk_panic` | ✅ PASS | All checks passed |
| LOG-009 | `d1_lk_panic_aarch64.log` | `analyze_lk_panic` | ✅ PASS | All checks passed |
| LOG-010 | `d2_qemu_null_pointer.log` | `extract_kernel_oops_log` | ✅ PASS | All checks passed |
| LOG-011 | `d2_aarch64_null_ptr.log` | `extract_kernel_oops_log` | ✅ PASS | All checks passed |
| LOG-012 | `d2_aarch64_paging_request.log` | `extract_kernel_oops_log` | ✅ PASS | All checks passed |
| LOG-013 | `d2_serror_interrupt.log` | `decode_esr_el1 + check_cache_coherency_panic` | ✅ PASS | All checks passed |
| LOG-014 | `d2_soft_lockup.log` | `analyze_watchdog_timeout` | ✅ PASS | All checks passed |
| LOG-015 | `d2_hard_lockup.log` | `analyze_watchdog_timeout` | ✅ PASS | All checks passed |
| LOG-016 | `d2_rcu_stall.log` | `analyze_watchdog_timeout` | ✅ PASS | All checks passed |
| LOG-017 | `d2_watchdog_serror_combined.log` | `analyze_watchdog_timeout + decode_esr_el1` | ✅ PASS | All checks passed |
| LOG-018 | `d3_std_high_sunreclaim.log` | `analyze_std_hibernation_error` | ✅ PASS | All checks passed |
| LOG-019 | `d3_std_swap_exhausted.log` | `analyze_std_hibernation_error` | ✅ PASS | All checks passed |
| LOG-020 | `d3_ufs_probe_fail.log` | `check_vendor_boot_ufs_driver` | ✅ PASS | All checks passed |
| LOG-021 | `d3_ufs_link_startup_fail.log` | `check_vendor_boot_ufs_driver` | ✅ PASS | All checks passed |
| LOG-022 | `d3_pmic_ocp_display.log` | `check_pmic_rail_voltage` | ✅ PASS | All checks passed |
| LOG-023 | `d3_pmic_undervoltage_cpu.log` | `check_pmic_rail_voltage` | ✅ PASS | All checks passed |
| LOG-024 | `d3_pmic_clean_boot.log` | `check_pmic_rail_voltage (negative)` | ✅ PASS | All checks passed |
| LOG-025 | `d4_ambiguous_ufs_kernel.log` | `segment_boot_log` | ✅ PASS | All checks passed |
| LOG-026 | `d4_early_boot_healthy.log` | `segment_boot_log + parse_early_boot_uart_log` | ✅ PASS | All checks passed |
| LOG-027 | `d4_android_selinux_avc.log` | `segment_boot_log` | ✅ PASS | All checks passed |
| LOG-028 | `d4_android_slow_boot.log` | `segment_boot_log` | ✅ PASS | All checks passed |

## Detailed Findings


