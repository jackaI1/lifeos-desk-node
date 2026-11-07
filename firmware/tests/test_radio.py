import binascii
import struct
import unittest
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location("check_radio", Path(__file__).parents[1]/"tools/check_radio.py")
radio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(radio)
decode, wifi = radio.decode, radio.wifi


class RadioTest(unittest.TestCase):
    def test_roundtrip_and_corruption(self):
        payload=struct.pack('<BBiII',1,0,-1000,50000,12)
        payload+=struct.pack('<H',binascii.crc_hqx(payload,0xffff))
        self.assertEqual(decode(payload),dict(sequence=12,temperature_mc=-1000,humidity_mpermil=50000))
        for bad in [payload[:-1], payload+b'x', b'\x02'+payload[1:], b'x'*16]:
            with self.assertRaises(ValueError): decode(bad)
    def test_rssi_schema(self):
        self.assertEqual(wifi('I desk_net: WIFI connected rssi=-65 attempts=3')['rssi_dbm'],-65)
        for line in ['WIFI connected rssi=2 attempts=1','WIFI connected rssi=-80 attempts=99','dropped']:
            with self.assertRaises(ValueError): wifi(line)
