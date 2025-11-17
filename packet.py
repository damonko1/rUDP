#!/usr/bin/env python3
import struct
import zlib

PACKET_TYPE = {'START': 0, 'END': 1, 'DATA': 2, 'ACK': 3}

class Packet:
    def __init__(self, pkt_type, seq_num, data=b''):
        self.type = pkt_type
        self.seq_num = seq_num
        self.data = data
        self.length = len(data)
        self.checksum = zlib.crc32(data) if data else 0

    @classmethod
    def from_bytes(cls, data):
        if len(data) < 16:
            return None

        header = struct.unpack('!IIII', data[:16])
        pkt = cls(header[0], header[1])
        pkt.length = header[2]
        pkt.checksum = header[3]

        if pkt.length > 0 and len(data) >= 16 + pkt.length:
            pkt.data = data[16:16 + pkt.length]

        return pkt

    def to_bytes(self):
        header = struct.pack('!IIII', self.type, self.seq_num, self.length, self.checksum)
        return header + self.data

    def is_valid(self):
        if self.type == PACKET_TYPE['DATA']:
            return zlib.crc32(self.data) == self.checksum
        return self.checksum == 0