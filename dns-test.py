#!/usr/bin/env python3
"""DNS 测试工具 - CLI 版本

用法:
    uv run dns-test.py               # 交互模式，逐次输入域名
    uv run dns-test.py <域名>         # 单次查询模式
"""

from __future__ import annotations

import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

import dns.message
import dns.query
import dns.rdatatype
from dns.exception import Timeout as DNSTimeout

# ── 配置 ──────────────────────────────────────────────
DNS_SERVERS: list[dict[str, str]] = [
    # ── UDP ──
    {"type": "UDP",  "name": "Google",             "addr": "8.8.8.8"},
    {"type": "UDP",  "name": "Google Sec",         "addr": "8.8.4.4"},
    {"type": "UDP",  "name": "Cloudflare",         "addr": "1.1.1.1"},
    {"type": "UDP",  "name": "Quad9",              "addr": "9.9.9.9"},
    {"type": "UDP",  "name": "AliDNS (阿里)",       "addr": "223.5.5.5"},
    {"type": "UDP",  "name": "DNSPod (腾讯)",       "addr": "119.29.29.29"},
    {"type": "UDP",  "name": "OpenDNS",            "addr": "208.67.222.222"},
    {"type": "UDP",  "name": "DNS.SB",             "addr": "185.222.222.222"},
    # ── DoT ──
    {"type": "DoT",  "name": "Google DoT",         "addr": "8.8.8.8"},
    {"type": "DoT",  "name": "Google DoT Sec",     "addr": "8.8.4.4"},
    {"type": "DoT",  "name": "Cloudflare DoT",     "addr": "1.1.1.1"},
    {"type": "DoT",  "name": "Quad9 DoT",          "addr": "9.9.9.9"},
    {"type": "DoT",  "name": "AliDNS DoT",         "addr": "223.5.5.5"},
    {"type": "DoT",  "name": "DNSPod DoT",         "addr": "1.12.12.12"},
    # ── DoH ──
    {"type": "DoH",  "name": "AliDNS DoH",         "addr": "https://dns.alidns.com/dns-query"},
    {"type": "DoH",  "name": "DNSPod DoH (腾讯)",   "addr": "https://doh.pub/dns-query"},
    {"type": "DoH",  "name": "TWNIC DoH (台湾)",    "addr": "https://dns.twnic.tw/dns-query"},
    {"type": "DoH",  "name": "Google DoH",         "addr": "https://dns.google/dns-query"},
    {"type": "DoH",  "name": "Cloudflare DoH",     "addr": "https://1.1.1.1/dns-query"},
    {"type": "DoH",  "name": "Quad9 DoH",          "addr": "https://9.9.9.9/dns-query"},
    {"type": "DoH",  "name": "DNS.SB DoH",         "addr": "https://doh.dns.sb/dns-query"},
    {"type": "DoH",  "name": "CTC DoH",            "addr": "https://38.76.213.238:8080/dns-query"},
]

TIMEOUT: float = 1.0
DEFAULT_HOST: str = "code.claude.com"


# ── DNS 查询结果 ──────────────────────────────────────

@dataclass
class DNSResult:
    server: dict[str, str]
    result: str = ""
    latency_str: str = ""
    ips: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.ips)


# ── 同步 DNS 查询函数 ─────────────────────────────────

def _query_udp(request: dns.message.Message, addr: str) -> dns.message.Message:
    return dns.query.udp(request, addr, timeout=TIMEOUT)


def _query_dot(request: dns.message.Message, addr: str) -> dns.message.Message:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return dns.query.tls(request, addr, timeout=TIMEOUT, ssl_context=ctx)


def _query_doh(request: dns.message.Message, url: str) -> dns.message.Message:
    wire = request.to_wire()
    req = urllib.request.Request(
        url,
        data=wire,
        headers={
            "Content-Type": "application/dns-message",
            "Accept": "application/dns-message",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as f:
        return dns.message.from_wire(f.read())


def query_single(server: dict[str, str], hostname: str) -> DNSResult:
    """对单个服务器执行 DNS 查询。"""
    result = DNSResult(server=server)
    ips: list[str] = []
    latency = -1.0

    try:
        request = dns.message.make_query(hostname, dns.rdatatype.A)
    except Exception:
        result.result = "Invalid Hostname"
        result.latency_str = "---"
        return result

    try:
        start = time.perf_counter()

        stype = server["type"]
        if stype == "UDP":
            response = _query_udp(request, server["addr"])
        elif stype == "DoT":
            response = _query_dot(request, server["addr"])
        elif stype == "DoH":
            response = _query_doh(request, server["addr"])
        else:
            result.result = f"Unknown type: {stype}"
            result.latency_str = "---"
            return result

        latency = (time.perf_counter() - start) * 1000

        if response and response.answer:
            for rrset in response.answer:
                if rrset.rdtype == dns.rdatatype.A:
                    for rr in rrset:
                        ips.append(rr.to_text())

        if ips:
            extra = f" (+{len(ips) - 1})" if len(ips) > 1 else ""
            result.result = f"{ips[0]}{extra}"
        else:
            result.result = "No Answer"

    except DNSTimeout:
        result.result = "Timeout"
    except urllib.error.URLError as e:
        result.result = f"HTTP Error: {e.reason}"
    except Exception as e:
        err = str(e)
        if "certificate verify failed" in err:
            result.result = "SSL Cert Error"
        else:
            result.result = err.strip()

    result.latency_str = f"{latency:.1f} ms" if latency > 0 else "---"
    result.ips = ips
    return result


def run_all(hostname: str) -> list[DNSResult]:
    """依次查询所有 DNS 服务器。"""
    return [query_single(s, hostname) for s in DNS_SERVERS]


# ── 格式化输出 ────────────────────────────────────────

def print_results(hostname: str, results: list[DNSResult]) -> None:
    """简单对齐打印 DNS 测试结果。"""

    total_success = 0

    for stype, label in [
        ("UDP", "UDP"),
        ("DoT", "DoT"),
        ("DoH", "DoH"),
    ]:
        group = [r for r in results if r.server["type"] == stype]
        if not group:
            continue

        print(f"\n  {'=' * 60}")
        print(f"  {label} 查询")
        print(f"  {'=' * 60}")
        print(f"  {'#':>2}  {'服务商':<18} {'地址':<38} {'解析结果':<30} {'延迟':<10}")
        print(f"  {'-' * 100}")

        for idx, r in enumerate(group, 1):
            print(f"  {idx:>2d}  {r.server['name']:<18} {r.server['addr']:<38} {r.result:<30} {r.latency_str:<10}")

        total_success += sum(1 for r in group if r.success)

    # ── 统计摘要 ──
    total = len(results)
    udp_ok = sum(1 for r in results if r.server["type"] == "UDP" and r.success)
    dot_ok = sum(1 for r in results if r.server["type"] == "DoT" and r.success)
    doh_ok = sum(1 for r in results if r.server["type"] == "DoH" and r.success)

    udp_total = sum(1 for r in results if r.server["type"] == "UDP")
    dot_total = sum(1 for r in results if r.server["type"] == "DoT")
    doh_total = sum(1 for r in results if r.server["type"] == "DoH")

    print()
    print(f"  {'=' * 60}")
    print(f"  DNS 解析测试完成 —— {hostname}")
    print(f"  成功: {total_success}/{total}"
          f"  |  UDP: {udp_ok}/{udp_total}"
          f"  |  DoT: {dot_ok}/{dot_total}"
          f"  |  DoH: {doh_ok}/{doh_total}")

    failed = [r for r in results if not r.success]
    if failed:
        print(f"  失败 ({len(failed)}):")
        for r in failed:
            print(f"    · {r.server['type']:>3s}  {r.server['name']:<18s}  {r.result}  [{r.latency_str}]")
    print()


def print_running(hostname: str) -> None:
    """打印开始测试的提示。"""
    print(f"\n  ⟳ 正在测试: {hostname} ...")
    sys.stdout.flush()


# ── 入口 ──────────────────────────────────────────────

def banner() -> None:
    """打印工具标题。"""
    print()
    print("  ==========================================")
    print("    DNS 解析测试工具")
    print("    UDP  /  DoT (DNS-over-TLS)  /  DoH")
    print("  ==========================================")
    print()


def main() -> None:
    banner()

    # 如果命令行传入了域名，单次查询后退出
    if len(sys.argv) > 1:
        hostname = sys.argv[1].strip()
        print_running(hostname)
        results = run_all(hostname)
        print_results(hostname, results)
        return

    # ── 交互模式 ──
    print("  输入域名进行测试，输入 q 退出\n")

    while True:
        try:
            raw = input(f"  [域名] (回车测试 {DEFAULT_HOST}) > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if raw.lower() in ("q", "quit", "exit"):
            break

        if not raw:
            raw = DEFAULT_HOST

        # 去除协议前缀和路径
        hostname = (
            raw.replace("https://", "")
            .replace("http://", "")
            .split("/")[0]
            .split("?")[0]
            .split("#")[0]
        )

        if not hostname:
            continue

        print_running(hostname)
        results = run_all(hostname)
        print_results(hostname, results)


if __name__ == "__main__":
    main()
