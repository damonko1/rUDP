#!/usr/bin/env python3
"""
CMSC481 Project 1 - Reliable File Transfer over UDP
Student Template

Instructions:
1. Implement checkpoint 1: perform_handshake() method
2. Implement checkpoints 2 & 3: Sliding window ACK handling
3. Implement checkpoint 4: Packet loss recovery (timeout/retransmission)
4. Implement checkpoint 5: RTT estimation (extra credit)

Each checkpoint builds on the previous ones.
"""
import socket
import sys
import time
import random
import os
from packet import Packet, PACKET_TYPE

class Sender:
    def __init__(self, receiver_ip, receiver_port, window_size, input_file):
        self.receiver_addr = (receiver_ip, receiver_port)
        self.window_size = window_size
        self.input_file = input_file
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(0.01)
        self.alpha = 0.125
        self.estimated_rtt = 0.5
        self.sample_rtt = 0.5
        self.rtt_enabled = False
        self.packet_loss_recovery_enabled = False  # Automatically set by autograder
        self.log_file = None
        self.timeout_value = 0.5
        self.max_retries = 10

    def set_log_file(self, log_path):
        # Create directory if it doesn't exist
        log_dir = os.path.dirname(log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        self.log_file = open(log_path, 'w')

    def set_rtt_enabled(self, enabled):
        self.rtt_enabled = enabled

    def set_packet_loss_recovery_enabled(self, enabled):
        self.packet_loss_recovery_enabled = enabled

    def log(self, packet):
        if self.log_file:
            self.log_file.write(f"{packet.type} {packet.seq_num} {packet.length} {packet.checksum}\n")
            self.log_file.flush()

    def log_rtt(self, rtt_msg):
        if self.log_file and self.rtt_enabled:
            self.log_file.write(f"RTT {rtt_msg}\n")
            self.log_file.flush()

    def send_packet(self, packet):
        self.socket.sendto(packet.to_bytes(), self.receiver_addr)
        self.log(packet)

    def perform_handshake(self, handshake_packet, expected_seq):
        """
        Checkpoint 1: Connection Establishment (Handshake)

        TODO: Implement the handshake protocol
        - Send the handshake packet up to 10 times
        - Wait for ACK with matching sequence number
        - Return True if handshake succeeds, False otherwise
        - Use socket timeout to handle lost packets

        Parameters:
        - handshake_packet: The packet to send (START or END)
        - expected_seq: The sequence number to expect in the ACK

        Returns:
        - True if ACK with expected_seq received, False after 10 attempts
        """
        # raise NotImplementedError("Checkpoint 1: Connection Establishment not implemented")
        # YOUR CODE HERE (within 15 lines)
        # Hint: Use a loop to retry up to 10 times 
        for _ in range(10):
            self.send_packet(handshake_packet)
            try:
                data, _ = self.socket.recvfrom(1472)
                ack = Packet.from_bytes(data)
                if ack and ack.type == PACKET_TYPE['ACK'] and ack.seq_num == expected_seq:
                    self.log(ack)
                    return True
            except socket.timeout:
                continue
        return False
        # END OF YOUR CODE

    def transfer_file(self):
        random_seq = random.randint(1, 2**32 - 1)

        # Perform START handshake
        start_packet = Packet(PACKET_TYPE['START'], random_seq)
        if not self.perform_handshake(start_packet, random_seq):
            print("Failed to establish connection")
            return

        with open(self.input_file, 'rb') as f:
            file_data = f.read()

        packets = []
        seq = 0
        for i in range(0, len(file_data), 1456):
            chunk = file_data[i:i+1456]
            packets.append(Packet(PACKET_TYPE['DATA'], seq, chunk))
            seq += 1

        left = 0
        right = min(self.window_size, len(packets))
        window = packets[left:right]
        rtt_landmark_seq = 0
        rtt_start_time = None

        while left < len(packets):
            # Send all packets in current window
            for i, pkt in enumerate(window):
                self.send_packet(pkt)
                if self.rtt_enabled and i == 0 and rtt_start_time is None:
                    rtt_start_time = time.time()
                    rtt_landmark_seq = pkt.seq_num

            timeout_start = time.time()
            timeout_value = self.estimated_rtt * 2 if self.rtt_enabled else 0.5

            while True:
                # Calculate remaining time before timeout
                remaining = timeout_value - (time.time() - timeout_start)

                # Checkpoint 4: Packet Loss Recovery
                if self.packet_loss_recovery_enabled and remaining <= 0:
                    """
                    TODO: Implement timeout and retransmission
                    - Retransmit all packets in current window
                    - Reset timeout timer
                    - Continue to wait for ACKs
                    """
                    #raise NotImplementedError("Checkpoint 4: Packet Loss Recovery not implemented")

                    # YOUR CODE HERE (within 10 lines)
                    # retransmit all packets in window
                    for pkt in window:
                        self.send_packet(pkt)
                    # Reset timeout timer
                    timeout_start = time.time()
                    rtt_start_time = None
                    rtt_landmark_seq = 0
                    # continue waiting for ACKs
                    continue

                    # END OF YOUR CODE

                self.socket.settimeout(max(0.01, remaining))
                try:
                    data, _ = self.socket.recvfrom(1472)
                    ack = Packet.from_bytes(data)

                    if ack and ack.type == PACKET_TYPE['ACK']:
                        self.log(ack)

                        # Ignore ACKs for the START packet during data transfer
                        if ack.seq_num == random_seq:
                            continue

                        if self.rtt_enabled and rtt_start_time and ack.seq_num > rtt_landmark_seq:
                            """
                            Checkpoint 5: RTT Measurement and Estimation (Extra Credit)

                            TODO: Implement RTT estimation using exponential weighted moving average
                            - Calculate sample RTT from rtt_start_time to current time
                            - Update estimated RTT using: estimated_rtt = (1-alpha) * estimated_rtt + alpha * sample_rtt
                            - Log RTT measurements using self.log_rtt()
                            - Reset rtt_start_time to None after calculation
                            """
                            #raise NotImplementedError("Checkpoint 5: RTT Estimation not implemented")


                            # YOUR CODE HERE (within 10 lines)
                            # calc sample rtt
                            sample = time.time() - rtt_start_time
                            old_est = self.estimated_rtt
                            self.sample_rtt = sample
                            self.estimated_rtt = (1 - self.alpha) * self.estimated_rtt + self.alpha * sample
                            deviation = sample - self.estimated_rtt
                            change = self.estimated_rtt - old_est
                            rtt_start_time = None
                            rtt_landmark_seq = 0
                            
                            
                            # END OF YOUR CODE

                            self.log_rtt(f"Sample: {self.sample_rtt*1000:.2f}ms | Estimated: {self.estimated_rtt*1000:.2f}ms | Deviation: {deviation*1000:+.2f}ms | Change: {change*1000:+.2f}ms")
                            


                        """
                        Checkpoint 2 & 3: Handle ACK and Slide Window

                        TODO: When receiving an ACK with cumulative acknowledgment:
                        1. Check if the ACK advances our window (ack.seq_num > left)
                        2. If yes, update left, right, and window
                        3. Check if all packets are acknowledged
                        4. If not done, send the new window of packets

                        Key variables:
                        - left: First unacknowledged packet sequence number
                        - right: One past the last packet in window
                        - window: Current window of packets
                        - packets: All DATA packets to send
                        - ack.seq_num: Next expected packet (cumulative ACK)
                        """
                        if len(packets) == 0:  # Special case for checkpoint 1 (no data packets)
                            break

                        #raise NotImplementedError("Checkpoint 2 & 3: Sliding Window not implemented")

                        # YOUR CODE HERE 
                        # check if advances our window
                        if ack.seq_num > left:
                            
                            # update the left, right, and sliding window values
                            left = ack.seq_num
                            
                            # checks if all packets have been acked if left is passed length of packet
                            if left >= len(packets):
                                break 
                            right = min(left + self.window_size, len(packets))
                            window = packets[left:right] # from left ACK value to the right
                            
                            timeout_start = time.time()  # reset
                            rtt_start_time = None # reset
                            rtt_landmark_seq = 0 # reset
                            
                            break
                            
                        
                        # END OF YOUR CODE

                except socket.timeout:
                    pass

        # Perform END handshake
        end_packet = Packet(PACKET_TYPE['END'], random_seq)
        if not self.perform_handshake(end_packet, random_seq):
            print("Warning: Failed to properly close connection")

        if self.log_file:
            self.log_file.close()

def main():
    if len(sys.argv) < 5:
        print("Usage: ./rSender.py <receiver-IP> <receiver-port> <window-size> <input-file> [options]")
        print("Options:")
        print("  --log FILE          Write packet log to FILE")
        print("  --rtt               Enable RTT-based congestion control")
        print("  --loss-recovery     Enable packet loss recovery (checkpoint 4)")
        sys.exit(1)

    receiver_ip = sys.argv[1]
    receiver_port = int(sys.argv[2])
    window_size = int(sys.argv[3])
    input_file = sys.argv[4]

    sender = Sender(receiver_ip, receiver_port, window_size, input_file)

    i = 5
    while i < len(sys.argv):
        if sys.argv[i] == '--log' and i + 1 < len(sys.argv):
            sender.set_log_file(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == '--rtt':
            sender.set_rtt_enabled(True)
            i += 1
        elif sys.argv[i] == '--loss-recovery':
            sender.set_packet_loss_recovery_enabled(True)
            i += 1
        else:
            i += 1

    sender.transfer_file()

if __name__ == "__main__":
    main()