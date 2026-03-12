"""
Tests for skills/bsp_diagnostics/android_init.py.

Covers analyze_selinux_denial and check_android_init_rc.
All tests are deterministic: no LLM calls, no network, no I/O.
"""
import pytest

from skills.bsp_diagnostics.android_init import (
    AndroidInitRCInput,
    AndroidInitRCOutput,
    SELinuxDenialInput,
    SELinuxDenialOutput,
    analyze_selinux_denial,
    check_android_init_rc,
)


# ---------------------------------------------------------------------------
# Fixtures — SELinux denial
# ---------------------------------------------------------------------------

CLEAN_LOG = """\
[   12.779457] LibBpfLoader: applying relo
[   13.000000] init: starting service 'zygote'...
[   13.100000] init: starting service 'netd'...
"""

AVC_DMESG_LOG = """\
[  128.521504] type=1400 audit(1773227155.624:8): avc: denied { syslog_read } for \
comm="dmesg" scontext=u:r:shell:s0 tcontext=u:r:kernel:s0 tclass=system permissive=0
"""

AVC_LOGCAT_LOG = (
    "03-11 11:03:56.284   189   189 I auditd  : type=1400 audit(0.0:4): "
    'avc: denied { execute_no_trans } for comm="init" path="/vendor/bin/toybox_vendor" '
    "dev=\"dm-4\" ino=222 scontext=u:r:init:s0 "
    "tcontext=u:object_r:vendor_toolbox_exec:s0 tclass=file permissive=0 bug=b/183668221\n"
)

AVC_PERMISSIVE_LOG = (
    "[   50.000000] type=1400 audit(0.0:1): "
    'avc: denied { read } for comm="app" '
    "scontext=u:r:untrusted_app:s0 tcontext=u:object_r:proc_net:s0 "
    "tclass=file permissive=1\n"
)

AVC_MULTI_LOG = """\
[  128.521504] type=1400 audit(1773227155.624:8): avc: denied { syslog_read } for \
comm="dmesg" scontext=u:r:shell:s0 tcontext=u:r:kernel:s0 tclass=system permissive=0
[  128.883175] type=1400 audit(1773227155.984:9): avc: denied { syslog_read } for \
comm="dmesg" scontext=u:r:shell:s0 tcontext=u:r:kernel:s0 tclass=system permissive=0
[  129.000000] type=1400 audit(0.0:10): avc: denied { write } for comm="logd" \
scontext=u:r:logd:s0 tcontext=u:object_r:kmsg_device:s0 tclass=chr_file permissive=0
"""

# ---------------------------------------------------------------------------
# Fixtures — init.rc
# ---------------------------------------------------------------------------

CLEAN_INIT_LOG = """\
[   13.000000] init: starting service 'zygote'...
[   13.100000] init: starting service 'netd'...
[   13.326794] init: Service 'bpfloader' (pid 275) exited with status 0 waiting took 0.633000 seconds
[   13.329317] init: Sending signal 9 to service 'bpfloader' (pid 275) process group...
"""

INIT_CMD_FAIL_LOG = """\
[   13.385514] init: Command 'start zygote_secondary' \
action=ro.crypto.state=encrypted && ro.crypto.type=file && zygote-start \
(/system/etc/init/hw/init.rc:1062) took 0ms and failed: service zygote_secondary not found
[   13.411183] init: Command 'symlink /sys/fs/f2fs/${dev.mnt.dev.data} /dev/sys/fs/by-name/userdata' \
action=boot (/system/etc/init/hw/init.rc:1092) took 0ms and failed: \
property 'dev.mnt.dev.data' doesn't exist while expanding '/sys/fs/f2fs/${dev.mnt.dev.data}'
"""

INIT_SVC_CRASH_LOG = (
    "[   20.000000] init: Service 'vendor.camera-provider-2-4' "
    "(pid 500) exited with status 1\n"
)

INIT_SVC_ZERO_EXIT_LOG = (
    "[   13.326794] init: Service 'update_verifier' (pid 282) exited with status 0 "
    "waiting took 0.010000 seconds\n"
)


# ---------------------------------------------------------------------------
# TestSchemas — analyze_selinux_denial
# ---------------------------------------------------------------------------

class TestSELinuxSchemas:
    def test_input_schema(self):
        inp = SELinuxDenialInput(logcat_log="test")
        assert inp.logcat_log == "test"

    def test_output_fields_present(self):
        out = analyze_selinux_denial(CLEAN_LOG)
        assert isinstance(out, SELinuxDenialOutput)
        assert hasattr(out, "denial_detected")
        assert hasattr(out, "denial_count")
        assert hasattr(out, "denials")
        assert hasattr(out, "enforcing_count")
        assert hasattr(out, "root_cause")
        assert hasattr(out, "recommended_action")
        assert hasattr(out, "confidence")

    def test_output_is_serialisable(self):
        out = analyze_selinux_denial(AVC_DMESG_LOG)
        d = out.model_dump()
        assert isinstance(d["denials"], list)


# ---------------------------------------------------------------------------
# TestNoDenial
# ---------------------------------------------------------------------------

class TestNoDenial:
    def test_clean_log_no_denial(self):
        out = analyze_selinux_denial(CLEAN_LOG)
        assert out.denial_detected is False

    def test_empty_log_no_denial(self):
        out = analyze_selinux_denial("")
        assert out.denial_detected is False

    def test_denial_count_zero_on_clean(self):
        out = analyze_selinux_denial(CLEAN_LOG)
        assert out.denial_count == 0

    def test_high_confidence_on_clean(self):
        out = analyze_selinux_denial(CLEAN_LOG)
        assert out.confidence >= 0.85


# ---------------------------------------------------------------------------
# TestSingleDenial — dmesg format
# ---------------------------------------------------------------------------

class TestDmesgFormatDenial:
    def setup_method(self):
        self.out = analyze_selinux_denial(AVC_DMESG_LOG)

    def test_denial_detected(self):
        assert self.out.denial_detected is True

    def test_denial_count(self):
        assert self.out.denial_count >= 1

    def test_permission_extracted(self):
        assert self.out.denials[0].permission == "syslog_read"

    def test_comm_extracted(self):
        assert self.out.denials[0].comm == "dmesg"

    def test_scontext_extracted(self):
        assert self.out.denials[0].scontext == "u:r:shell:s0"

    def test_tcontext_extracted(self):
        assert self.out.denials[0].tcontext == "u:r:kernel:s0"

    def test_tclass_extracted(self):
        assert self.out.denials[0].tclass == "system"

    def test_enforcing_denial(self):
        assert self.out.denials[0].permissive is False

    def test_enforcing_count(self):
        assert self.out.enforcing_count >= 1

    def test_high_confidence(self):
        assert self.out.confidence >= 0.85


# ---------------------------------------------------------------------------
# TestSingleDenial — logcat format
# ---------------------------------------------------------------------------

class TestLogcatFormatDenial:
    def setup_method(self):
        self.out = analyze_selinux_denial(AVC_LOGCAT_LOG)

    def test_denial_detected(self):
        assert self.out.denial_detected is True

    def test_permission_extracted(self):
        assert self.out.denials[0].permission == "execute_no_trans"

    def test_comm_extracted(self):
        assert self.out.denials[0].comm == "init"

    def test_tclass_is_file(self):
        assert self.out.denials[0].tclass == "file"


# ---------------------------------------------------------------------------
# TestPermissiveMode
# ---------------------------------------------------------------------------

class TestPermissiveMode:
    def setup_method(self):
        self.out = analyze_selinux_denial(AVC_PERMISSIVE_LOG)

    def test_denial_detected(self):
        assert self.out.denial_detected is True

    def test_denial_is_permissive(self):
        assert self.out.denials[0].permissive is True

    def test_enforcing_count_zero(self):
        assert self.out.enforcing_count == 0

    def test_lower_confidence_in_permissive_mode(self):
        # All-permissive denials are less critical than enforcing
        assert self.out.confidence < 0.90


# ---------------------------------------------------------------------------
# TestMultipleDenials
# ---------------------------------------------------------------------------

class TestMultipleDenials:
    def setup_method(self):
        self.out = analyze_selinux_denial(AVC_MULTI_LOG)

    def test_denial_detected(self):
        assert self.out.denial_detected is True

    def test_raw_count(self):
        # 3 raw denial lines (2 are duplicates of syslog_read)
        assert self.out.denial_count == 3

    def test_deduplicated_entries(self):
        # After deduplication: syslog_read + write = 2 unique entries
        assert len(self.out.denials) == 2

    def test_enforcing_count(self):
        assert self.out.enforcing_count == 3


# ---------------------------------------------------------------------------
# TestInitRCSchemas
# ---------------------------------------------------------------------------

class TestInitRCSchemas:
    def test_input_schema(self):
        inp = AndroidInitRCInput(dmesg_log="test")
        assert inp.dmesg_log == "test"

    def test_output_fields_present(self):
        out = check_android_init_rc(CLEAN_INIT_LOG)
        assert isinstance(out, AndroidInitRCOutput)
        assert hasattr(out, "failure_detected")
        assert hasattr(out, "failed_commands")
        assert hasattr(out, "failed_services")
        assert hasattr(out, "root_cause")
        assert hasattr(out, "recommended_action")
        assert hasattr(out, "confidence")

    def test_output_is_serialisable(self):
        out = check_android_init_rc(INIT_CMD_FAIL_LOG)
        d = out.model_dump()
        assert isinstance(d["failed_commands"], list)


# ---------------------------------------------------------------------------
# TestNoFailure
# ---------------------------------------------------------------------------

class TestNoFailure:
    def test_clean_init_no_failure(self):
        out = check_android_init_rc(CLEAN_INIT_LOG)
        assert out.failure_detected is False

    def test_empty_log_no_failure(self):
        out = check_android_init_rc("")
        assert out.failure_detected is False

    def test_zero_exit_not_flagged(self):
        out = check_android_init_rc(INIT_SVC_ZERO_EXIT_LOG)
        assert out.failure_detected is False

    def test_high_confidence_on_clean(self):
        out = check_android_init_rc(CLEAN_INIT_LOG)
        assert out.confidence >= 0.85


# ---------------------------------------------------------------------------
# TestCommandFailure
# ---------------------------------------------------------------------------

class TestCommandFailure:
    def setup_method(self):
        self.out = check_android_init_rc(INIT_CMD_FAIL_LOG)

    def test_failure_detected(self):
        assert self.out.failure_detected is True

    def test_two_failed_commands(self):
        assert len(self.out.failed_commands) == 2

    def test_first_command_extracted(self):
        assert self.out.failed_commands[0].command == "start zygote_secondary"

    def test_first_reason_extracted(self):
        assert "zygote_secondary not found" in self.out.failed_commands[0].reason

    def test_first_rc_file_extracted(self):
        assert "init.rc" in self.out.failed_commands[0].rc_file

    def test_first_rc_line_extracted(self):
        assert self.out.failed_commands[0].rc_line == 1062

    def test_second_command_extracted(self):
        assert "symlink" in self.out.failed_commands[1].command

    def test_second_reason_extracted(self):
        assert "dev.mnt.dev.data" in self.out.failed_commands[1].reason

    def test_reasonable_confidence(self):
        assert self.out.confidence >= 0.80


# ---------------------------------------------------------------------------
# TestServiceCrash
# ---------------------------------------------------------------------------

class TestServiceCrash:
    def test_nonzero_exit_detected(self):
        out = check_android_init_rc(INIT_SVC_CRASH_LOG)
        assert out.failure_detected is True
        assert len(out.failed_services) == 1

    def test_service_name_extracted(self):
        out = check_android_init_rc(INIT_SVC_CRASH_LOG)
        assert out.failed_services[0].service == "vendor.camera-provider-2-4"

    def test_exit_status_extracted(self):
        out = check_android_init_rc(INIT_SVC_CRASH_LOG)
        assert out.failed_services[0].exit_status == 1

    def test_pid_extracted(self):
        out = check_android_init_rc(INIT_SVC_CRASH_LOG)
        assert out.failed_services[0].pid == 500

    def test_zero_exit_not_failure(self):
        out = check_android_init_rc(INIT_SVC_ZERO_EXIT_LOG)
        assert out.failure_detected is False
        assert len(out.failed_services) == 0


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_mixed_selinux_and_init_log(self):
        combined = AVC_DMESG_LOG + INIT_CMD_FAIL_LOG
        selinux_out = analyze_selinux_denial(combined)
        init_out = check_android_init_rc(combined)
        assert selinux_out.denial_detected is True
        assert init_out.failure_detected is True

    def test_recommended_action_not_empty_selinux(self):
        out = analyze_selinux_denial(AVC_DMESG_LOG)
        assert len(out.recommended_action) > 10

    def test_recommended_action_not_empty_init(self):
        out = check_android_init_rc(INIT_CMD_FAIL_LOG)
        assert len(out.recommended_action) > 10
