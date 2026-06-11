#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
规则文件合并工具
支持YAML和TEXT格式的规则文件合并，包含智能去重功能
"""

import os
import sys
import yaml
import requests
from pathlib import Path
from typing import List, Dict, Set, Tuple
from urllib.parse import urlparse
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RuleMerger:
    def __init__(self, project_root: str = None):
        """
        初始化规则合并器

        Args:
            project_root: 项目根目录，默认为脚本所在目录的上两级（scripts/merge_rules.py -> ../..）
        """
        if project_root is None:
            # 获取项目根目录（脚本所在位置的上两级）
            script_dir = Path(os.path.abspath(__file__)).parent
            project_root = script_dir.parent

        self.project_root = Path(project_root)
        self.temp_dir = self.project_root / "custom" / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # 用于存储会话，支持系统代理
        self.session = requests.Session()

        logger.info(f"项目根目录: {self.project_root}")
        logger.info(f"临时目录: {self.temp_dir}")

    def download_file(self, url: str, filename: str = None) -> str:
        """
        下载文件到temp目录

        Args:
            url: 文件URL
            filename: 保存的文件名，如果为None则从URL自动生成

        Returns:
            下载文件的路径
        """
        if filename is None:
            # 从URL生成文件名
            parsed_url = urlparse(url)
            filename = os.path.basename(parsed_url.path)
            if not filename:
                filename = f"rules_{hash(url) % 10000}.txt"

        filepath = self.temp_dir / filename

        try:
            logger.info(f"下载文件: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(response.text)

            logger.info(f"文件已保存: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"下载失败: {url}, 错误: {e}")
            raise

    def read_file(self, file_path: str) -> str:
        """
        读取文件内容

        Args:
            file_path: 文件路径

        Returns:
            文件内容
        """
        path = Path(file_path)

        # 如果是相对路径，则相对于项目根目录
        if not path.is_absolute():
            path = self.project_root / path

        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info(f"读取文件: {path}")
            return content

        except Exception as e:
            logger.error(f"读取失败: {path}, 错误: {e}")
            raise

    def parse_yaml_rules(self, content: str, behavior: str = 'classical') -> List[str]:
        """
        解析YAML格式的规则文件

        Args:
            content: 文件内容
            behavior: 文件格式行为
                - 'classical': 用DOMAIN-SUFFIX等来区分的经典格式
                - 'domain': 用+开头表示DOMAIN-SUFFIX的格式

        Returns:
            规则列表（转换为标准classical格式）
        """
        try:
            data = yaml.safe_load(content)
            if isinstance(data, dict) and 'payload' in data:
                payload = data['payload']
                if isinstance(payload, list):
                    rules = []
                    for item in payload:
                        if isinstance(item, str):
                            item = item.strip()
                            # 检查是否已经是标准格式的规则（包含逗号）
                            if ',' in item:
                                # 已经是标准格式，直接保留
                                rules.append(item)
                            else:
                                # 还需要转换
                                if behavior == 'domain':
                                    rule = self._convert_domain_to_rule(item, behavior)
                                else:
                                    rule = self._convert_domain_to_rule(item, 'classical')
                                if rule:
                                    rules.append(rule)
                        else:
                            # 如果不是字符串，保留原样
                            rules.append(str(item))
                    return rules
            logger.warning("无法从YAML中提取payload")
            return []

        except Exception as e:
            logger.error(f"YAML解析失败: {e}")
            return []

    def parse_text_rules(self, content: str, behavior: str = 'classical') -> List[str]:
        """
        解析TEXT格式的规则文件

        Args:
            content: 文件内容
            behavior: 文件格式行为
                - 'classical': 用DOMAIN-SUFFIX等来区分的经典格式
                - 'domain': 用+开头表示DOMAIN-SUFFIX的格式

        Returns:
            规则列表
        """
        rules = []

        for line in content.strip().split('\n'):
            line = line.strip()

            # 跳过空行和注释
            if not line or line.startswith('#'):
                continue

            # 处理规则格式
            rule = self._convert_domain_to_rule(line, behavior)
            if rule:
                rules.append(rule)

        return rules

    def _convert_domain_to_rule(self, domain: str, behavior: str = 'classical') -> str:
        """
        将域名转换为Clash规则格式

        Args:
            domain: 域名
            behavior: 文件格式行为
                - 'classical': 标准格式，+. 表示 DOMAIN-SUFFIX
                - 'domain': 域名格式，+/+. 开头为 DOMAIN-SUFFIX，否则为 DOMAIN

        Returns:
            Clash规则（标准classical格式）
        """
        domain = domain.strip()

        if behavior == 'domain':
            # domain 格式：+/+. 开头表示DOMAIN-SUFFIX
            if domain.startswith('+.'):
                domain = domain[2:]
                return f"DOMAIN-SUFFIX,{domain}"
            elif domain.startswith('+'):
                domain = domain[1:]
                return f"DOMAIN-SUFFIX,{domain}"
            else:
                # 不以+开头的则使用DOMAIN前缀
                if domain:
                    return f"DOMAIN,{domain}"
                return None

        # classical 格式处理
        if domain.startswith('+.'):
            domain = domain[2:]
            return f"DOMAIN-SUFFIX,{domain}"

        # 检查是否包含通配符
        if '*' in domain:
            # 移除通配符，转换为后缀匹配
            domain = domain.replace('*.', '')
            domain = domain.replace('*', '')
            if domain:
                return f"DOMAIN-SUFFIX,{domain}"
            return None

        # 默认转换为DOMAIN-SUFFIX
        if domain:
            return f"DOMAIN-SUFFIX,{domain}"

        return None

    def _parse_rule(self, rule: str) -> Tuple[str, str]:
        """
        解析规则，返回规则类型和内容

        Args:
            rule: 规则字符串，如 "DOMAIN-SUFFIX,example.com"

        Returns:
            (规则类型, 内容)，如 ("DOMAIN-SUFFIX", "example.com")
        """
        if ',' not in rule:
            return None, None

        parts = rule.split(',', 1)
        rule_type = parts[0].strip()
        content = parts[1].strip() if len(parts) > 1 else ''

        return rule_type, content

    def _is_covered_by(self, rule1: str, rule2: str) -> bool:
        """
        判断rule1是否被rule2覆盖

        例如：
        - DOMAIN-SUFFIX,api.example.com 被 DOMAIN-SUFFIX,example.com 覆盖
        - DOMAIN,api.example.com 被 DOMAIN-SUFFIX,example.com 覆盖

        Args:
            rule1: 被检查的规则
            rule2: 覆盖规则

        Returns:
            True 如果 rule1 被 rule2 覆盖
        """
        type1, content1 = self._parse_rule(rule1)
        type2, content2 = self._parse_rule(rule2)

        if not type1 or not type2 or not content1 or not content2:
            return False

        # DOMAIN-KEYWORD 不做处理
        if type1 == 'DOMAIN-KEYWORD' or type2 == 'DOMAIN-KEYWORD':
            return False

        # 如果类型相同
        if type1 == type2:
            if type1 in ('DOMAIN-SUFFIX', 'DOMAIN-SUFFIX'):
                # DOMAIN-SUFFIX,api.example.com 被 DOMAIN-SUFFIX,example.com 覆盖
                if type1 == 'DOMAIN-SUFFIX':
                    return content1.endswith('.' + content2) or content1 == content2

        # DOMAIN-SUFFIX 可以覆盖 DOMAIN
        elif type2 == 'DOMAIN-SUFFIX' and type1 == 'DOMAIN':
            # DOMAIN,api.example.com 被 DOMAIN-SUFFIX,example.com 覆盖
            return content1.endswith('.' + content2) or content1 == content2

        return False

    def deduplicate_rules(self, rules: List[str]) -> List[str]:
        """
        去重规则，删除被覆盖的规则

        规则覆盖关系：
        - DOMAIN-SUFFIX,example.com 覆盖 DOMAIN-SUFFIX,api.example.com
        - DOMAIN-SUFFIX,example.com 覆盖 DOMAIN,api.example.com
        - DOMAIN-KEYWORD 不做处理（因为匹配速度慢）

        Args:
            rules: 规则列表

        Returns:
            去重后的规则列表
        """
        if not rules:
            return rules

        # 转换为set进行基本去重
        unique_rules = list(set(rules))

        # 移除被覆盖的规则
        kept_rules = []

        for i, rule1 in enumerate(unique_rules):
            covered = False

            for j, rule2 in enumerate(unique_rules):
                if i != j and self._is_covered_by(rule1, rule2):
                    covered = True
                    break

            if not covered:
                kept_rules.append(rule1)

        removed_count = len(unique_rules) - len(kept_rules)
        if removed_count > 0:
            logger.info(f"去重完成：删除 {removed_count} 条被覆盖的规则")

        return kept_rules

    def fetch_rules(self, include_config: List[Dict]) -> List[str]:
        """
        获取include中指定的所有规则

        Args:
            include_config: include配置列表，每项包含:
                - type: 文件类型 (txt/yaml)
                - url: 下载地址（可选）
                - path: 本地路径（可选）
                - behavior: 文件格式行为，classical 或 domain（可选，默认classical）

        Returns:
            合并后的规则列表
        """
        all_rules = []

        for item in include_config:
            if not isinstance(item, dict):
                logger.warning(f"跳过无效的include项: {item}")
                continue

            file_type = item.get('type', '').lower()
            url = item.get('url')
            path = item.get('path')
            behavior = item.get('behavior', 'classical').lower()

            if not file_type:
                logger.warning(f"跳过type为空的include项: {item}")
                continue

            try:
                content = None

                if url:
                    # 从URL下载
                    filepath = self.download_file(url)
                    content = self.read_file(filepath)

                elif path:
                    # 从本地路径读取
                    content = self.read_file(path)

                else:
                    logger.warning(f"跳过既无url也无path的include项: {item}")
                    continue

                # 根据类型解析规则
                if file_type in ('txt', 'text', 'list'):
                    rules = self.parse_text_rules(content, behavior)
                elif file_type in ('yaml', 'yml'):
                    rules = self.parse_yaml_rules(content, behavior)
                else:
                    logger.warning(f"未知的文件类型: {file_type}")
                    continue

                logger.info(f"获取到 {len(rules)} 条规则 (类型: {file_type}, behavior: {behavior})")
                all_rules.extend(rules)

            except Exception as e:
                logger.error(f"处理include项失败: {item}, 错误: {e}")
                continue

        return all_rules

    def merge_rules_file(self, config_file: str, output_file: str = None,
                         deduplicate: bool = True) -> str:
        """
        合并规则文件

        Args:
            config_file: 配置文件路径（包含include和payload的YAML文件）
            output_file: 输出文件路径，如果为None则在temp目录生成
            deduplicate: 是否进行去重

        Returns:
            输出文件路径
        """
        # 读取配置文件
        config_content = self.read_file(config_file)
        config_data = yaml.safe_load(config_content)

        if not isinstance(config_data, dict):
            raise ValueError("配置文件必须是YAML格式的字典")

        all_rules: List[str] = []

        # 处理include部分
        include_config = config_data.get('include', [])
        if include_config:
            logger.info(f"开始处理 {len(include_config)} 个include项")
            included_rules = self.fetch_rules(include_config)
            all_rules.extend(included_rules)
            logger.info(f"include共获取 {len(included_rules)} 条规则")

        # 处理payload部分
        payload = config_data.get('payload', [])
        if payload:
            logger.info(f"处理payload中的 {len(payload)} 条规则")
            all_rules.extend(payload)

        # 去重处理
        if deduplicate:
            original_count = len(all_rules)
            all_rules = self.deduplicate_rules(all_rules)
            logger.info(f"去重前: {original_count} 条, 去重后: {len(all_rules)} 条")

        # 转换为列表并排序
        all_rules = sorted(list(set(all_rules)))
        logger.info(f"合并后共 {len(all_rules)} 条规则")

        # 生成输出文件
        if output_file is None:
            config_filename = Path(config_file).stem
            output_file = self.temp_dir / f"{config_filename}_merged.yaml"
        else:
            # 处理相对路径
            output_file = Path(output_file)
            if not output_file.is_absolute():
                output_file = self.project_root / output_file

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 构建输出数据
        output_data = {
            'payload': all_rules
        }

        # 保存为YAML（添加缩进处理）
        from io import StringIO
        stream = StringIO()
        yaml.dump(
            output_data,
            stream,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False
        )

        # 后处理：为列表项添加缩进
        yaml_content = stream.getvalue()
        lines = yaml_content.split('\n')
        formatted_lines = []
        for line in lines:
            if line.startswith('- '):
                # 为列表项添加两个空格的缩进
                formatted_lines.append('  ' + line)
            else:
                formatted_lines.append(line)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(formatted_lines))

        logger.info(f"规则已保存到: {output_path}")
        return str(output_path)

    def merge_multiple_files(self, config_files: List[str], output_file: str = None,
                            deduplicate: bool = True) -> str:
        """
        合并多个配置文件

        Args:
            config_files: 配置文件路径列表
            output_file: 输出文件路径
            deduplicate: 是否进行去重

        Returns:
            输出文件路径
        """
        all_rules: List[str] = []

        for config_file in config_files:
            logger.info(f"处理配置文件: {config_file}")
            config_content = self.read_file(config_file)
            config_data = yaml.safe_load(config_content)

            if not isinstance(config_data, dict):
                logger.warning(f"跳过非字典配置文件: {config_file}")
                continue

            # 处理include部分
            include_config = config_data.get('include', [])
            if include_config:
                included_rules = self.fetch_rules(include_config)
                all_rules.extend(included_rules)

            # 处理payload部分
            payload = config_data.get('payload', [])
            if payload:
                all_rules.extend(payload)

        # 去重处理
        if deduplicate:
            original_count = len(all_rules)
            all_rules = self.deduplicate_rules(all_rules)
            logger.info(f"去重前: {original_count} 条, 去重后: {len(all_rules)} 条")

        # 转换为列表并排序
        all_rules = sorted(list(set(all_rules)))
        logger.info(f"总共合并 {len(all_rules)} 条规则")

        # 生成输出文件
        if output_file is None:
            output_file = self.temp_dir / "merged_rules.yaml"
        else:
            # 处理相对路径
            output_file = Path(output_file)
            if not output_file.is_absolute():
                output_file = self.project_root / output_file

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 构建输出数据
        output_data = {
            'payload': all_rules
        }

        # 保存为YAML（添加缩进处理）
        from io import StringIO
        stream = StringIO()
        yaml.dump(
            output_data,
            stream,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False
        )

        # 后处理：为列表项添加缩进
        yaml_content = stream.getvalue()
        lines = yaml_content.split('\n')
        formatted_lines = []
        for line in lines:
            if line.startswith('- '):
                # 为列表项添加两个空格的缩进
                formatted_lines.append('  ' + line)
            else:
                formatted_lines.append(line)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(formatted_lines))

        logger.info(f"规则已保存到: {output_path}")
        return str(output_path)


def main():
    r"""
    主函数
    使用示例：
        python merge_rules.py custom/category-ai-chat-!cn.yaml
        python merge_rules.py custom/category-ai-chat-!cn.yaml -o output.yaml
        python merge_rules.py file1.yaml file2.yaml file3.yaml -m
    """
    import argparse

    parser = argparse.ArgumentParser(
        description='规则文件合并工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
示例:
  # 合并单个配置文件（包括其include和payload）
  python merge_rules.py custom/category-ai-chat-!cn.yaml

  # 指定输出文件（相对路径相对于项目根目录）
  python merge_rules.py custom/category-ai-chat-!cn.yaml -o merged_output.yaml

  # 合并多个配置文件
  python merge_rules.py file1.yaml file2.yaml file3.yaml -m

  # 禁用去重
  python merge_rules.py config.yaml --no-dedupe
        """
    )

    parser.add_argument(
        'files',
        nargs='+',
        help='要处理的配置文件'
    )

    parser.add_argument(
        '-o', '--output',
        help='输出文件路径（相对于项目根目录）'
    )

    parser.add_argument(
        '-m', '--merge',
        action='store_true',
        help='合并多个配置文件（而不是处理单个文件）'
    )

    parser.add_argument(
        '-r', '--root',
        help='项目根目录'
    )

    parser.add_argument(
        '--no-dedupe',
        action='store_true',
        help='禁用去重功能'
    )

    args = parser.parse_args()

    try:
        merger = RuleMerger(args.root)
        deduplicate = not args.no_dedupe

        if args.merge or len(args.files) > 1:
            # 合并多个文件
            output = merger.merge_multiple_files(args.files, args.output, deduplicate)
        else:
            # 处理单个文件
            output = merger.merge_rules_file(args.files[0], args.output, deduplicate)

        try:
            print(f"\n[OK] 合并完成！输出文件: {output}")
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Windows 环境下编码问题处理
            print(f"\n[OK] 合并完成！输出文件: {output}")
        return 0

    except Exception as e:
        logger.error(f"执行失败: {e}")
        try:
            print(f"\n[ERROR] 执行失败: {e}", file=sys.stderr)
        except (UnicodeEncodeError, UnicodeDecodeError):
            print(f"\n[ERROR] 执行失败: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
