# XVF3800 firmware (from github.com/respeaker/reSpeaker_XVF3800_USB_4MIC_ARRAY)

Not in git — Seeed's repo has no license, so we fetch instead of redistributing:
`bash scripts/fetch_xvf_kit.sh` (the setup scripts run it) downloads these files here.

- `respeaker_xvf3800_usb_dfu_firmware_v2.1.0_16k6ch.bin` — **USB, 16 kHz, 6 channels. The one Sona uses.**
- `respeaker_xvf3800_usb_dfu_firmware_v2.1.0.bin` — USB, 16 kHz, 2 channels (fallback).
- `respeaker_xvf3800_i2s_dfu_firmware_v1.0.7.bin` — the I2S firmware the XIAO board ships with (to revert).
- `doa_convention.jpg` — how the reported azimuth maps to the physical board.
- `dfu_guide.md` — Seeed's official flashing guide.

## Flash (Mac or Pi)
1. Use the **XMOS USB-C port — the one beside the 3.5 mm jack** (the other port is the XIAO).
2. Unplug. **Hold MUTE, plug in while holding, keep holding until the red LED blinks** → safe/DFU mode.
3. `dfu-util -l` must show `[2886:001a] ... "reSpeaker DFU Upgrade"`.
4. `dfu-util -R -e -a 1 -D firmware/xvf3800/respeaker_xvf3800_usb_dfu_firmware_v2.1.0_16k6ch.bin`
   (`sudo` on the Pi). `-R` reboots it; it then enumerates as a USB mic.
5. Verify: `tools/xvf_host/mac_arm64/xvf_host VERSION` then `... AEC_AZIMUTH_VALUES`.

Note: USB firmware takes the XVF3800 off the I2S bus — the XIAO no longer receives audio.
Recovery image (4 MB blank) if ever needed: `xmos_firmwares/recover/4mb_all_ff.bin` in the repo above.
