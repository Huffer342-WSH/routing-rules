# /// script
# requires-python = ">=3.10"
# dependencies = ["ruamel.yaml>=0.18,<0.19"]
# ///
"""Read local subscription metadata and fill the Mihomo provider template."""

import argparse
import copy
import io
import ipaddress
import json
import math
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import YAMLError

DEFAULT_TEMPLATE = Path(__file__).resolve().parents[1] / "mihomo-provider-template.yaml"
LABELS = {"monthly": "按月", "quota": "定量"}


def running_sparkle_executables():
    if sys.platform != "win32":
        raise ValueError("自动定位目前支持 Windows；请用 --profile 手动指定")
    command = (
        "$ErrorActionPreference = 'Stop'; "
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
        "$paths = @(Get-CimInstance Win32_Process -Filter \"Name = 'Sparkle.exe'\" "
        "| Where-Object { $_.ExecutablePath } "
        "| Select-Object -ExpandProperty ExecutablePath -Unique); "
        "ConvertTo-Json -InputObject $paths -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW, check=True,
        )
        paths = json.loads(completed.stdout.lstrip("\ufeff"))
        if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
            raise ValueError
        return [Path(p) for p in paths]
    except (OSError, subprocess.SubprocessError, ValueError):
        raise ValueError("无法查询 Sparkle 进程路径；请用 --profile 手动指定") from None


def discover_profile(executables=None):
    paths = running_sparkle_executables() if executables is None else executables
    candidates = sorted({(path.parent / "data" / "profile.yaml").resolve()
                         for path in paths if (path.parent / "data" / "profile.yaml").is_file()})
    if not candidates:
        raise ValueError("未找到运行中 Sparkle 对应的 data/profile.yaml；请启动便携版 Sparkle 或用 --profile 手动指定")
    if len(candidates) > 1:
        raise ValueError("发现多个 Sparkle 配置，请用 --profile 选择：\n" + "\n".join(map(str, candidates)))
    return candidates[0]


def yaml_parser():
    parser = YAML()
    parser.preserve_quotes = True
    parser.width = 4096
    return parser


def read_yaml(path):
    try:
        return yaml_parser().load(path.read_text(encoding="utf-8-sig"))
    except YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f"（第 {mark.line + 1} 行）" if mark else ""
        # Parser exceptions can contain the subscription URL; never echo them.
        raise ValueError(f"YAML 格式错误{location}") from None


def subscriptions(document):
    """Support Sparkle items and compatible items/profiles metadata lists."""
    if isinstance(document, dict):
        items = document.get("items", document.get("profiles"))
    else:
        items = document
    if not isinstance(items, list):
        raise ValueError("源文件必须包含 items/profiles 列表，或本身是订阅列表")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("订阅列表包含非对象条目")
        if item.get("type") != "remote":
            continue
        if not item.get("url"):
            continue
        try:
            host = urlsplit(str(item["url"])).hostname
        except ValueError:
            raise ValueError("远程订阅 URL 格式错误") from None
        if not host:
            raise ValueError("远程订阅 URL 缺少主机名")
        host = host.lower().rstrip(".")
        if host == "localhost" or host.endswith((".localhost", ".local", ".lan")):
            continue
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            # Domain names are kept without making DNS requests.
            pass
        else:
            if not address.is_global:
                continue
        result.append(item)
    if not result:
        raise ValueError("源文件没有符合 remote 类型且地址非本地的订阅")
    return result


def identify(item):
    return str(item.get("id", item.get("uid", ""))), str(item.get("name") or "未命名订阅")


def inferred_type(item):
    extra = item.get("extra")
    expire = extra.get("expire") if isinstance(extra, dict) else None
    return "quota" if isinstance(expire, float) and math.isnan(expire) else "monthly"


def assignments(items, monthly=(), quota=(), skip=(), default_type=None):
    choices = {}
    for kind, selectors in (("monthly", monthly), ("quota", quota), ("skip", skip)):
        for selector in selectors:
            matches = [i for i, item in enumerate(items) if selector in identify(item)]
            if len(matches) != 1:
                raise ValueError("订阅选择项不存在或匹配多个条目；请用 --list 查询并改用唯一 ID")
            index = matches[0]
            if index in choices and choices[index] != kind:
                raise ValueError("同一订阅被分配了冲突的计费类型或跳过选项")
            choices[index] = kind
    result = []
    for index, item in enumerate(items):
        kind = choices.get(index, default_type or inferred_type(item))
        if kind != "skip":
            result.append((item, kind))
    if not result:
        raise ValueError("没有选中可生成的订阅")
    return result


def fill_template(template, selected):
    result = copy.deepcopy(template)
    prototypes = result.get("proxy-providers")
    if not isinstance(prototypes, dict) or not prototypes:
        raise ValueError("模板缺少 proxy-providers 示例")
    by_type = {}
    for provider in prototypes.values():
        prefix = str(provider.get("override", {}).get("additional-prefix", ""))
        for kind, label in LABELS.items():
            if prefix.startswith(f"[{label}・"):
                by_type.setdefault(kind, provider)
    providers = CommentedMap()
    shared_renames = None
    for item, kind in selected:
        if kind not in by_type:
            raise ValueError(f"模板缺少 {LABELS[kind]} provider 示例")
        _, name = identify(item)
        if any(c in name for c in "]\r\n"):
            raise ValueError("机场名称不能含 ] 或换行符，请先修改源文件中的名称")
        url = item["url"]
        try:
            valid = isinstance(url, str) and urlsplit(url).scheme in ("http", "https") and urlsplit(url).hostname
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("选中的订阅不是有效的 HTTP(S) URL")
        key = f"{LABELS[kind]}・{name}"
        if key in providers:
            raise ValueError("所选机场名称重复，请先修改源文件中的名称")
        provider = copy.deepcopy(by_type[kind])
        provider["url"] = url
        # Let Mihomo derive distinct cache paths from subscription URLs.
        provider.pop("path", None)
        override = provider.setdefault("override", CommentedMap())
        override["additional-prefix"] = f"[{LABELS[kind]}・{name}] "
        if "proxy-name" in override:
            if shared_renames is None:
                shared_renames = override["proxy-name"]
                shared_renames.yaml_set_anchor("flag-renames", always_dump=True)
            elif override["proxy-name"] != shared_renames:
                raise ValueError("模板中各计费类型的国旗规则不同，无法共享")
            override["proxy-name"] = shared_renames
        # Remove template comments saying this particular provider is the first.
        override.ca.items.pop("proxy-name", None)
        providers[key] = provider
    for provider in providers.values():
        provider.ca.end.clear()
    result["proxy-providers"] = providers
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="读取本地订阅元数据，填充 Mihomo YAML 模板；不下载订阅。")
    parser.add_argument("--profile", type=Path, help="手动指定订阅元数据；默认从运行中的 Sparkle.exe 目录定位 data/profile.yaml")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--list", action="store_true", help="列出名称、ID 和自动识别的计费类型，不显示订阅链接")
    parser.add_argument("--monthly", action="append", default=[], metavar="名称或ID", help="按月订阅，可重复")
    parser.add_argument("--quota", action="append", default=[], metavar="名称或ID", help="定量订阅，可重复")
    parser.add_argument("--skip", action="append", default=[], metavar="名称或ID", help="跳过订阅，可重复")
    parser.add_argument("--default-type", choices=LABELS, help="覆盖未显式归类的订阅类型；默认 extra.expire 为 .nan 时定量，其余按月")
    parser.add_argument("-o", "--output", type=Path, help="输出文件；省略时将完整 YAML（含订阅链接）打印到终端")
    parser.add_argument("--force", action="store_true", help="覆盖已有输出文件")
    args = parser.parse_args(argv)
    try:
        if args.profile is None:
            args.profile = discover_profile()
            print(f"已自动定位订阅文件：{args.profile}", file=sys.stderr)
        items = subscriptions(read_yaml(args.profile))
        if args.list:
            for item in items:
                identity, name = identify(item)
                print(f"{identity}\t{name}\t{LABELS[inferred_type(item)]}")
            return 0
        if args.output and args.output.resolve() in (args.profile.resolve(), args.template.resolve()):
            raise ValueError("输出路径不能覆盖源 profile 或模板")
        selected = assignments(items, args.monthly, args.quota, args.skip, args.default_type)
        document = fill_template(read_yaml(args.template), selected)
        buffer = io.StringIO()
        yaml_parser().dump(document, buffer)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("w" if args.force else "x", encoding="utf-8", newline="\n") as output:
                output.write(buffer.getvalue())
            print(f"已生成 {len(selected)} 个 provider → {args.output}", file=sys.stderr)
        else:
            sys.stdout.write(buffer.getvalue())
        return 0
    except (ValueError, OSError, YAMLError) as exc:
        if isinstance(exc, FileExistsError):
            message = "输出文件已存在；需要覆盖时加 --force"
        elif isinstance(exc, OSError):
            message = f"文件读写失败：{type(exc).__name__}"
        elif isinstance(exc, YAMLError):
            message = "无法生成 YAML"
        else:
            message = str(exc)
        print(f"错误：{message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
