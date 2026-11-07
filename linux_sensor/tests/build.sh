#!/usr/bin/env bash
# Linux CI only. All downloads and toolchains stay in this runner's /tmp.
set -euo pipefail
root=$(pwd)
work=${DESK_BUILDROOT_WORK:-/tmp/desk-buildroot}
mkdir -p "$work"
curl --fail --location --retry 3 https://buildroot.org/downloads/buildroot-2024.02.9.tar.xz -o "$work/buildroot.tar.xz"
tar -xf "$work/buildroot.tar.xz" -C "$work"
br="$work/buildroot-2024.02.9"
make -C "$br" BR2_EXTERNAL="$root/linux_sensor/buildroot" qemu_arm_vexpress_defconfig
cat >> "$br/.config" <<CONF
BR2_TOOLCHAIN_BUILDROOT_CXX=y
# BR2_PACKAGE_HOST_QEMU is not set
BR2_LINUX_KERNEL_INTREE_DTS_NAME="arm/vexpress-v2p-ca9"
BR2_PACKAGE_DESK_SENSOR=y
BR2_LINUX_KERNEL_CUSTOM_VERSION=y
BR2_LINUX_KERNEL_CUSTOM_VERSION_VALUE="6.6.63"
BR2_LINUX_KERNEL_CONFIG_FRAGMENT_FILES="$root/linux_sensor/buildroot/board/linux.fragment"
CONF
make -C "$br" olddefconfig
# Always rebuild our package from this checkout when the pinned toolchain is cached.
if [[ -d "$br/output/build/desk-sensor-1.0" ]]; then make -C "$br" desk-sensor-dirclean; fi
make -C "$br" -j2
mkdir -p linux_sensor/build
cp "$br/output/images/zImage" linux_sensor/build/
cp "$br/output/images/rootfs.ext2" linux_sensor/build/
dtc -@ -I dts -O dtb linux_sensor/desk-overlay.dts -o linux_sensor/build/desk.dtbo
fdtoverlay -i "$br/output/images/vexpress-v2p-ca9.dtb" -o linux_sensor/build/desk.dtb linux_sensor/build/desk.dtbo
python3 linux_sensor/tests/qemu.py
