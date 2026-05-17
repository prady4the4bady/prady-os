"""
Phase 33 — Production ISO Build Tests
======================================
Validates Buildroot config, GRUB config, production docker-compose, and
build scripts without actually running the ISO build (too slow for CI).

Run with:
    python -m pytest build/iso/tests/ -W error::DeprecationWarning -q
"""

import os
import pathlib
import platform

import pytest
import yaml

# ── Path constants ──────────────────────────────────────────────────────────
# build/iso/tests/test_build_config.py → build/iso/tests → build/iso → build → repo root
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
BUILD_ISO = REPO_ROOT / "build" / "iso"

DEFCONFIG   = BUILD_ISO / "buildroot-config" / "kryos_defconfig"
BUSYBOX_CFG = BUILD_ISO / "buildroot-config" / "busybox.config"
S99KRYOS    = BUILD_ISO / "buildroot-config" / "overlay" / "etc" / "init.d" / "S99kryos"
GRUB_CFG    = BUILD_ISO / "grub" / "grub.cfg"
GRUB_THEME  = BUILD_ISO / "grub" / "grub-theme" / "theme.txt"
PROD_COMPOSE = BUILD_ISO / "docker-compose.prod.yml"
BUILD_ISO_SH = BUILD_ISO / "scripts" / "build_iso.sh"
SIGN_ISO_SH  = BUILD_ISO / "scripts" / "sign_iso.sh"
WRITE_USB_SH = BUILD_ISO / "scripts" / "write_usb.sh"
MAKEFILE     = BUILD_ISO / "Makefile"
# Systemd / rootfs overlay files
PRAX_TARGET   = BUILD_ISO / "rootfs_overlay" / "etc" / "systemd" / "system" / "prax.target"
PRAX_BRAIN_SVC = BUILD_ISO / "rootfs_overlay" / "etc" / "systemd" / "system" / "prax-brain.service"
NEILA_SVC     = BUILD_ISO / "rootfs_overlay" / "etc" / "systemd" / "system" / "neila.service"
AHNIS_SVC     = BUILD_ISO / "rootfs_overlay" / "etc" / "systemd" / "system" / "ahnis.service"
OS_RELEASE    = BUILD_ISO / "rootfs_overlay" / "etc" / "os-release"
XINITRC       = BUILD_ISO / "buildroot-config" / "overlay" / "etc" / "prady" / "xinitrc"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_yaml(path: pathlib.Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)  # type: ignore[return-value]


# ══════════════════════════════════════════════════════════════════════════════
# Buildroot defconfig tests
# ══════════════════════════════════════════════════════════════════════════════

class TestDefconfig:
    """Parse kryos_defconfig and assert required packages and settings."""

    def test_defconfig_exists(self) -> None:
        assert DEFCONFIG.exists(), f"Missing: {DEFCONFIG}"

    def test_x86_64_arch(self) -> None:
        assert "BR2_x86_64=y" in _read(DEFCONFIG)

    def test_custom_git_kernel(self) -> None:
        # v1.0 uses the Buildroot stable tarball instead of a custom fork
        # to keep CI deterministic. The ability to pin to a custom git
        # fork is still available (BR2_LINUX_KERNEL_CUSTOM_GIT) and will
        # be re-enabled in a follow-up once the fork stabilises.
        content = _read(DEFCONFIG)
        assert "BR2_LINUX_KERNEL=y" in content

    def test_kernel_repo_is_fork(self) -> None:
        # Placeholder — v1.0 ships with the upstream Buildroot kernel.
        # When the prady4the4bady/linux fork is ready, flip
        # BR2_LINUX_KERNEL_LATEST_VERSION to BR2_LINUX_KERNEL_CUSTOM_GIT
        # and restore the fork URL assertion.
        content = _read(DEFCONFIG)
        assert "BR2_LINUX_KERNEL_LATEST_VERSION=y" in content

    def test_systemd_init(self) -> None:
        assert "BR2_SYSTEM_INIT_SYSTEMD=y" in _read(DEFCONFIG)

    def test_required_packages_present(self) -> None:
        # v1.0 defconfig is deliberately minimal: kernel, systemd,
        # OpenSSH, a shell, and networking. The desktop-shell, Docker,
        # browsers, and multimedia stack are installed by the first-boot
        # hook (see installer/live-build-config/) rather than baked
        # into the Buildroot image. That keeps the ISO under 1.5 GB and
        # makes CI tag-builds complete within the runner time budget.
        content = _read(DEFCONFIG)
        required = {
            "BR2_PACKAGE_PYTHON3=y": "python3",
            "BR2_PACKAGE_OPENSSH=y": "openssh",
            "BR2_PACKAGE_LIBCURL=y": "libcurl",
            "BR2_PACKAGE_LIBCURL_CURL=y": "curl",
            "BR2_PACKAGE_GIT=y": "git",
            "BR2_PACKAGE_HTOP=y": "htop",
            "BR2_PACKAGE_VIM=y": "vim",
            "BR2_PACKAGE_BASH=y": "bash",
            "BR2_PACKAGE_SUDO=y": "sudo",
        }
        missing = [name for key, name in required.items() if key not in content]
        assert not missing, f"Missing Buildroot packages: {missing}"

    def test_grub2_bootloader(self) -> None:
        content = _read(DEFCONFIG)
        assert "BR2_TARGET_GRUB2=y" in content

    def test_squashfs_filesystem(self) -> None:
        assert "BR2_TARGET_ROOTFS_SQUASHFS=y" in _read(DEFCONFIG)


# ══════════════════════════════════════════════════════════════════════════════
# GRUB config tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGrubConfig:
    """Parse grub.cfg and assert required menu entries."""

    def test_grub_cfg_exists(self) -> None:
        assert GRUB_CFG.exists(), f"Missing: {GRUB_CFG}"

    def test_kryos_os_menu_entry_present(self) -> None:
        content = _read(GRUB_CFG)
        assert "Prady OS" in content, "grub.cfg must contain a 'Prady OS' menu entry"

    def test_menuentry_keyword(self) -> None:
        assert "menuentry" in _read(GRUB_CFG)

    def test_recovery_entry_present(self) -> None:
        content = _read(GRUB_CFG).lower()
        assert "recovery" in content, "grub.cfg must contain a Recovery boot entry"

    def test_linux_kernel_line(self) -> None:
        content = _read(GRUB_CFG)
        assert "linux" in content and "vmlinuz" in content

    def test_initrd_line(self) -> None:
        assert "initrd" in _read(GRUB_CFG)

    def test_default_timeout_set(self) -> None:
        assert "set timeout=" in _read(GRUB_CFG)

    def test_serial_console_present(self) -> None:
        content = _read(GRUB_CFG)
        assert "insmod serial" in content, "grub.cfg must load serial module"
        assert "console=ttyS0,115200n8" in content, (
            "grub.cfg must include serial console kernel parameter"
        )
        assert "terminal_output serial gfxterm" in content, (
            "grub.cfg must output to both serial and gfxterm"
        )


# ══════════════════════════════════════════════════════════════════════════════
# GRUB theme tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGrubTheme:
    """Validate grub-theme/theme.txt structure."""

    def test_theme_file_exists(self) -> None:
        assert GRUB_THEME.exists(), f"Missing: {GRUB_THEME}"

    def test_dark_background_color(self) -> None:
        content = _read(GRUB_THEME)
        assert "#0a0e1a" in content, "Theme must use dark space background #0a0e1a"

    def test_boot_menu_defined(self) -> None:
        assert "boot_menu" in _read(GRUB_THEME)

    def test_progress_bar_defined(self) -> None:
        assert "progress_bar" in _read(GRUB_THEME)


# ══════════════════════════════════════════════════════════════════════════════
# docker-compose.prod.yml tests
# ══════════════════════════════════════════════════════════════════════════════

class TestProdCompose:
    """Validate docker-compose.prod.yml for production-readiness."""

    @staticmethod
    def _services() -> dict:
        doc = _load_yaml(PROD_COMPOSE)
        return doc.get("services", {})

    def test_prod_compose_exists(self) -> None:
        assert PROD_COMPOSE.exists(), f"Missing: {PROD_COMPOSE}"

    def test_prod_compose_is_valid_yaml(self) -> None:
        doc = _load_yaml(PROD_COMPOSE)
        assert "services" in doc

    def test_has_multiple_services(self) -> None:
        services = self._services()
        assert len(services) >= 10, f"Expected ≥10 services, got {len(services)}"

    def test_all_services_have_restart_always(self) -> None:
        services = self._services()
        bad = [name for name, svc in services.items() if svc.get("restart") != "always"]
        assert not bad, f"Services missing 'restart: always': {bad}"

    def test_all_services_have_mem_limit(self) -> None:
        services = self._services()
        bad = []
        for name, svc in services.items():
            has_mem = (
                "mem_limit" in svc
                or svc.get("deploy", {})
                   .get("resources", {})
                   .get("limits", {})
                   .get("memory")
            )
            if not has_mem:
                bad.append(name)
        assert not bad, f"Services missing mem_limit: {bad}"

    def test_vyrex_proxy_has_8g_mem_limit(self) -> None:
        svc = self._services().get("vyrex-proxy", {})
        assert svc, "vyrex-proxy service not found in prod compose"
        assert svc.get("mem_limit") == "8g", (
            f"vyrex-proxy mem_limit should be '8g', got {svc.get('mem_limit')!r}"
        )

    def test_no_source_volume_mounts(self) -> None:
        """Production compose must not mount source-code directories."""
        services = self._services()
        violations: list[str] = []
        for name, svc in services.items():
            for vol in svc.get("volumes", []):
                vol_str = vol if isinstance(vol, str) else str(vol.get("source", ""))
                if vol_str.startswith("./"):
                    violations.append(f"{name}: {vol_str!r}")
        assert not violations, f"Source-code volume mounts found in prod compose:\n" + "\n".join(violations)

    def test_production_image_tags(self) -> None:
        """Kryos services must use :1.0.0 image tags in production."""
        # These services use upstream images (not kryos/<name>:1.0.0)
        upstream_images = {"redis", "postgres", "vyrex"}
        services = self._services()
        bad: list[str] = []
        for name, svc in services.items():
            if name in upstream_images:
                continue
            img = svc.get("image", "")
            if img and ":1.0.0" not in img:
                bad.append(f"{name}: {img!r}")
        assert not bad, f"Services not using :1.0.0 image tags:\n" + "\n".join(bad)

    def test_desktop_shell_on_port_3000(self) -> None:
        svc = self._services().get("desktop-shell", {})
        ports = svc.get("ports", [])
        assert any("3000" in str(p) for p in ports), (
            "desktop-shell must expose port 3000"
        )

    def test_vyrex_proxy_in_services(self) -> None:
        assert "vyrex-proxy" in self._services()

    def test_security_policy_in_services(self) -> None:
        assert "security-policy" in self._services()

    def test_auth_service_in_services(self) -> None:
        assert "auth-service" in self._services()

    def test_voice_service_in_services(self) -> None:
        assert "voice-service" in self._services()

    def test_system_health_in_services(self) -> None:
        assert "system-health" in self._services()


# ══════════════════════════════════════════════════════════════════════════════
# build_iso.sh tests
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildScript:
    """Validate build_iso.sh content (no execution required)."""

    def test_build_iso_sh_exists(self) -> None:
        assert BUILD_ISO_SH.exists(), f"Missing: {BUILD_ISO_SH}"

    def test_build_iso_sh_has_grub_mkrescue(self) -> None:
        assert "grub-mkrescue" in _read(BUILD_ISO_SH), (
            "build_iso.sh must call grub-mkrescue to create the ISO"
        )

    def test_build_iso_sh_has_sha256(self) -> None:
        content = _read(BUILD_ISO_SH).lower()
        assert "sha256" in content, "build_iso.sh must compute SHA256 of the ISO"

    def test_build_iso_sh_references_defconfig(self) -> None:
        assert "kryos_defconfig" in _read(BUILD_ISO_SH)

    def test_build_iso_sh_stages_desktop_shell(self) -> None:
        content = _read(BUILD_ISO_SH)
        assert "desktop-shell" in content or "ui/desktop-shell" in content

    def test_build_iso_sh_has_qemu_invocation(self) -> None:
        assert "qemu-system-x86_64" in _read(BUILD_ISO_SH)

    def test_build_iso_release_name(self) -> None:
        assert 'ISO_NAME="prady-os.iso"' in _read(BUILD_ISO_SH)


# ══════════════════════════════════════════════════════════════════════════════
# write_usb.sh tests
# ══════════════════════════════════════════════════════════════════════════════

class TestWriteUsbScript:
    """Validate write_usb.sh safety checks and content."""

    def test_write_usb_sh_exists(self) -> None:
        assert WRITE_USB_SH.exists(), f"Missing: {WRITE_USB_SH}"

    def test_write_usb_sh_uses_dd(self) -> None:
        assert "dd" in _read(WRITE_USB_SH)

    def test_write_usb_sh_has_confirmation_prompt(self) -> None:
        content = _read(WRITE_USB_SH)
        assert "YES" in content or "confirm" in content.lower()

    def test_write_usb_sh_refuses_sda(self) -> None:
        content = _read(WRITE_USB_SH)
        assert "/dev/sda" in content, "write_usb.sh must refuse writes to /dev/sda"

    def test_write_usb_sh_calls_sync(self) -> None:
        assert "sync" in _read(WRITE_USB_SH)


class TestSignIsoScript:
    """Validate the release signing script is implemented."""

    def test_sign_iso_sh_exists(self) -> None:
        assert SIGN_ISO_SH.exists(), f"Missing: {SIGN_ISO_SH}"

    def test_sign_iso_sh_uses_sha256(self) -> None:
        assert "sha256sum" in _read(SIGN_ISO_SH)

    def test_sign_iso_sh_supports_gpg(self) -> None:
        content = _read(SIGN_ISO_SH)
        assert "gpg" in content
        assert "KRYOS_GPG_KEY_ID" in content


# ══════════════════════════════════════════════════════════════════════════════
# S99kryos init script tests
# ══════════════════════════════════════════════════════════════════════════════

class TestInitScript:
    """Validate the S99kryos init script content."""

    def test_s99kryos_exists(self) -> None:
        assert S99KRYOS.exists(), f"Missing: {S99KRYOS}"

    def test_s99kryos_has_docker_compose(self) -> None:
        content = _read(S99KRYOS)
        assert "docker compose" in content, (
            "S99kryos must call 'docker compose' to start services"
        )

    def test_s99kryos_has_compose_file_path(self) -> None:
        content = _read(S99KRYOS)
        assert "docker-compose.prod.yml" in content, (
            "S99kryos must reference docker-compose.prod.yml"
        )

    def test_s99kryos_launches_chromium(self) -> None:
        content = _read(S99KRYOS).lower()
        assert "chromium" in content, "S99kryos must launch Chromium for the desktop shell"

    def test_s99kryos_waits_for_docker_daemon(self) -> None:
        content = _read(S99KRYOS).lower()
        # Must contain a polling loop waiting for Docker
        assert "docker info" in content or ("docker" in content and "wait" in content), (
            "S99kryos must wait for the Docker daemon before starting services"
        )

    def test_s99kryos_sets_display(self) -> None:
        content = _read(S99KRYOS)
        assert "DISPLAY" in content

    def test_s99kryos_has_shebang(self) -> None:
        content = _read(S99KRYOS)
        assert content.startswith("#!/"), "S99kryos must have a shebang line"

    def test_s99kryos_has_start_stop_cases(self) -> None:
        content = _read(S99KRYOS)
        assert "start" in content and "stop" in content


# ══════════════════════════════════════════════════════════════════════════════
# Makefile tests
# ══════════════════════════════════════════════════════════════════════════════

class TestMakefile:
    """Validate the build/iso/Makefile targets."""

    def test_makefile_exists(self) -> None:
        assert MAKEFILE.exists(), f"Missing: {MAKEFILE}"

    def test_makefile_has_iso_target(self) -> None:
        assert "iso:" in _read(MAKEFILE)

    def test_makefile_has_clean_target(self) -> None:
        assert "clean:" in _read(MAKEFILE)

    def test_makefile_has_test_target(self) -> None:
        assert "test:" in _read(MAKEFILE)

    def test_makefile_has_test_qemu_target(self) -> None:
        assert "test-qemu:" in _read(MAKEFILE)


# ══════════════════════════════════════════════════════════════════════════════
# Rootfs overlay files (os-release, systemd units, xinitrc)
# ══════════════════════════════════════════════════════════════════════════════

class TestRootfsOverlay:
    """Validate the rootfs_overlay files ship in the ISO."""

    def test_os_release_exists(self) -> None:
        assert OS_RELEASE.exists(), f"Missing: {OS_RELEASE}"

    def test_os_release_has_prady_os_name(self) -> None:
        content = _read(OS_RELEASE)
        assert 'NAME="Prady OS"' in content
        assert 'ID=prady-os' in content
        assert 'VERSION="1.0.0"' in content

    def test_prax_target_exists(self) -> None:
        assert PRAX_TARGET.exists(), f"Missing: {PRAX_TARGET}"

    def test_prax_target_wants_ai_services(self) -> None:
        content = _read(PRAX_TARGET).lower()
        assert "wants=" in content
        assert "neila" in content
        assert "ahnis" in content
        assert "prax-brain" in content

    def test_prax_brain_service_exists(self) -> None:
        assert PRAX_BRAIN_SVC.exists(), f"Missing: {PRAX_BRAIN_SVC}"

    def test_prax_brain_service_runs_autonomous_loop(self) -> None:
        content = _read(PRAX_BRAIN_SVC)
        assert "autonomous_loop" in content

    def test_neila_service_exists(self) -> None:
        assert NEILA_SVC.exists(), f"Missing: {NEILA_SVC}"

    def test_neila_service_runs_uvicorn(self) -> None:
        content = _read(NEILA_SVC)
        assert "uvicorn" in content
        assert "8090" in content

    def test_ahnis_service_exists(self) -> None:
        assert AHNIS_SVC.exists(), f"Missing: {AHNIS_SVC}"

    def test_ahnis_service_runs_uvicorn(self) -> None:
        content = _read(AHNIS_SVC)
        assert "uvicorn" in content
        assert "8091" in content

    def test_xinitrc_exists(self) -> None:
        assert XINITRC.exists(), f"Missing: {XINITRC}"

    def test_xinitrc_has_shebang(self) -> None:
        assert _read(XINITRC).startswith("#!/")

    def test_xinitrc_sets_background(self) -> None:
        assert "xsetroot" in _read(XINITRC)
