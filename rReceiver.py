#!/usr/bin/env python3
import socket
import sys
import os
import time
import random
from packet import Packet, PACKET_TYPE

class Receiver:
    def __init__(self, port, window_size, output_file):
        self.port = port
        self.window_size = window_size
        self.output_file = output_file

        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', port))
        self.data_packet_count = 0
        self.drop_every_nth = None
        self.base_delay_ms = 0
        self.jitter_ms = 0
        self.log_file = None

    def set_log_file(self, log_path):
        # Create directory if it doesn't exist
        log_dir = os.path.dirname(log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        self.log_file = open(log_path, 'w')

    def set_drop_rate(self, drop_rate):
        self.drop_every_nth = drop_rate if drop_rate > 0 else None

    def set_delay(self, delay_ms, jitter_ms=0):
        self.base_delay_ms = delay_ms
        self.jitter_ms = jitter_ms

    def log(self, packet):
        if self.log_file:
            self.log_file.write(f"{packet.type} {packet.seq_num} {packet.length} {packet.checksum}\n")
            self.log_file.flush()

    def simulate_delay(self):
        if self.base_delay_ms > 0:
            delay = self.base_delay_ms / 1000.0
            if self.jitter_ms > 0:
                jitter = random.uniform(-self.jitter_ms, self.jitter_ms) / 1000.0
                delay += jitter
            time.sleep(max(0, delay))

    def should_drop_packet(self, packet):
        if packet.type == PACKET_TYPE['DATA'] and self.drop_every_nth:
            self.data_packet_count += 1
            if self.data_packet_count % self.drop_every_nth == 0:
                return True
        return False

    def send_ack(self, seq_num, addr):
        self.simulate_delay()
        ack = Packet(PACKET_TYPE['ACK'], seq_num)
        self.socket.sendto(ack.to_bytes(), addr)
        self.log(ack)

    def handle_connection(self):
        expected_seq = 0
        buffer = {}
        output_file = None
        start_seq_num = None
        connection_active = False
        self.data_packet_count = 0

        while True:
            data, addr = self.socket.recvfrom(1472)
            packet = Packet.from_bytes(data)

            if not packet:
                continue

            self.log(packet)

            if packet.type == PACKET_TYPE['START']:
                if not connection_active:
                    connection_active = True
                    start_seq_num = packet.seq_num
                    expected_seq = 0
                    buffer = {}
                    output_file = open(self.output_file, 'wb')

                self.send_ack(packet.seq_num, addr)

            elif packet.type == PACKET_TYPE['DATA'] and connection_active:
                if not packet.is_valid():
                    continue

                if self.should_drop_packet(packet):
                    continue

                if packet.seq_num < expected_seq + self.window_size:
                    if packet.seq_num >= expected_seq:
                        buffer[packet.seq_num] = packet.data

                    while expected_seq in buffer:
                        output_file.write(buffer[expected_seq])
                        output_file.flush()  # Ensure data is written immediately
                        del buffer[expected_seq]
                        expected_seq += 1

                    self.send_ack(expected_seq, addr)

            elif packet.type == PACKET_TYPE['END'] and connection_active:
                if packet.seq_num == start_seq_num:
                    self.send_ack(packet.seq_num, addr)
                    output_file.close()
                    connection_active = False
                    return True

        return False

    def run(self):
        try:
            self.handle_connection()
        except KeyboardInterrupt:
            pass
        finally:
            if self.log_file:
                self.log_file.close()
            self.socket.close()

def main():
    if len(sys.argv) < 4:
        print("Usage: ./rReceiver.py <port> <window-size> <output-file> [options]")
        print("Options:")
        print("  --log FILE      Write packet log to FILE")
        print("  --drop N        Drop every Nth DATA packet")
        print("  --delay MS      Add MS milliseconds delay to ACKs")
        print("  --jitter MS     Add ±MS milliseconds jitter to delay")
        sys.exit(1)

    port = int(sys.argv[1])
    window_size = int(sys.argv[2])
    output_file = sys.argv[3]

    receiver = Receiver(port, window_size, output_file)

    i = 4
    while i < len(sys.argv):
        if sys.argv[i] == '--log' and i + 1 < len(sys.argv):
            receiver.set_log_file(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == '--drop' and i + 1 < len(sys.argv):
            receiver.set_drop_rate(int(sys.argv[i + 1]))
            i += 2
        elif sys.argv[i] == '--delay' and i + 1 < len(sys.argv):
            receiver.set_delay(int(sys.argv[i + 1]))
            i += 2
        elif sys.argv[i] == '--jitter' and i + 1 < len(sys.argv):
            receiver.jitter_ms = int(sys.argv[i + 1])
            i += 2
        else:
            i += 1

    receiver.run()

if __name__ == "__main__":
    main()