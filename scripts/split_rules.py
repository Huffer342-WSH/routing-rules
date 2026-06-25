#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
规则文件拆分工具
================

将规则文件拆分为 domain、ipcidr、classical 三个类别，分别导出 text 格式的
.list 文件和 yaml 格式的 .yaml 文件。

domain 和 ipcidr 规则集在 mihomo/clash-meta 中匹配效率最高，classical 效率较低。
本工具自动从 classical 规则中提取 DOMAIN/DOMAIN-SUFFIX 归入 domain，
提取 IP-CIDR/IP-CIDR6 归入 ipcidr，剩余规则保留在 classical。

用法示例::

    # 拆分单个配置文件
    python split_rules.py custom/category-ai-chat-\!cn.yaml

    # 指定输出目录和前缀
    python split_rules.py custom/proxy.yaml -o output/ -p proxy

    # 拆分多个配置文件并合并
    python split_rules.py custom/proxy.yaml custom/direct.yaml -m
"""

import os
import sys
import yaml
import logging
from io import StringIO
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse
from ipaddress import ip_network

import requests
from tqdm import tqdm

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Windows 终端编码兼容
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 常量：规则类型分类
# ---------------------------------------------------------------------------

# 可归入 domain 类型的规则前缀
DOMAIN_RULE_TYPES = {"DOMAIN", "DOMAIN-SUFFIX"}

# 可归入 ipcidr 类型的规则前缀
IPCIDR_RULE_TYPES = {"IP-CIDR", "IP-CIDR6"}

# domain-native 格式中表示 DOMAIN-SUFFIX 的前缀
SUFFIX_PREFIX = "+."


# ===================================================================
# RuleSplitter
# ===================================================================

class RuleSplitter:
    """规则拆分器：将规则拆分为 domain / ipcidr / classical 三类。"""

    def __init__(self, project_root: str = None):
        """
        初始化拆分器。

        Args:
            project_root: 项目根目录，默认为脚本所在目录的上两级
                          （scripts/split_rules.py -> ../..）。
        """
        if project_root is None:
            script_dir = Path(os.path.abspath(__file__)).parent
            project_root = script_dir.parent

        self.project_root = Path(project_root)
        self.temp_dir = self.project_root / "custom" / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()

        logger.info("项目根目录: %s", self.project_root)

    # ==================================================================
    # 文件 I/O
    # ==================================================================

    def download_file(self, url: str, filename: str = None) -> str:
        """下载文件到 temp 目录，返回本地路径。"""
        if filename is None:
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path) or f"dl_{hash(url) & 0xFFFF:04x}.txt"

        filepath = self.temp_dir / filename
        logger.info("下载: %s", url)
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()

        filepath.write_text(resp.text, encoding="utf-8")
        logger.info("已保存: %s", filepath)
        return str(filepath)

    def read_file(self, file_path: str) -> str:
        """读取文件内容（支持相对路径，相对于项目根目录）。"""
        path = Path(file_path)
        if not path.is_absolute():
            path = self.project_root / path
        content = path.read_text(encoding="utf-8")
        logger.info("读取文件: %s", path)
        return content

    # ==================================================================
    # 解析：domain-native 格式  <-->  内部 canonical 格式
    #
    # 内部统一使用 canonical 格式存储 domain 规则：
    #   +.suffix.com   →  DOMAIN-SUFFIX
    #   exact.com      →  DOMAIN
    #
    # 输出时：
    #   .list   → 直接写出 canonical
    #   .yaml   → payload 下列出，加单引号
    # ==================================================================

    @staticmethod
    def _parse_rule_tuple(rule: str) -> Tuple[Optional[str], Optional[str]]:
        """将 classical 规则拆为 (类型, 内容)。"""
        if "," not in rule:
            return None, None
        parts = rule.split(",", 1)
        return parts[0].strip().upper(), parts[1].strip()

    # ---- 从 domain-native 行 / 条目 转为 canonical ----

    @staticmethod
    def _normalize_domain(raw: str) -> Optional[str]:
        """
        将各种 domain 写法统一为 canonical 格式 (``+.suffix`` | ``exact``)。

        支持： ``+.suffix``, ``+suffix``, ``.suffix``, ``*.*.suffix``,
        ``*.suffix``, ``exact.com``, 以及已含逗号的 classical DOMAIN/DOMAIN-SUFFIX。
        """
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            return None

        # 可能是 classical 格式的 DOMAIN / DOMAIN-SUFFIX
        if "," in raw:
            rtype, content = RuleSplitter._parse_rule_tuple(raw)
            if rtype == "DOMAIN-SUFFIX":
                return f"{SUFFIX_PREFIX}{content}"
            if rtype == "DOMAIN":
                return content
            return None  # 不是 domain 类型

        # 已经是 +. 开头 — 直接返回
        if raw.startswith(SUFFIX_PREFIX):
            return raw

        # +suffix → +.suffix
        if raw.startswith("+"):
            return f"{SUFFIX_PREFIX}{raw[1:]}"

        # *.*.suffix  / *.suffix  → +.suffix
        if "*" in raw:
            cleaned = raw.replace("*", "").replace("..", ".")
            cleaned = cleaned.strip(".")
            return f"{SUFFIX_PREFIX}{cleaned}" if cleaned else None

        # .suffix  → +.suffix
        if raw.startswith("."):
            return f"+{raw}"

        # 默认：精确匹配
        return raw

    # ---- 解析各种来源 ----

    def parse_domain_source(self, content: str, file_type: str) -> List[str]:
        """
        解析 behavior=domain 的源文件，返回 canonical domain 列表。

        Args:
            content: 文件原始内容。
            file_type: ``txt`` / ``text`` / ``list`` 或 ``yaml`` / ``yml``。
        """
        rules: List[str] = []

        if file_type in ("yaml", "yml"):
            data = yaml.safe_load(content)
            if isinstance(data, dict) and "payload" in data:
                payload = data["payload"]
                if isinstance(payload, list):
                    for item in payload:
                        if isinstance(item, str):
                            norm = self._normalize_domain(item)
                            if norm:
                                rules.append(norm)
        else:
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                norm = self._normalize_domain(line)
                if norm:
                    rules.append(norm)

        return rules

    def parse_classical_source(self, content: str, file_type: str) -> List[str]:
        """
        解析 behavior=classical 的源文件，返回 ``RULE-TYPE,content`` 列表。

        Args:
            content: 文件原始内容。
            file_type: ``txt`` / ``text`` / ``list`` 或 ``yaml`` / ``yml``。
        """
        rules: List[str] = []

        if file_type in ("yaml", "yml"):
            data = yaml.safe_load(content)
            if isinstance(data, dict) and "payload" in data:
                payload = data["payload"]
                if isinstance(payload, list):
                    for item in payload:
                        if isinstance(item, str):
                            item = item.strip()
                            if item and not item.startswith("#"):
                                rules.append(item)
        else:
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                rules.append(line)

        return rules

    # ==================================================================
    # 分类：classical 规则 → domain / ipcidr / classical
    # ==================================================================

    @staticmethod
    def classify_classical_rules(
        rules: List[str],
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        将 classical 格式规则拆成三组。

        Returns:
            (domain_canonical, ipcidr_cidr_only, classical_original)

        - domain_canonical: 已转为 ``+.suffix`` / ``exact`` 格式
        - ipcidr_cidr_only: 仅 CIDR 部分（去掉 ``IP-CIDR,`` 前缀及 ``,no-resolve``）
        - classical_original: 保持原样
        """
        domains: List[str] = []
        ipcidrs: List[str] = []
        classical: List[str] = []

        for rule in rules:
            rule = rule.strip()
            if not rule or rule.startswith("#"):
                continue

            rtype, content = RuleSplitter._parse_rule_tuple(rule)

            if rtype in DOMAIN_RULE_TYPES:
                # DOMAIN / DOMAIN-SUFFIX → 转为 canonical domain
                if rtype == "DOMAIN-SUFFIX":
                    domains.append(f"{SUFFIX_PREFIX}{content}")
                else:
                    domains.append(content)

            elif rtype in IPCIDR_RULE_TYPES:
                # IP-CIDR / IP-CIDR6 → 只保留 CIDR 地址段
                # content 格式可能是 "1.2.3.0/24,no-resolve"
                cidr = content.split(",")[0].strip()
                if cidr:
                    ipcidrs.append(cidr)

            else:
                # 其余一切归 classical
                classical.append(rule)

        return domains, ipcidrs, classical

    # ==================================================================
    # 去重
    # ==================================================================

    # ---- domain 去重 ----

    @staticmethod
    def deduplicate_domains(domains: List[str]) -> List[str]:
        """
        Domain 规则去重。

        规则：
        - 精确去重：完全相同的条目只保留一条
        - 后缀覆盖：``+.example.com`` 覆盖 ``sub.example.com`` 和
          ``example.com``（后缀匹配能命中所有子域名及自身）
        - 排序：后缀规则在前，精确规则在后，字母序
        """
        if not domains:
            return []

        unique = list(set(domains))

        # 分离后缀规则和精确规则
        suffix_rules: List[str] = []
        exact_rules: List[str] = []

        for d in unique:
            if d.startswith(SUFFIX_PREFIX):
                suffix_rules.append(d)
            else:
                exact_rules.append(d)

        # 构建后缀 Trie（按域名标签反转）
        # 例如 +.example.com → 标签 ["com", "example"]
        trie: dict = {}
        TERM = ""

        for s in suffix_rules:
            domain = s[len(SUFFIX_PREFIX):]  # 去掉 "+."
            labels = domain.lower().split(".")
            node = trie
            for label in reversed(labels):
                node = node.setdefault(label, {})
            node[TERM] = s

        def _covered_by_suffix(domain: str) -> Optional[str]:
            """检查 domain 是否被某个 +.suffix 覆盖。"""
            labels = list(reversed(domain.lower().split(".")))
            node = trie
            for label in labels:
                if label not in node:
                    return None
                node = node[label]
                if TERM in node:
                    # 找到后缀匹配
                    # 完全匹配（idx == len-1）：suffix 规则本身已在 suffix_rules
                    # 中，这里处理 exact 规则被 suffix 覆盖的情况
                    # 部分匹配：子域名被 suffix 覆盖
                    return node[TERM]
            return None

        # 过滤被后缀覆盖的精确规则
        kept_exact = [d for d in exact_rules if _covered_by_suffix(d) is None]

        # 后缀规则内部去重：较短的 suffix 覆盖较长的
        # 例如 +.example.com 被 +.com 覆盖（但通常不会出现这种情况）
        # 这里只做精确去重（已在 set 中完成）

        kept = suffix_rules + kept_exact
        kept.sort(key=lambda d: (not d.startswith(SUFFIX_PREFIX), d))

        removed = len(unique) - len(kept)
        if removed:
            logger.info("domain 去重: %d → %d (删除 %d 条)", len(unique), len(kept), removed)

        return kept

    # ---- ipcidr 去重 ----

    @staticmethod
    def deduplicate_ipcidrs(ipcidrs: List[str]) -> List[str]:
        """
        IP-CIDR 规则去重。

        规则：
        - 精确去重
        - 大段覆盖小段：``1.0.0.0/8`` 覆盖 ``1.2.3.0/24``
        - 排序：按网络地址排序
        """
        if not ipcidrs:
            return []

        unique = list(set(ipcidrs))

        # 解析为 ip_network 对象
        networks: List[Tuple[str, ip_network]] = []
        for cidr in unique:
            try:
                net = ip_network(cidr, strict=False)
                networks.append((cidr, net))
            except ValueError:
                # 无法解析的保留原样
                networks.append((cidr, None))

        # 按前缀长度升序（大段在前），便于覆盖检查
        valid = [(c, n) for c, n in networks if n is not None]
        invalid = [c for c, n in networks if n is None]

        valid.sort(key=lambda x: x[1].prefixlen)

        kept: List[str] = []
        kept_nets: List[ip_network] = []

        for cidr, net in tqdm(valid, desc="IP-CIDR 去重", unit="cidr"):
            covered = False
            for existing in kept_nets:
                try:
                    if net.subnet_of(existing):
                        covered = True
                        break
                except TypeError:
                    # IPv4 vs IPv6 混合比较（Python 3.7+ 不会发生，但防御）
                    if net.version == existing.version and net.subnet_of(existing):
                        covered = True
                        break
            if not covered:
                kept.append(cidr)
                kept_nets.append(net)

        kept.extend(invalid)

        removed = len(unique) - len(kept)
        if removed:
            logger.info("ipcidr 去重: %d → %d (删除 %d 条)", len(unique), len(kept), removed)

        return kept

    # ---- classical 去重 ----

    @staticmethod
    def deduplicate_classical(rules: List[str]) -> List[str]:
        """
        Classical 规则去重（仅精确去重 + 排序）。

        DOMAIN 与 DOMAIN-SUFFIX 已被移除，这里主要是 GEOIP / DST-PORT /
        SRC-PORT / IP-ASN 等无法做覆盖判断的规则。
        """
        if not rules:
            return []

        unique = list(set(rules))
        unique.sort()
        removed = len(rules) - len(unique)
        if removed:
            logger.info("classical 去重: %d → %d (删除 %d 条)", len(rules), len(unique), removed)
        return unique

    # ==================================================================
    # 输出
    # ==================================================================

    @staticmethod
    def _write_list(filepath: Path, rules: List[str]):
        """写 text 格式（.list）。"""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text("\n".join(rules) + ("\n" if rules else ""), encoding="utf-8")
        logger.info("写入: %s (%d 条)", filepath, len(rules))

    @staticmethod
    def _write_yaml(filepath: Path, rules: List[str]):
        """写 YAML 格式（.yaml）。"""
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # 强制为可能产生歧义的标量加单引号（如 +.xxx、*xxx、.xxx）
        class QuotedString(str):
            pass

        def quoted_representer(dumper, data):
            return dumper.represent_scalar(
                "tag:yaml.org,2002:str", str(data), style="'"
            )

        yaml.add_representer(QuotedString, quoted_representer)

        def _quote_if_needed(s: str) -> str:
            if s and (s[0] in "+*." or ":" in s or "#" in s):
                return QuotedString(s)
            return s

        quoted_rules = [_quote_if_needed(r) for r in rules]

        stream = StringIO()
        yaml.dump(
            {"payload": quoted_rules},
            stream,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

        # 后处理：为列表项添加缩进（兼容 clash 规则集格式）
        lines = stream.getvalue().split("\n")
        formatted = []
        for line in lines:
            if line.startswith("- "):
                formatted.append("  " + line)
            else:
                formatted.append(line)

        filepath.write_text("\n".join(formatted), encoding="utf-8")
        logger.info("写入: %s (%d 条)", filepath, len(rules))

    def write_category(self, out_dir: Path, prefix: str, category: str,
                       rules: List[str]):
        """输出一个类别：``{category}/{prefix}.list`` 和 ``{category}/{prefix}.yaml``。"""
        if not rules:
            logger.warning("%s: 无规则，跳过输出", category)
            return

        cat_dir = out_dir / category
        list_path = cat_dir / f"{prefix}.list"
        yaml_path = cat_dir / f"{prefix}.yaml"

        self._write_list(list_path, rules)
        self._write_yaml(yaml_path, rules)

    # ==================================================================
    # 主流程
    # ==================================================================

    def split_config(self, config_file: str,
                     deduplicate: bool = True) -> Tuple[List[str], List[str], List[str]]:
        """
        解析一个配置文件的 include + payload，返回三类规则。

        Returns:
            (domain_rules, ipcidr_rules, classical_rules)
        """
        config_content = self.read_file(config_file)
        config_data = yaml.safe_load(config_content)

        if not isinstance(config_data, dict):
            raise ValueError(f"配置文件必须是 YAML 字典: {config_file}")

        all_domains: List[str] = []
        all_ipcidrs: List[str] = []
        all_classical: List[str] = []

        # ---- 处理 include ----
        for item in config_data.get("include", []):
            if not isinstance(item, dict):
                continue

            file_type = item.get("type", "").lower()
            behavior = item.get("behavior", "classical").lower()
            url = item.get("url")
            path = item.get("path")

            if not file_type:
                logger.warning("跳过 type 为空的 include 项: %s", item)
                continue

            try:
                # 获取内容
                if url:
                    local_path = self.download_file(url)
                    content = self.read_file(local_path)
                elif path:
                    content = self.read_file(path)
                else:
                    logger.warning("跳过无 url 也无 path 的 include 项")
                    continue

                if behavior == "domain":
                    # 直接解析为 canonical domain 格式
                    domains = self.parse_domain_source(content, file_type)
                    logger.info("include (domain): 获取 %d 条 domain 规则", len(domains))
                    all_domains.extend(domains)

                else:
                    # 解析为 classical 格式，再分类
                    rules = self.parse_classical_source(content, file_type)
                    logger.info("include (classical): 获取 %d 条规则", len(rules))
                    dm, ip, cl = self.classify_classical_rules(rules)
                    all_domains.extend(dm)
                    all_ipcidrs.extend(ip)
                    all_classical.extend(cl)

            except Exception:
                logger.exception("处理 include 项失败: %s", item)
                continue

        # ---- 处理 payload ----
        payload = config_data.get("payload", [])
        if payload:
            logger.info("处理 payload: %d 条规则", len(payload))
            dm, ip, cl = self.classify_classical_rules(
                [str(p) for p in payload if isinstance(p, str)]
            )
            all_domains.extend(dm)
            all_ipcidrs.extend(ip)
            all_classical.extend(cl)

        # ---- 去重 ----
        logger.info(
            "分类汇总 — domain: %d, ipcidr: %d, classical: %d",
            len(all_domains), len(all_ipcidrs), len(all_classical),
        )

        if deduplicate:
            all_domains = self.deduplicate_domains(all_domains)
            all_ipcidrs = self.deduplicate_ipcidrs(all_ipcidrs)
            all_classical = self.deduplicate_classical(all_classical)

        return all_domains, all_ipcidrs, all_classical

    def split_and_write(self, config_file: str, output_dir: str = None,
                        output_prefix: str = None,
                        deduplicate: bool = True) -> Dict[str, int]:
        """
        拆分一个配置文件并写入输出。

        Args:
            config_file: 输入配置文件路径。
            output_dir: 输出目录（默认为项目根目录下的 ``publish-rules/``）。
            output_prefix: 输出文件前缀（默认使用配置文件名）。

        Returns:
            {category: count} 字典。
        """
        domains, ipcidrs, classical = self.split_config(config_file, deduplicate)

        if output_dir is None:
            out_dir = self.project_root / "publish-rules"
        else:
            out_dir = Path(output_dir)
            if not out_dir.is_absolute():
                out_dir = self.project_root / out_dir

        if output_prefix is None:
            output_prefix = Path(config_file).stem

        self.write_category(out_dir, output_prefix, "domain", domains)
        self.write_category(out_dir, output_prefix, "ipcidr", ipcidrs)
        self.write_category(out_dir, output_prefix, "classical", classical)

        return {
            "domain": len(domains),
            "ipcidr": len(ipcidrs),
            "classical": len(classical),
        }

    def merge_and_split(self, config_files: List[str], output_dir: str = None,
                        output_prefix: str = "merged",
                        deduplicate: bool = True) -> Dict[str, int]:
        """
        合并多个配置文件后拆分输出。

        Args:
            config_files: 配置文件路径列表。
            output_dir: 输出目录。
            output_prefix: 输出文件前缀。

        Returns:
            {category: count} 字典。
        """
        all_domains: List[str] = []
        all_ipcidrs: List[str] = []
        all_classical: List[str] = []

        for cf in config_files:
            logger.info("=== 处理: %s ===", cf)
            dm, ip, cl = self.split_config(cf, deduplicate)
            all_domains.extend(dm)
            all_ipcidrs.extend(ip)
            all_classical.extend(cl)

        # 合并后再次去重（跨文件去重）
        logger.info(
            "合并汇总 — domain: %d, ipcidr: %d, classical: %d",
            len(all_domains), len(all_ipcidrs), len(all_classical),
        )

        if deduplicate:
            all_domains = self.deduplicate_domains(all_domains)
            all_ipcidrs = self.deduplicate_ipcidrs(all_ipcidrs)
            all_classical = self.deduplicate_classical(all_classical)

        if output_dir is None:
            out_dir = self.project_root / "publish-rules"
        else:
            out_dir = Path(output_dir)
            if not out_dir.is_absolute():
                out_dir = self.project_root / out_dir

        self.write_category(out_dir, output_prefix, "domain", all_domains)
        self.write_category(out_dir, output_prefix, "ipcidr", all_ipcidrs)
        self.write_category(out_dir, output_prefix, "classical", all_classical)

        return {
            "domain": len(all_domains),
            "ipcidr": len(all_ipcidrs),
            "classical": len(all_classical),
        }


# ===================================================================
# CLI
# ===================================================================

def main():
    r"""
    主入口。

    示例::

        # 拆分单个配置文件
        python split_rules.py custom/category-ai-chat-\!cn.yaml

        # 指定输出目录和前缀
        python split_rules.py custom/proxy.yaml -o publish-rules/ -p proxy

        # 合并多个配置文件后拆分
        python split_rules.py custom/proxy.yaml custom/direct.yaml -m

        # 禁用去重
        python split_rules.py custom/proxy.yaml --no-dedupe
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="规则文件拆分工具 — 拆分为 domain / ipcidr / classical 三类",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=main.__doc__,
    )
    parser.add_argument(
        "files", nargs="+", help="要处理的配置文件（一个或多个）"
    )
    parser.add_argument(
        "-o", "--output-dir", default=None,
        help="输出目录（默认为项目根目录下的 publish-rules/）",
    )
    parser.add_argument(
        "-p", "--prefix", default=None,
        help="输出文件前缀（单文件模式默认使用配置文件名，多文件模式默认为 merged）",
    )
    parser.add_argument(
        "-m", "--merge", action="store_true",
        help="合并多个配置文件后拆分（而非逐个处理）",
    )
    parser.add_argument(
        "-r", "--root", default=None, help="项目根目录",
    )
    parser.add_argument(
        "--no-dedupe", action="store_true", help="禁用去重",
    )

    args = parser.parse_args()

    try:
        splitter = RuleSplitter(args.root)
        deduplicate = not args.no_dedupe
        result: Dict[str, int] = {}

        if args.merge and len(args.files) > 1:
            result = splitter.merge_and_split(
                args.files,
                output_dir=args.output_dir,
                output_prefix=args.prefix or "merged",
                deduplicate=deduplicate,
            )
        else:
            for cf in args.files:
                prefix = args.prefix or Path(cf).stem
                result = splitter.split_and_write(
                    cf,
                    output_dir=args.output_dir,
                    output_prefix=prefix,
                    deduplicate=deduplicate,
                )

        # 汇总
        print("\n===== 拆分结果 =====")
        for cat, cnt in result.items():
            print(f"  {cat}: {cnt} 条")
        print("\n[OK] 拆分完成！")

        return 0

    except Exception:
        logger.exception("执行失败")
        print(f"\n[ERROR] 执行失败，详见日志", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
