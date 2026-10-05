## 覆写脚本

适用于单个订阅，直接处理订阅提供的proxies

<https://raw.githubusercontent.com/Huffer342-WSH/routing-rules/refs/heads/main/override.js>

## YAML 模板

[mihomo-provider-template.yaml](./mihomo-provider-template.yaml)

填写模板中的 `proxy-providers` 部分，参考 [proxy-providers](https://wiki.metacubex.one/config/proxy-providers/)。

按地区及按月／定量分类节点，自动补国旗，无需 JS 覆写。

### 手动填写

1. 下载模板，在文件开头的 `proxy-providers` 中，将示例 `url` 替换为自己的订阅链接。
2. 修改机场名称及 `override.additional-prefix`：按月订阅使用 `"[按月・机场名] "`，不限时定量订阅使用 `"[定量・机场名] "`，保留末尾空格。分类依据是前缀，机场名应唯一且不能包含 `]`。
3. 多个机场可复制第二个机场的完整配置块，再修改名称、链接和前缀；保留 `proxy-name: *flag-renames` 以复用国旗规则。第一个机场中的 `&flag-renames` 是共享定义，删除该机场前需将定义移到其他引用之前。

### 自动生成

最简单的自动生成方式：安装 uv，启动 Windows 便携版 Sparkle，然后在仓库根目录运行：

```powershell
uv run --no-project scripts/generate_provider_config.py
```

脚本会自动定位 Sparkle 的订阅文件，将填好的 YAML 打印到终端。复制其中从 `proxy-providers:` 开始的 YAML 内容，保存为 `.yaml` 文件后导入客户端即可。

如需直接保存到文件，运行：

```powershell
uv run --no-project scripts/generate_provider_config.py -o  ./config.yaml
```

生成后将 YAML 作为完整配置导入客户端。更多参数、模板修改和注意事项见[详细使用说明](./docs/mihomo-provider-template.md)。

## 规则:

<https://github.com/Huffer342-WSH/routing-rules/tree/rules>

是在[@MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat/tree/meta)的基础上添加一些我自己的规则得到的。可以在规则配置中的`rule-providers:`中使用，例如：

```yaml
rule-providers:
  domain-proxy:
    type: http
    format: mrs
    behavior: domain
    url: https://raw.githubusercontent.com/Huffer342-WSH/routing-rules/refs/heads/rules/domain/proxy.mrs
    interval: 64800
  domain-direct:
    type: http
    format: mrs
    behavior: domain
    url: https://raw.githubusercontent.com/Huffer342-WSH/routing-rules/refs/heads/rules/domain/direct.mrs
    interval: 64800
  domain-ai:
    type: http
    format: mrs
    behavior: domain
    url: https://raw.githubusercontent.com/Huffer342-WSH/routing-rules/refs/heads/rules/domain/category-ai-chat-!cn.mrs
    interval: 64800
```
