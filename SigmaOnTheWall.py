import argparse
import csv
import json
import logging
import socket
import statistics
import struct
import subprocess
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from queue import Queue

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Protocol(Enum):
    HTTP = 'http'
    HTTPS = 'https'
    ICMP = 'icmp'
    IGMP = 'igmp'
    GRE = 'gre'
    IPIP = 'ipip'
    TCP = 'tcp'
    UDP = 'udp'
    SCTP = 'sctp'
    DCCP = 'dccp'


class DiscordNotifier:
    
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url
        self.queue = Queue()
        self.worker_thread = None
        
        if self.webhook_url:
            self.worker_thread = threading.Thread(target=self._worker, daemon=False)
            self.worker_thread.start()
    
    def _worker(self):
        while True:
            task = self.queue.get()
            if task is None:
                break
            
            payload, retries = task
            for attempt in range(retries):
                try:
                    response = requests.post(self.webhook_url, json=payload, timeout=10)
                    response.raise_for_status()
                    break
                except Exception as e:
                    if attempt < retries - 1:
                        time.sleep(2 ** attempt)
                    else:
                        logger.warning(f"Failed to send Discord notification after {retries} attempts: {e}")
    
    def notify_test_start(self, url: str, threads: int, duration: int, method: str, rps: float):
        if not self.webhook_url:
            return
        
        payload = {
            'embeds': [{
                'title': 'Stress Test Started',
                'color': 3447003,
                'fields': [
                    {'name': 'Target', 'value': url, 'inline': False},
                    {'name': 'Threads', 'value': str(threads), 'inline': True},
                    {'name': 'Duration', 'value': f"{duration}s", 'inline': True},
                    {'name': 'Method', 'value': method, 'inline': True},
                    {'name': 'RPS', 'value': str(rps) if rps > 0 else 'Unlimited', 'inline': True}
                ]
            }]
        }
        self.queue.put((payload, 3))
    
    def notify_live_progress(self, total_requests: int, successful_requests: int,
                            failed_requests: int, rps: float, avg_latency: float,
                            success_rate: float, elapsed_time: float):
        if not self.webhook_url:
            return
        
        payload = {
            'embeds': [{
                'title': 'Live Progress Update',
                'color': 3447003,
                'fields': [
                    {'name': 'Elapsed Time', 'value': f"{elapsed_time:.1f}s", 'inline': True},
                    {'name': 'Total Requests', 'value': str(total_requests), 'inline': True},
                    {'name': 'Successful', 'value': str(successful_requests), 'inline': True},
                    {'name': 'Failed', 'value': str(failed_requests), 'inline': True},
                    {'name': 'RPS', 'value': f"{rps:.2f}", 'inline': True},
                    {'name': 'Avg Latency', 'value': f"{avg_latency*1000:.2f}ms", 'inline': True},
                    {'name': 'Success Rate', 'value': f"{success_rate:.2f}%", 'inline': True}
                ]
            }]
        }
        self.queue.put((payload, 2))
    
    def notify_test_complete(self, results: Dict):
        if not self.webhook_url:
            return
        
        payload = {
            'embeds': [{
                'title': 'Stress Test Complete',
                'color': 3066993,
                'fields': [
                    {'name': 'Total Requests', 'value': str(results['total_requests']), 'inline': True},
                    {'name': 'Successful', 'value': str(results['successful_requests']), 'inline': True},
                    {'name': 'Failed', 'value': str(results['failed_requests']), 'inline': True},
                    {'name': 'Success Rate', 'value': f"{results['success_rate']:.2f}%", 'inline': True},
                    {'name': 'RPS', 'value': f"{results['rps']:.2f}", 'inline': True},
                    {'name': 'Duration', 'value': f"{results['duration']:.2f}s", 'inline': True},
                    {'name': 'Avg Latency', 'value': f"{results['avg_latency']*1000:.2f}ms", 'inline': True},
                    {'name': 'P95 Latency', 'value': f"{results['p95_latency']*1000:.2f}ms", 'inline': True},
                    {'name': 'P99 Latency', 'value': f"{results['p99_latency']*1000:.2f}ms", 'inline': True}
                ]
            }]
        }
        self.queue.put((payload, 3))
    
    def notify_test_interrupted(self, url: str):
        if not self.webhook_url:
            return
        
        payload = {
            'embeds': [{
                'title': 'Stress Test Interrupted',
                'color': 15158332,
                'fields': [
                    {'name': 'Target', 'value': url, 'inline': False}
                ]
            }]
        }
        self.queue.put((payload, 2))
    
    def notify_test_error(self, url: str, error: str):
        if not self.webhook_url:
            return
        
        payload = {
            'embeds': [{
                'title': 'Stress Test Error',
                'color': 15158332,
                'fields': [
                    {'name': 'Target', 'value': url, 'inline': False},
                    {'name': 'Error', 'value': error[:256], 'inline': False}
                ]
            }]
        }
        self.queue.put((payload, 3))
    
    def shutdown(self):
        if self.worker_thread:
            self.queue.put(None)
            self.worker_thread.join(timeout=10)


class ProtocolHandler:
    
    def __init__(self, target: str, timeout: int = 10):
        self.target = target
        self.timeout = timeout
        self.parsed_url = None
        
        try:
            self.parsed_url = urlparse(target if target.startswith(('http://', 'https://')) else f'http://{target}')
        except Exception:
            pass
    
    def execute(self) -> Optional[float]:
        raise NotImplementedError
    
    def close(self):
        pass


class HTTPHandler(ProtocolHandler):
    
    def __init__(self, target: str, timeout: int = 10, method: str = 'GET',
                 headers: Optional[Dict] = None, data: Optional[str] = None,
                 json_data: Optional[str] = None, auth: Optional[Tuple] = None,
                 proxy: Optional[Dict] = None, verify_ssl: bool = True,
                 response_check: Optional[List[int]] = None, cookies: Optional[Dict] = None):
        super().__init__(target, timeout)
        self.method = method
        self.headers = headers or {}
        self.data = data
        self.json_data = json_data
        self.auth = auth
        self.proxy = proxy
        self.verify_ssl = verify_ssl
        self.response_check = response_check or [200]
        self.cookies = cookies
    
    def execute(self) -> Optional[float]:
        try:
            url = self.target if self.target.startswith(('http://', 'https://')) else f'http://{self.target}'
            
            start_time = time.time()
            
            if self.json_data:
                response = requests.request(
                    method=self.method,
                    url=url,
                    json=json.loads(self.json_data),
                    headers=self.headers,
                    auth=self.auth,
                    proxies=self.proxy,
                    verify=self.verify_ssl,
                    timeout=self.timeout,
                    cookies=self.cookies,
                    allow_redirects=False
                )
            else:
                response = requests.request(
                    method=self.method,
                    url=url,
                    data=self.data,
                    headers=self.headers,
                    auth=self.auth,
                    proxies=self.proxy,
                    verify=self.verify_ssl,
                    timeout=self.timeout,
                    cookies=self.cookies,
                    allow_redirects=False
                )
            
            elapsed_time = time.time() - start_time
            
            if response.status_code not in self.response_check:
                logger.debug(f"HTTP {response.status_code} not in expected codes {self.response_check}")
                return None
            
            return elapsed_time
        
        except requests.exceptions.Timeout:
            logger.debug(f"HTTP request timeout after {self.timeout}s")
            return None
        except requests.exceptions.RequestException as e:
            logger.debug(f"HTTP request failed: {e}")
            return None
        except Exception as e:
            logger.debug(f"HTTP request failed: {e}")
            return None


class ICMPHandler(ProtocolHandler):
    
    def execute(self) -> Optional[float]:
        try:
            if sys.platform == 'win32':
                cmd = ['ping', '-n', '1', '-w', str(self.timeout * 1000), self.target]
            else:
                cmd = ['ping', '-c', '1', '-W', str(self.timeout * 1000), self.target]
            
            start_time = time.time()
            result = subprocess.run(cmd, capture_output=True, timeout=self.timeout + 1)
            elapsed_time = time.time() - start_time
            
            if result.returncode == 0:
                return elapsed_time
            else:
                return None
        
        except subprocess.TimeoutExpired:
            logger.debug(f"ICMP ping timeout after {self.timeout}s")
            return None
        except Exception as e:
            logger.debug(f"ICMP ping failed: {e}")
            return None


class IGMPHandler(ProtocolHandler):
    
    def __init__(self, target: str, timeout: int = 10, port: int = 5000):
        super().__init__(target, timeout)
        self.port = port
    
    def execute(self) -> Optional[float]:
        try:
            start_time = time.time()
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            
            mreq = struct.pack('4sL', socket.inet_aton(self.target), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            
            sock.sendto(b'IGMP_TEST', (self.target, self.port))
            sock.close()
            
            elapsed_time = time.time() - start_time
            return elapsed_time
        
        except OSError as e:
            logger.debug(f"IGMP request failed: {e}")
            return None
        except Exception as e:
            logger.debug(f"IGMP request failed: {e}")
            return None


class GREHandler(ProtocolHandler):
    
    def execute(self) -> Optional[float]:
        try:
            start_time = time.time()
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, 47)
            sock.settimeout(self.timeout)
            
            sock.sendto(b'GRE_TEST', (self.target, 0))
            sock.close()
            
            elapsed_time = time.time() - start_time
            return elapsed_time
        
        except (AttributeError, OSError) as e:
            logger.debug(f"GRE request failed (requires root): {e}")
            return None
        except Exception as e:
            logger.debug(f"GRE request failed: {e}")
            return None


class IPIPHandler(ProtocolHandler):
    
    def execute(self) -> Optional[float]:
        try:
            start_time = time.time()
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, 4)
            sock.settimeout(self.timeout)
            
            sock.sendto(b'IPIP_TEST', (self.target, 0))
            sock.close()
            
            elapsed_time = time.time() - start_time
            return elapsed_time
        
        except (AttributeError, OSError) as e:
            logger.debug(f"IPIP request failed (requires root): {e}")
            return None
        except Exception as e:
            logger.debug(f"IPIP request failed: {e}")
            return None


class TCPHandler(ProtocolHandler):
    
    def __init__(self, target: str, timeout: int = 10, port: int = 80):
        super().__init__(target, timeout)
        self.port = port
        if self.parsed_url:
            self.host = self.parsed_url.hostname or self.parsed_url.netloc
            self.port = self.parsed_url.port or port
        else:
            self.host = target
    
    def execute(self) -> Optional[float]:
        try:
            start_time = time.time()
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.host, self.port))
            sock.close()
            
            elapsed_time = time.time() - start_time
            return elapsed_time
        
        except socket.timeout:
            logger.debug(f"TCP connection timeout after {self.timeout}s")
            return None
        except OSError as e:
            logger.debug(f"TCP connection failed: {e}")
            return None
        except Exception as e:
            logger.debug(f"TCP connection failed: {e}")
            return None


class UDPHandler(ProtocolHandler):
    
    def __init__(self, target: str, timeout: int = 10, port: int = 53):
        super().__init__(target, timeout)
        self.port = port
        if self.parsed_url:
            self.host = self.parsed_url.hostname or self.parsed_url.netloc
            self.port = self.parsed_url.port or port
        else:
            self.host = target
    
    def execute(self) -> Optional[float]:
        try:
            start_time = time.time()
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            sock.sendto(b'UDP_TEST', (self.host, self.port))
            sock.close()
            
            elapsed_time = time.time() - start_time
            return elapsed_time
        
        except socket.timeout:
            logger.debug(f"UDP request timeout after {self.timeout}s")
            return None
        except OSError as e:
            logger.debug(f"UDP request failed: {e}")
            return None
        except Exception as e:
            logger.debug(f"UDP request failed: {e}")
            return None


class SCTPHandler(ProtocolHandler):
    
    def __init__(self, target: str, timeout: int = 10, port: int = 132):
        super().__init__(target, timeout)
        self.port = port
        if self.parsed_url:
            self.host = self.parsed_url.hostname or self.parsed_url.netloc
            self.port = self.parsed_url.port or port
        else:
            self.host = target
    
    def execute(self) -> Optional[float]:
        try:

            start_time = time.time()
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, 132)
            sock.settimeout(self.timeout)
            sock.sendto(b'SCTP_TEST', (self.host, 0))
            sock.close()
            
            elapsed_time = time.time() - start_time
            return elapsed_time
        
        except (AttributeError, OSError) as e:
            logger.debug(f"SCTP request failed: {e}")
            return None
        except Exception as e:
            logger.debug(f"SCTP request failed: {e}")
            return None


class DCCPHandler(ProtocolHandler):
    
    def __init__(self, target: str, timeout: int = 10, port: int = 33):
        super().__init__(target, timeout)
        self.port = port
        if self.parsed_url:
            self.host = self.parsed_url.hostname or self.parsed_url.netloc
            self.port = self.parsed_url.port or port
        else:
            self.host = target
    
    def execute(self) -> Optional[float]:
        try:
            start_time = time.time()
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, 33)
            sock.settimeout(self.timeout)
            sock.sendto(b'DCCP_TEST', (self.host, 0))
            sock.close()
            
            elapsed_time = time.time() - start_time
            return elapsed_time
        
        except (AttributeError, OSError) as e:
            logger.debug(f"DCCP request failed: {e}")
            return None
        except Exception as e:
            logger.debug(f"DCCP request failed: {e}")
            return None


class ProtocolHandlerFactory:
    
    @staticmethod
    def create(protocol: Protocol, target: str, timeout: int = 10, **kwargs) -> ProtocolHandler:
        if protocol == Protocol.HTTP or protocol == Protocol.HTTPS:
            return HTTPHandler(target, timeout, **kwargs)
        elif protocol == Protocol.ICMP:
            return ICMPHandler(target, timeout)
        elif protocol == Protocol.IGMP:
            return IGMPHandler(target, timeout, **kwargs)
        elif protocol == Protocol.GRE:
            return GREHandler(target, timeout)
        elif protocol == Protocol.IPIP:
            return IPIPHandler(target, timeout)
        elif protocol == Protocol.TCP:
            return TCPHandler(target, timeout, **kwargs)
        elif protocol == Protocol.UDP:
            return UDPHandler(target, timeout, **kwargs)
        elif protocol == Protocol.SCTP:
            return SCTPHandler(target, timeout, **kwargs)
        elif protocol == Protocol.DCCP:
            return DCCPHandler(target, timeout, **kwargs)
        else:
            raise ValueError(f"Unknown protocol: {protocol}")


class AdvancedStressTest:
    
    def __init__(self, target: str, protocol: Protocol = Protocol.HTTP, threads: int = 10,
                 duration: int = 60, timeout: int = 10, rps: float = 0, method: str = 'GET',
                 headers: Optional[Dict] = None, data: Optional[str] = None,
                 json_data: Optional[str] = None, auth: Optional[Tuple] = None,
                 proxy: Optional[Dict] = None, verify_ssl: bool = True,
                 response_check: Optional[List[int]] = None, cookies: Optional[Dict] = None,
                 discord_webhook: Optional[str] = None):
        self.target = target
        self.protocol = protocol
        self.threads = threads
        self.duration = duration
        self.timeout = timeout
        self.rps = rps
        self.method = method
        self.headers = headers
        self.data = data
        self.json_data = json_data
        self.auth = auth
        self.proxy = proxy
        self.verify_ssl = verify_ssl
        self.response_check = response_check
        self.cookies = cookies
        
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.latencies = []
        self.error_samples = []
        self.status_codes = defaultdict(int)
        
        self.start_time = None
        self.end_time = None
        
        self.notifier = DiscordNotifier(discord_webhook)
    
    def _worker(self, worker_id: int):
        request_count = 0
        min_interval = 1.0 / self.rps if self.rps > 0 else 0
        last_request_time = time.time()
        
        while not self.stop_event.is_set():
            try:
                if self.rps > 0:
                    elapsed_since_last = time.time() - last_request_time
                    if elapsed_since_last < min_interval:
                        time.sleep(min_interval - elapsed_since_last)
                
                handler = ProtocolHandlerFactory.create(
                    self.protocol, self.target, self.timeout,
                    method=self.method, headers=self.headers, data=self.data,
                    json_data=self.json_data, auth=self.auth, proxy=self.proxy,
                    verify_ssl=self.verify_ssl, response_check=self.response_check,
                    cookies=self.cookies
                )
                
                last_request_time = time.time()
                latency = handler.execute()
                handler.close()
                
                with self.lock:
                    self.total_requests += 1
                    
                    if latency is not None:
                        self.successful_requests += 1
                        self.latencies.append(latency)
                        if self.protocol not in (Protocol.HTTP, Protocol.HTTPS):
                            self.status_codes[0] += 1
                    else:
                        self.failed_requests += 1
                        if len(self.error_samples) < 10:
                            self.error_samples.append({
                                'worker_id': worker_id,
                                'timestamp': datetime.now().isoformat(),
                                'error': 'Request failed'
                            })
                
                request_count += 1
            
            except Exception as e:
                logger.debug(f"Worker {worker_id} encountered error: {e}")
                with self.lock:
                    self.failed_requests += 1
                    if len(self.error_samples) < 10:
                        self.error_samples.append({
                            'worker_id': worker_id,
                            'timestamp': datetime.now().isoformat(),
                            'error': str(e)[:100]
                        })
    
    def _progress_reporter(self):
        while not self.stop_event.is_set():
            time.sleep(5)
            
            with self.lock:
                elapsed_time = time.time() - self.start_time
                
                if self.total_requests > 0:
                    rps = self.total_requests / elapsed_time
                    success_rate = (self.successful_requests / self.total_requests) * 100
                    avg_latency = statistics.mean(self.latencies) if self.latencies else 0
                    
                    self.notifier.notify_live_progress(
                        self.total_requests, self.successful_requests, self.failed_requests,
                        rps, avg_latency, success_rate, elapsed_time
                    )
    
    def run(self):
        try:
            self.start_time = time.time()
            
            self.notifier.notify_test_start(self.target, self.threads, self.duration,
                                           self.method, self.rps)
            
            worker_threads = []
            for i in range(self.threads):
                t = threading.Thread(target=self._worker, args=(i,), daemon=False)
                t.start()
                worker_threads.append(t)
            
            progress_thread = threading.Thread(target=self._progress_reporter, daemon=False)
            progress_thread.start()
            
            time.sleep(self.duration)
            self.stop_event.set()
            
            for t in worker_threads:
                t.join(timeout=5)
                if t.is_alive():
                    logger.warning("Worker thread did not terminate within timeout")
            
            progress_thread.join(timeout=5)
            
            self.end_time = time.time()
            
        except KeyboardInterrupt:
            logger.info("Test interrupted by user")
            self.stop_event.set()
            
            for t in worker_threads:
                t.join(timeout=5)
            
            progress_thread.join(timeout=5)
            
            self.notifier.notify_test_interrupted(self.target)
            self.notifier.shutdown()
            sys.exit(1)
    
    def get_results(self) -> Dict:
        with self.lock:
            latencies = self.latencies.copy()
            total_requests = self.total_requests
            successful_requests = self.successful_requests
            failed_requests = self.failed_requests
            status_codes = dict(self.status_codes)
            error_samples = self.error_samples.copy()
        
        duration = self.end_time - self.start_time if self.end_time else 0
        rps = total_requests / duration if duration > 0 else 0
        success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0
        
        if latencies:
            sorted_latencies = sorted(latencies)
            min_latency = sorted_latencies[0]
            max_latency = sorted_latencies[-1]
            avg_latency = statistics.mean(latencies)
            median_latency = statistics.median(latencies)
            stdev_latency = statistics.stdev(latencies) if len(latencies) > 1 else 0
            
            p95_index = int(len(sorted_latencies) * 0.95) - 1
            p95_index = max(0, min(p95_index, len(sorted_latencies) - 1))
            p95_latency = sorted_latencies[p95_index]
            
            p99_index = int(len(sorted_latencies) * 0.99) - 1
            p99_index = max(0, min(p99_index, len(sorted_latencies) - 1))
            p99_latency = sorted_latencies[p99_index]
        else:
            min_latency = max_latency = avg_latency = median_latency = stdev_latency = 0
            p95_latency = p99_latency = 0
        
        results = {
            'target': self.target,
            'protocol': self.protocol.value,
            'duration': duration,
            'total_requests': total_requests,
            'successful_requests': successful_requests,
            'failed_requests': failed_requests,
            'success_rate': success_rate,
            'rps': rps,
            'min_latency': min_latency,
            'max_latency': max_latency,
            'avg_latency': avg_latency,
            'median_latency': median_latency,
            'stdev_latency': stdev_latency,
            'p95_latency': p95_latency,
            'p99_latency': p99_latency,
            'status_codes': status_codes,
            'error_samples': error_samples,
            'latency_distribution': self._get_latency_distribution(sorted_latencies if latencies else [])
        }
        
        return results
    
    def _get_latency_distribution(self, sorted_latencies: List[float]) -> Dict:
        buckets = {
            '0-50ms': 0,
            '50-100ms': 0,
            '100-200ms': 0,
            '200-500ms': 0,
            '500ms-1s': 0,
            '1s+': 0
        }
        
        for latency in sorted_latencies:
            latency_ms = latency * 1000
            if latency_ms < 50:
                buckets['0-50ms'] += 1
            elif latency_ms < 100:
                buckets['50-100ms'] += 1
            elif latency_ms < 200:
                buckets['100-200ms'] += 1
            elif latency_ms < 500:
                buckets['200-500ms'] += 1
            elif latency_ms < 1000:
                buckets['500ms-1s'] += 1
            else:
                buckets['1s+'] += 1
        
        return buckets
    
    def export_results(self, filename: str, format: str = 'json'):
        results = self.get_results()
        
        if format == 'json':
            import os
            if os.path.exists(filename):
                logger.warning(f"File {filename} already exists. It will be overwritten.")
            
            with open(filename, 'w') as f:
                json.dump(results, f, indent=2)
            logger.info(f"Results exported to {filename}")
        
        elif format == 'csv':
            import os
            if os.path.exists(filename):
                logger.warning(f"File {filename} already exists. It will be overwritten.")
            
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Metric', 'Value'])
                writer.writerow(['Target', results['target']])
                writer.writerow(['Protocol', results['protocol']])
                writer.writerow(['Duration', f"{results['duration']:.2f}s"])
                writer.writerow(['Total Requests', results['total_requests']])
                writer.writerow(['Successful Requests', results['successful_requests']])
                writer.writerow(['Failed Requests', results['failed_requests']])
                writer.writerow(['Success Rate', f"{results['success_rate']:.2f}%"])
                writer.writerow(['RPS', f"{results['rps']:.2f}"])
                writer.writerow(['Min Latency', f"{results['min_latency']*1000:.2f}ms"])
                writer.writerow(['Max Latency', f"{results['max_latency']*1000:.2f}ms"])
                writer.writerow(['Avg Latency', f"{results['avg_latency']*1000:.2f}ms"])
                writer.writerow(['Median Latency', f"{results['median_latency']*1000:.2f}ms"])
                writer.writerow(['Stdev Latency', f"{results['stdev_latency']*1000:.2f}ms"])
                writer.writerow(['P95 Latency', f"{results['p95_latency']*1000:.2f}ms"])
                writer.writerow(['P99 Latency', f"{results['p99_latency']*1000:.2f}ms"])
            logger.info(f"Results exported to {filename}")
        
        else:
            logger.error(f"Unknown export format: {format}")
    
    def shutdown(self):
        self.notifier.shutdown()


def main():
    parser = argparse.ArgumentParser(description='Advanced Internet Stress Testing Tool')
    
    parser.add_argument('target', help='Target URL or hostname')
    parser.add_argument('-p', '--protocol', type=str, default='http', 
                       choices=[p.value for p in Protocol],
                       help='Protocol to test (default: http)')
    parser.add_argument('-t', '--threads', type=int, default=10,
                       help='Number of worker threads (default: 10)')
    parser.add_argument('-d', '--duration', type=int, default=60,
                       help='Test duration in seconds (default: 60)')
    parser.add_argument('--timeout', type=int, default=10,
                       help='Request timeout in seconds (default: 10)')
    parser.add_argument('--rps', type=float, default=0,
                       help='Requests per second (0 = unlimited, default: 0)')
    parser.add_argument('-m', '--method', type=str, default='GET',
                       help='HTTP method (default: GET)')
    parser.add_argument('-H', '--headers', type=str,
                       help='HTTP headers as JSON string')
    parser.add_argument('--data', type=str,
                       help='Request body data')
    parser.add_argument('--json', type=str, dest='json_data',
                       help='Request body as JSON')
    parser.add_argument('--auth', type=str,
                       help='Basic auth as "username:password"')
    parser.add_argument('--proxy', type=str,
                       help='Proxy URL')
    parser.add_argument('--no-verify-ssl', action='store_true',
                       help='Disable SSL verification')
    parser.add_argument('--response-check', type=str,
                       help='Expected HTTP status codes as comma-separated list (default: 200)')
    parser.add_argument('--cookies', type=str,
                       help='Cookies as JSON string')
    parser.add_argument('--discord-webhook', type=str,
                       help='Discord webhook URL for notifications')
    parser.add_argument('-o', '--output', type=str,
                       help='Output file for results (JSON or CSV)')
    parser.add_argument('--format', type=str, choices=['json', 'csv'], default='json',
                       help='Output format (default: json)')
    
    args = parser.parse_args()
    
    headers = {}
    if args.headers:
        try:
            headers = json.loads(args.headers)
        except json.JSONDecodeError:
            logger.error("Invalid JSON for headers")
            sys.exit(1)
    
    auth = None
    if args.auth:
        parts = args.auth.split(':')
        if len(parts) == 2:
            auth = (parts[0], parts[1])
        else:
            logger.error("Auth must be in format 'username:password'")
            sys.exit(1)
    
    proxy = None
    if args.proxy:
        proxy = {'http': args.proxy, 'https': args.proxy}
    
    response_check = [200]
    if args.response_check:
        try:
            response_check = [int(code.strip()) for code in args.response_check.split(',')]
        except ValueError:
            logger.error("Response codes must be integers")
            sys.exit(1)
    
    cookies = {}
    if args.cookies:
        try:
            cookies = json.loads(args.cookies)
        except json.JSONDecodeError:
            logger.error("Invalid JSON for cookies")
            sys.exit(1)
    
    try:
        protocol = Protocol(args.protocol)
    except ValueError:
        logger.error(f"Unknown protocol: {args.protocol}")
        sys.exit(1)
    
    test = AdvancedStressTest(
        target=args.target,
        protocol=protocol,
        threads=args.threads,
        duration=args.duration,
        timeout=args.timeout,
        rps=args.rps,
        method=args.method,
        headers=headers if headers else None,
        data=args.data,
        json_data=args.json_data,
        auth=auth,
        proxy=proxy,
        verify_ssl=not args.no_verify_ssl,
        response_check=response_check,
        cookies=cookies if cookies else None,
        discord_webhook=args.discord_webhook
    )
    
    try:
        logger.info(f"Starting stress test on {args.target} with {args.threads} threads for {args.duration}s")
        test.run()
        
        results = test.get_results()
        
        logger.info("Test completed")
        logger.info(f"Total requests: {results['total_requests']}")
        logger.info(f"Successful requests: {results['successful_requests']}")
        logger.info(f"Failed requests: {results['failed_requests']}")
        logger.info(f"Success rate: {results['success_rate']:.2f}%")
        logger.info(f"RPS: {results['rps']:.2f}")
        logger.info(f"Avg latency: {results['avg_latency']*1000:.2f}ms")
        logger.info(f"P95 latency: {results['p95_latency']*1000:.2f}ms")
        logger.info(f"P99 latency: {results['p99_latency']*1000:.2f}ms")
        
        if args.output:
            test.export_results(args.output, args.format)
        
        test.notifier.notify_test_complete(results)
        test.shutdown()
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        test.notifier.notify_test_error(args.target, str(e))
        test.shutdown()
        sys.exit(1)


if __name__ == '__main__':
    main()
