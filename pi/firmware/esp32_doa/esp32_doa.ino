// Sona — ReSpeaker XVF3800 (XIAO ESP32S3 variant): read DoA + VAD over I2C,
// stream over USB serial as "DOA:<deg>,VAD:<0|1>" at 10 Hz.
//
// Based on Seeed's example:
//   https://wiki.seeedstudio.com/respeaker_xvf3800_xiao_doa_vad/
// Requires the XVF3800 I2S firmware (e.g. respeaker_xvf3800_i2s_dfu_firmware_v1.0.7.bin).
//
// HARDWARE-DAY TODO: verify against the wiki example on the bench —
//  * the read flag (XMOS control reads set bit7 of the command id),
//  * the 4-byte payload layout (angle low/high byte + speech flag),
//  * whether Wire.begin() needs explicit SDA/SCL pins on this board.

#include <Wire.h>

#define XVF3800_ADDR 0x2C
#define GPO_SERVICER_RESID 20
#define GPO_SERVICER_RESID_DOA 18  // DOA_VALUE = resid 20 / cmd 18 (Seeed python_control command map)
#define DOA_READ_BYTES 4

bool readDoa(uint16_t &angle, bool &speech) {
  Wire.beginTransmission(XVF3800_ADDR);
  Wire.write((uint8_t)GPO_SERVICER_RESID);
  Wire.write((uint8_t)(GPO_SERVICER_RESID_DOA | 0x80));  // read command
  Wire.write((uint8_t)(DOA_READ_BYTES + 1));             // payload + status byte
  if (Wire.endTransmission(false) != 0) return false;

  uint8_t n = Wire.requestFrom((int)XVF3800_ADDR, DOA_READ_BYTES + 1);
  if (n < DOA_READ_BYTES + 1) return false;

  uint8_t status = Wire.read();
  uint8_t b0 = Wire.read();
  uint8_t b1 = Wire.read();
  uint8_t b2 = Wire.read();
  uint8_t b3 = Wire.read();
  (void)b3;
  if (status != 0) return false;

  angle = (uint16_t)b0 | ((uint16_t)b1 << 8);
  speech = (b2 != 0);
  return true;
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
}

void loop() {
  uint16_t angle;
  bool speech;
  if (readDoa(angle, speech)) {
    Serial.print("DOA:");
    Serial.print(angle);
    Serial.print(",VAD:");
    Serial.println(speech ? 1 : 0);
  }
  delay(100);
}
