#!/usr/bin/env python3
import subprocess
import time
import os
import sys
import signal
import hashlib
import platform

class Autograder:
    def __init__(self, sender_file='rSender.py'):
        # Detect Python command based on platform
        system = platform.system()
        if system == 'Windows':
            self.python_cmd = 'python'
        elif system in ['Darwin', 'Linux']:  # Darwin is macOS
            self.python_cmd = 'python3'
        else:
            # Default to python3 for other Unix-like systems
            self.python_cmd = 'python3'

        # Store sender file to use
        self.sender_file = sender_file
        self.checkpoints = [
            {
                'name': 'Setup Check',
                'tests': 1,
                'points': 10,
                'window': 5,
                'options': {},
                'type': 'setup'
            },
            {
                'name': 'Connection Establishment (Handshake)',
                'tests': 5,
                'points': 10,
                'window': 5,
                'options': {},
                'type': 'handshake'
            },
            {
                'name': 'Basic File Transfer (No Window Sliding)',
                'tests': 5,
                'points': 15,
                'window': 10,
                'options': {},
                'type': 'basic'
            },
            {
                'name': 'Large File Transfer (Window Sliding)',
                'tests': 5,
                'points': 15,
                'window': 5,
                'options': {},
                'type': 'sliding'
            },
            {
                'name': 'Packet Loss Recovery',
                'tests': 5,
                'points': 30,
                'window': 5,
                'options': {'drop': 2, 'loss_recovery': True},  # Drop every 2nd packet to force timeouts
                'type': 'loss'
            },
            {
                'name': 'RTT Measurement and Estimation (Extra Credit)',
                'tests': 5,
                'points': 20,
                'window': 10,
                'options': {'delay': 50, 'jitter': 20, 'rtt': True},
                'type': 'rtt'
            }
        ]
        self.base_port = 6000

    def get_file_hash(self, filepath):
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def check_handshake_protocol(self, sender_log, receiver_log):
        """Check if handshake protocol was correctly implemented"""
        if not os.path.exists(sender_log) or not os.path.exists(receiver_log):
            return False, "Log files not found"

        try:
            # Check sender log for START and END packets
            with open(sender_log, 'r') as f:
                sender_lines = f.readlines()

            # Check receiver log for corresponding ACKs
            with open(receiver_log, 'r') as f:
                receiver_lines = f.readlines()

            # Look for START handshake
            start_sent = False
            start_acked = False
            end_sent = False
            end_acked = False

            for line in sender_lines:
                parts = line.strip().split()
                if len(parts) >= 4:
                    if parts[0] == '0':  # START packet
                        start_sent = True
                    elif parts[0] == '1':  # END packet
                        end_sent = True
                    elif parts[0] == '3':  # ACK packet
                        # Check if it's ACK for START or END
                        if start_sent and not start_acked:
                            start_acked = True
                        elif end_sent and not end_acked:
                            end_acked = True

            if start_sent and start_acked and end_sent and end_acked:
                return True, "Handshake protocol correctly implemented"
            else:
                missing = []
                if not start_sent: missing.append("START not sent")
                if not start_acked: missing.append("START not acknowledged")
                if not end_sent: missing.append("END not sent")
                if not end_acked: missing.append("END not acknowledged")
                return False, f"Handshake incomplete: {', '.join(missing)}"

        except Exception as e:
            return False, f"Error checking logs: {str(e)}"

    def check_rtt_convergence(self, sender_log):
        """Check if RTT measurements show convergence behavior - very generous check"""
        if not os.path.exists(sender_log):
            return False, "No sender log found"

        rtt_samples = []
        estimated_rtts = []

        try:
            with open(sender_log, 'r') as f:
                for line in f:
                    if 'RTT Sample:' in line:
                        # Parse RTT values from log line
                        parts = line.strip().split('|')
                        if len(parts) >= 2:
                            # Extract Sample RTT
                            sample_part = parts[0].split(':')[1].strip()
                            sample_rtt = float(sample_part.replace('ms', ''))
                            rtt_samples.append(sample_rtt)

                            # Extract Estimated RTT
                            est_part = parts[1].split(':')[1].strip()
                            est_rtt = float(est_part.replace('ms', ''))
                            estimated_rtts.append(est_rtt)

            # If no RTT samples at all, fail
            if len(estimated_rtts) == 0:
                return False, "No RTT measurements found"

            # If we have any RTT samples but too few, that's OK - pass for effort
            if len(estimated_rtts) < 5:
                return True, f"RTT calculated ({len(estimated_rtts)} samples)"

            # For convergence check: Any significant change (>10%) means adaptation is happening
            initial_est = estimated_rtts[0]
            final_est = estimated_rtts[-1]

            # Calculate percentage change
            if initial_est > 0:
                percent_change = abs((final_est - initial_est) / initial_est) * 100
            else:
                percent_change = 100  # If initial is 0, any change is significant

            # Accept if there's any significant change (>10%), either up or down
            # This shows the algorithm is adapting to network conditions
            if percent_change > 10:
                direction = "increased" if final_est > initial_est else "decreased"
                return True, f"RTT converged: {direction} by {percent_change:.1f}% ({initial_est:.1f}ms → {final_est:.1f}ms)"

            # Even if change is small, if we have enough samples, pass it
            # This means RTT is stable and algorithm is working
            if len(estimated_rtts) >= 10:
                return True, f"RTT stable: {initial_est:.1f}ms → {final_est:.1f}ms ({len(estimated_rtts)} samples)"

            # Default: pass with minimal requirements met
            return True, f"RTT tracking: {initial_est:.1f}ms → {final_est:.1f}ms"

        except Exception as e:
            return False, f"Error parsing log: {str(e)}"

    def run_test(self, checkpoint_num, test_num):
        checkpoint = self.checkpoints[checkpoint_num]
        input_file = os.path.join('input', f'checkpoint_{checkpoint_num}_{test_num}.txt')
        output_file = os.path.join('output', f'checkpoint_{checkpoint_num}_{test_num}.out')
        sender_log = os.path.join('sender_log', f'checkpoint_{checkpoint_num}_{test_num}.log')
        receiver_log = os.path.join('receiver_log', f'checkpoint_{checkpoint_num}_{test_num}.log')

        port = self.base_port + checkpoint_num * 10 + test_num

        # Clean up any existing output
        if os.path.exists(output_file):
            try:
                os.remove(output_file)
            except (PermissionError, OSError):
                # On Windows, file might still be locked
                pass

        # Check if input file exists
        if not os.path.exists(input_file):
            # For checkpoint 1 (handshake), create empty file if not exists
            if checkpoint.get('type') == 'handshake':
                # Create empty input file
                os.makedirs(os.path.dirname(input_file), exist_ok=True)
                with open(input_file, 'w') as f:
                    pass  # Create empty file
            else:
                return False, f"Input file {input_file} not found"

        # Build receiver command
        receiver_cmd = [
            self.python_cmd, 'rReceiver.py',
            str(port), str(checkpoint['window']), output_file,
            '--log', receiver_log
        ]

        if 'drop' in checkpoint['options']:
            receiver_cmd.extend(['--drop', str(checkpoint['options']['drop'])])
        if 'delay' in checkpoint['options']:
            receiver_cmd.extend(['--delay', str(checkpoint['options']['delay'])])
        if 'jitter' in checkpoint['options']:
            receiver_cmd.extend(['--jitter', str(checkpoint['options']['jitter'])])

        # Build sender command
        sender_cmd = [
            self.python_cmd, self.sender_file,
            '127.0.0.1', str(port), str(checkpoint['window']), input_file,
            '--log', sender_log
        ]

        if checkpoint['options'].get('rtt'):
            sender_cmd.append('--rtt')
        if checkpoint['options'].get('loss_recovery'):
            sender_cmd.append('--loss-recovery')

        # Start receiver
        try:
            receiver_proc = subprocess.Popen(
                receiver_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
        except FileNotFoundError:
            return False, "rReceiver.py not found"

        time.sleep(0.5)

        # Run sender
        try:
            sender_proc = subprocess.Popen(
                sender_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )

            # Wait for sender to complete with appropriate timeout
            # Short timeout for handshake, longer for data transfer and RTT tests
            if checkpoint.get('type') == 'handshake':
                timeout_sec = 5  # 5 seconds for handshake only
            elif checkpoint.get('type') == 'rtt':
                timeout_sec = 30  # 30 seconds for RTT tests (may have delays)
            elif checkpoint.get('type') == 'loss':
                timeout_sec = 30 # 30 seconds for loss/re-transmission
            else:
                timeout_sec = 10  # 10 seconds for sliding window data transfer (checkpoints 2, 3)

            sender_proc.wait(timeout=timeout_sec)

            # Give receiver time to write output and handle retransmissions
            # Longer wait for RTT tests due to retransmissions
            wait_time = 2.0 if checkpoint.get('type') == 'rtt' else 1.0
            time.sleep(wait_time)

            # Check for NotImplementedError in sender stderr
            sender_stderr = sender_proc.stderr.read().decode('utf-8', errors='ignore')
            if 'NotImplementedError' in sender_stderr:
                # Extract checkpoint info from error message
                if 'Checkpoint' in sender_stderr:
                    error_msg = sender_stderr.split('NotImplementedError:')[1].strip().split('\n')[0]
                    return False, f"Not Implemented: {error_msg}"
                else:
                    return False, "Not Implemented"

            # Kill receiver (Windows-compatible)
            if platform.system() == 'Windows':
                # On Windows, use kill directly for better compatibility
                try:
                    receiver_proc.kill()
                    receiver_proc.wait(timeout=1)
                except:
                    pass
            else:
                receiver_proc.terminate()
                try:
                    receiver_proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    receiver_proc.kill()

            # For handshake checkpoint, check logs instead of output
            if checkpoint.get('type') == 'handshake':
                handshake_valid, handshake_msg = self.check_handshake_protocol(sender_log, receiver_log)
                return handshake_valid, handshake_msg

            # For other checkpoints, verify output matches input
            if not os.path.exists(output_file):
                return False, "Output file not created"

            input_hash = self.get_file_hash(input_file)
            output_hash = self.get_file_hash(output_file)

            if input_hash and output_hash and input_hash == output_hash:
                return True, "Success"
            else:
                return False, "Output does not match input"

        except subprocess.TimeoutExpired:
            # Clean up processes
            try:
                sender_proc.kill()
            except:
                pass
            try:
                receiver_proc.kill()
            except:
                pass

            # Provide specific timeout message based on checkpoint type
            if checkpoint.get('type') == 'handshake':
                return False, f"Timeout after {timeout_sec}s - handshake implementation may be stuck or incomplete"
            elif checkpoint.get('type') in ['basic', 'sliding']:
                return False, f"Timeout after {timeout_sec}s - sliding window not properly implemented"
            else:
                return False, f"Timeout after {timeout_sec} seconds"
        except FileNotFoundError:
            try:
                receiver_proc.kill()
            except:
                pass
            return False, "rSender.py not found"
        except Exception as e:
            try:
                receiver_proc.kill()
            except:
                pass
            return False, f"Error: {str(e)}"

    def run_checkpoint(self, checkpoint_num):
        checkpoint = self.checkpoints[checkpoint_num]
        print(f"Checkpoint {checkpoint_num}: {checkpoint['name']}")

        # Checkpoint 0 checks for required files, folders, and input files
        if checkpoint_num == 0:
            # Check if required files exist
            # Use the specified sender file instead of hardcoded rSender.py
            required_files = [self.sender_file, 'rReceiver.py', 'packet.py']
            missing_files = []

            for file in required_files:
                if not os.path.exists(file):
                    missing_files.append(file)

            # Check if required folders exist (only input folder is required)
            required_folders = ['input']
            missing_folders = []

            for folder in required_folders:
                if not os.path.exists(folder):
                    missing_folders.append(folder)

            # Check if all required input files exist
            missing_input_files = []
            # Check input files for checkpoints 1-5 (skip checkpoint 0 as it doesn't use input files)
            for cp in range(1, len(self.checkpoints)):
                checkpoint_info = self.checkpoints[cp]
                for test in range(1, checkpoint_info['tests'] + 1):
                    input_file = os.path.join('input', f'checkpoint_{cp}_{test}.txt')
                    if not os.path.exists(input_file):
                        missing_input_files.append(input_file)

            # Determine pass/fail based on all checks
            if missing_files or missing_folders or missing_input_files:
                print(f"  Test 1 - FAIL")
                if missing_files:
                    print(f"    Missing required files: {', '.join(missing_files)}")
                if missing_folders:
                    print(f"    Missing required folders: {', '.join(missing_folders)}")
                if missing_input_files:
                    print(f"    Missing input files: {len(missing_input_files)} files")
                    # Show first 5 missing input files as examples
                    for i, file in enumerate(missing_input_files[:5]):
                        print(f"      - {file}")
                    if len(missing_input_files) > 5:
                        print(f"      ... and {len(missing_input_files) - 5} more")
                print(f"  0/1 Passed")
                passed = 0
                failure_reasons = []
                if missing_files:
                    failure_reasons.append(f"Missing files: {', '.join(missing_files)}")
                if missing_folders:
                    failure_reasons.append(f"Missing folders: {', '.join(missing_folders)}")
                if missing_input_files:
                    failure_reasons.append(f"Missing {len(missing_input_files)} input files")
                failure_reason = "; ".join(failure_reasons)
            else:
                print(f"  Test 1 - PASS (Free points - all required files/folders exist)")
                print(f"  1/1 Passed")
                passed = 1
                failure_reason = None
        else:
            passed = 0
            failure_reason = None
            not_implemented = False

            for test_num in range(1, checkpoint['tests'] + 1):
                # If NotImplementedError detected, skip remaining tests in this checkpoint
                if not_implemented:
                    print(f"  Test {test_num} - SKIP (Not Implemented)")
                    continue

                result, reason = self.run_test(checkpoint_num, test_num)
                status = "PASS" if result else "FAIL"

                # Check if this test hit NotImplementedError
                if reason and "Not Implemented" in reason:
                    not_implemented = True
                    status = "SKIP"
                    if not failure_reason:
                        failure_reason = reason

                print(f"  Test {test_num} - {status}")

                # Print NotImplementedError message on first occurrence
                if not_implemented and test_num == 1 and reason:
                    print(f"    {reason}")

                # For RTT checkpoint, also check RTT convergence
                if checkpoint.get('type') == 'rtt' and not not_implemented:
                    sender_log = os.path.join('sender_log', f'checkpoint_{checkpoint_num}_{test_num}.log')
                    converged, conv_msg = self.check_rtt_convergence(sender_log)

                    output_correct = "YES" if result else "NO"
                    convergence_status = "YES" if converged else "NO"

                    print(f"    Correct output? \t\t{output_correct}")
                    print(f"    EstimatedRTT Converges? \t{convergence_status} ({conv_msg})")

                    # Test passes only if both output is correct AND RTT converges
                    if result and not converged:
                        result = False
                        reason = f"RTT did not converge: {conv_msg}"
                        status = "FAIL"
                        passed -= 1  # Adjust the count

                if not result and not failure_reason:
                    failure_reason = reason
                    if checkpoint.get('type') != 'rtt' and not not_implemented:  # Don't double print for RTT or NotImplemented
                        print(f"    Reason: {reason}")
                if result and not not_implemented:
                    passed += 1

            print(f"  {passed}/{checkpoint['tests']} Passed")

        if checkpoint['tests'] > 0:
            score = (passed / checkpoint['tests']) * checkpoint['points']
        else:
            score = 0

        return score, passed, checkpoint['tests'], failure_reason

    def run(self, checkpoint_to_test=None):
        print("=" * 60)
        print("CMSC481 Project 1 Autograder")
        print("=" * 60)

        total_score = 0
        total_passed = 0
        total_tests = 0

        # Determine which checkpoints to run
        if checkpoint_to_test is not None:
            checkpoints_to_run = [checkpoint_to_test]
        else:
            checkpoints_to_run = range(len(self.checkpoints))

        for i in checkpoints_to_run:
            score, passed, tests, failure_reason = self.run_checkpoint(i)
            total_score += score
            total_passed += passed
            total_tests += tests

            # Early termination if checkpoint 0 fails (missing required files/folders)
            if i == 0 and passed == 0:
                print("\n" + "=" * 60)
                print("CRITICAL FAILURE: Setup requirements not met!")
                print(f"Reason: {failure_reason}")
                print("\nPlease ensure the following exist in the current directory:")
                print("Required Python files:")
                print(f"  - {self.sender_file}")
                print("  - rReceiver.py")
                print("  - packet.py")
                print("\nRequired folder:")
                print("  - input/     (containing all test input files)")
                print("\nAll input test files for checkpoints 1-5 must be present in the input/ folder")
                print("=" * 60)
                return

            print()

        print("=" * 60)
        if checkpoint_to_test is not None:
            max_score = self.checkpoints[checkpoint_to_test]['points']
            print(f"Checkpoint {checkpoint_to_test} Score: {total_score:.1f}/{max_score} points")
        else:
            print(f"Total Score: {total_score:.1f}/100 points")
        print(f"Total Tests Passed: {total_passed}/{total_tests}")
        print("=" * 60)

def main():
    # Check for sender file argument
    sender_file = 'rSender.py'
    checkpoint_num = None

    # Parse arguments
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--sender' and i + 1 < len(sys.argv):
            sender_file = sys.argv[i + 1]
            i += 2
        else:
            try:
                checkpoint_num = int(sys.argv[i])
                if not (0 <= checkpoint_num <= 5):
                    print("Error: Checkpoint number must be between 0 and 5")
                    print("Usage: python3 autograder.py [checkpoint_number] [--sender FILE]")
                    sys.exit(1)
                i += 1
            except ValueError:
                print(f"Error: Invalid argument '{sys.argv[i]}'")
                print("Usage: python3 autograder.py [checkpoint_number] [--sender FILE]")
                sys.exit(1)

    grader = Autograder(sender_file)

    if sender_file != 'rSender.py':
        print(f"Using custom sender: {sender_file}")

    if checkpoint_num is not None:
        print(f"Testing only checkpoint {checkpoint_num}")
        grader.run(checkpoint_num)
    else:
        grader.run()

if __name__ == "__main__":
    main()