# Mihomo 原生订阅分类模板

配套文件：[`mihomo-provider-template.yaml`](../mihomo-provider-template.yaml)。运行时只需要 YAML，不需要覆写脚本或 Sub-Store。

## 从 Sparkle 本地订阅列表生成

脚本：[`scripts/generate_provider_config.py`](../scripts/generate_provider_config.py)，先安装 uv，并在仓库根目录执行本文命令；uv 自动准备脚本依赖，不修改项目 Python 环境。

```powershell
# 查看符合条件的订阅名称、ID 和自动分类，不显示 URL
uv run --no-project scripts/generate_provider_config.py --list

# 自动定位 Sparkle，按 extra.expire 自动分类并生成文件
uv run --no-project scripts/generate_provider_config.py -o "$env:LOCALAPPDATA\mihomo-provider\config.yaml"

# 不指定 -o 时，将完整 YAML 打印到终端
uv run --no-project scripts/generate_provider_config.py
```

未传 `--profile` 时，在 Windows 上查询正在运行的 `Sparkle.exe`，从可执行文件所在目录定位 `data/profile.yaml`。同一路径的多个进程自动去重；没有找到文件、无法读取进程路径或存在多个候选时，提示用 `--profile` 指定，不会猜选配置。此方式适用于便携版目录布局，安装版或自定义数据目录请手动指定。

手动指定优先且不会查询进程，例如 `uv run --no-project scripts/generate_provider_config.py --profile "D:\Sparkle\data\profile.yaml" --list`。默认模板为仓库根目录的配套 YAML，可用 `--template "其他模板路径"` 更换；自动定位和默认模板均不依赖命令运行目录。

- 只选择 `type: remote` 且 URL 非本地地址的条目；跳过本地配置、localhost、`.localhost`／`.local`／`.lan`，以及回环、私有、链路本地等非公网 IP（含 IPv6）。普通域名不做 DNS 查询，因此不会检查其最终解析 IP。
- 支持 Sparkle 的 `items` 列表、兼容软件的 `profiles` 列表，或顶层列表；条目需要 `type`、`name`、`url`，可用 `id`／`uid` 选择。不是任意客户端格式的通用转换器。
- 不下载订阅，不修改源文件或模板，不应用到正在运行的客户端；将选中条目的 URL 与名称填入 provider，其余参数继续使用模板。Sparkle 的 `verify`、`interval`、覆写脚本及代理设置不直接迁移。
- 按用户确认的规则自动分类：`extra.expire: .nan` 为不限时定量，其余（包括缺失或 null）为按月。`--monthly 名称或ID`、`--quota 名称或ID` 可重复并覆盖自动结果，`--skip 名称或ID` 排除。`--default-type monthly|quota` 会覆盖所有未显式指定的订阅类型。`--list` 展示自动分类，不应用这些手动覆盖选项。
- 生成后的国旗规则共享一个 `&flag-renames`，即使只选择定量机场也能独立解析；分组、DNS、规则和其余模板字段保持不变。模板注释和 YAML 锚点使用 round-trip 解析保留。
- 已存在的输出文件需要 `--force` 才会覆盖；即使加此参数也不允许覆盖输入 profile 或模板。输出包含真实订阅凭据，示例将其放在仓库之外。

验证命令：`uv run --no-project --with "ruamel.yaml>=0.18,<0.19" python -m unittest discover -s scripts/tests -v`。已用本机 profile 验证筛选得到 6 个远程非本地订阅，生成文件通过本地 Mihomo `-t` 配置检查；没有测试这些订阅的下载或节点连通性。

## 脚本参数

| 参数                                | 用途                                                |
| ----------------------------------- | --------------------------------------------------- |
| `--profile "路径"`                  | 手动指定订阅元数据，优先于进程自动定位              |
| `--template "路径"`                 | 指定模板，默认使用仓库根目录的模板                  |
| `--monthly "名称或ID"`              | 将指定订阅归为按月，可重复                          |
| `--quota "名称或ID"`                | 将指定订阅归为定量，可重复                          |
| `--skip "名称或ID"`                 | 排除指定订阅，可重复                                |
| `--default-type monthly` 或 `quota` | 覆盖所有未显式指定的订阅类型                        |
| `--list`                            | 仅列出订阅及自动分类，不应用手动分类参数            |
| `-o "路径"`                         | 输出到文件；省略则打印到终端                        |
| `--force`                           | 允许覆盖已有输出文件，仍禁止覆盖输入 profile 或模板 |

例如，手动覆盖部分机场的分类并跳过一个订阅：

```powershell
uv run --no-project scripts/generate_provider_config.py --monthly "机场A" --quota "机场B" --skip "机场C" -o "$env:LOCALAPPDATA\mihomo-provider\config.yaml" --force
```

生成完成后，将输出 YAML 作为完整配置导入客户端。

## 填写机场

修改模板最开头的 `proxy-providers`，替换两个示例 URL。增加机场时，复制对应块并修改 provider 名称、URL 和节点前缀即可；无需维护各策略组的 `use` 列表。

```yaml
proxy-providers:
  按月机场A:
    type: http
    interval: 3600
    proxy: DIRECT
    header:
      User-Agent: ["clash.meta"]
    exclude-filter: '剩余|套餐|网址|客服|过滤|时间|境外'
    health-check:
      enable: true
      url: https://www.gstatic.com/generate_204
      interval: 600
      timeout: 5000
      lazy: true
    url: "你的按月订阅链接"
    override:
      additional-prefix: "[按月・机场A] "
  定量机场B:
    type: http
    interval: 3600
    proxy: DIRECT
    header:
      User-Agent: ["clash.meta"]
    exclude-filter: '剩余|套餐|网址|客服|过滤|时间|境外'
    health-check:
      enable: true
      url: https://www.gstatic.com/generate_204
      interval: 600
      timeout: 5000
      lazy: true
    url: "你的定量订阅链接"
    override:
      additional-prefix: "[定量・机场B] "
  按月机场C:
    type: http
    interval: 3600
    proxy: DIRECT
    header:
      User-Agent: ["clash.meta"]
    exclude-filter: '剩余|套餐|网址|客服|过滤|时间|境外'
    health-check:
      enable: true
      url: https://www.gstatic.com/generate_204
      interval: 600
      timeout: 5000
      lazy: true
    url: "另一个按月订阅链接"
    override:
      additional-prefix: "[按月・机场C] "
```

- 保留前缀的方括号、`・` 和末尾空格；计费标签必须是 `按月` 或 `定量`。
- provider 名称和机场前缀分别保持唯一；机场名不要包含 `]`。
- **实际分类依据是节点前缀，不是 provider 名称。**前缀也避免不同机场同名节点混淆。
- 不需要某种计费类型时，可以删掉对应 provider；该类型的空自动组仍会保留。
- 订阅每小时更新，默认直连下载，携带 `User-Agent: clash.meta`。没有手写缓存路径，Mihomo 按 URL 自动生成，避免复制 provider 时共用缓存文件。
- 新增机场请复制完整的 provider 块，包括 `override.proxy-name`，以保留提示条目过滤、健康检查及国旗重命名。上面的简化示例省略了国旗规则，请以 YAML 模板中的完整块为准。订阅应返回内核支持的节点格式；此次两个链接均能返回含 `proxies` 的 YAML。
- 将模板作为完整配置导入；不要再叠加原 `override.js`，否则其中的策略组会被重新替换。

## 组结构和使用方式

以日本为例：

```text
节点组-🇯🇵日本（手动选择）
├─ ♻️🇯🇵日本-按月自动   ← 所有按月机场的日本节点
├─ ♻️🇯🇵日本-定量自动   ← 所有定量机场的日本节点
└─ 各机场的日本节点    ← 保留高倍率，供手选
```

保留香港、台湾、日本、新加坡、韩国、美国、英国、法国、德国、澳大利亚、加拿大 11 个独立地区组；土耳其、阿根廷、印度、越南、俄罗斯、荷兰、尼日利亚、北马其顿等合并到“其他地区”。每个地区（含其他地区）都有按月、定量两个 `url-test` 组和一个手动组，共 55 个策略组。

| 入口                                              | 行为                                                               |
| ------------------------------------------------- | ------------------------------------------------------------------ |
| 默认代理                                          | 默认进入“自动选择”，也能手选地区、节点、负载均衡或 DIRECT          |
| 自动选择                                          | 手动选择“自动选择-按月”或“自动选择-定量”，默认按月                 |
| 自动选择-AI                                       | 同样拆分按月、定量，默认按月；仅纳入美、日、新、台、英、韩、法、德 |
| 负载均衡-轮询／一致性哈希                         | 各自提供按月、定量两个独立池，默认按月                             |
| 地区手动组                                        | 默认使用该地区的按月自动组，可切换定量或直接选节点                 |
| 战网、Telegram、微软服务 - CN、微软服务、漏网之鱼 | 默认跟随“默认代理”，保留手动切换入口                               |

全局自动组默认 600 秒，地区自动组 300 秒、容差 50ms。provider 本身也配置了健康检查。`lazy: true` 是惰性检查，并不保证定量节点完全不产生测速流量：若使用了相应 provider，健康检查仍可能消耗少量流量。

按月和定量池不会按速度互相抢占，也不会在按月不可用时自动转入定量。需要定量时，手动切换对应入口。机场是否按月／定量由填写者指定，不能从订阅流量统计可靠推断。

## 节点国旗与重命名

模板使用 Mihomo 原生 `override.proxy-name` 正则替换。内核先执行各条重命名规则，再添加 `additional-prefix`；机场名称不参与国旗识别。

```text
日本-优化       → [定量・机场B] 🇯🇵 日本-优化
🇭🇰[HK]HongKong01 → [按月・机场A] 🇭🇰[HK]HongKong01
荷兰-Amsterdam → [按月・机场A] 🇳🇱 荷兰-Amsterdam
```

规则按名称中的国家、英文缩写和部分城市名识别，覆盖原模板的 19 个地区；是否设置独立策略组不影响补国旗。已有任意国旗时保留原样，不重复添加，也不自动纠正原有国旗。没有识别到名称时保留原名；不查询节点 IP，也不保证实际出口所在地。多个国家同时出现时，第一条匹配的规则生效。

国旗规则在第一个机场中通过 `proxy-name: &flag-renames` 定义一次，后续机场使用 `proxy-name: *flag-renames` 复用；修改定义处会应用到所有引用它的机场。新增机场建议复制第二个机场块，再修改 URL 和前缀。锚点必须先定义后引用，删除或移动第一个机场时，需要将完整定义移到最先使用它的机场。

可继续往共享的 `&flag-renames` 列表添加改名规则。例如，下面只展示“无国旗的日本节点补国旗”：

```yaml
proxy-name:
  - pattern: '(?i)^(?!.*[🇦-🇿])(?=.*(?:日本|Japan|Tokyo|(?<![A-Za-z])JP(?![A-Za-z]))).+'
    target: '🇯🇵 $0'
```

`$0` 保留整个原名；捕获组可用 `$1` 等进行替换。当前模板保留完整原名和倍率信息。调整名称后，客户端保存的旧节点选择可能需要重新选择。
