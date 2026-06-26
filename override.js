function main(config) {

    // 自动测速/选择节点组的测试间隔，单位：秒
    const autoSelectInterval = 600;
    const rulesetUpdateInterval = 64800;
    const netTestUrl = 'https://www.gstatic.com/generate_204'

    // -----------------------------------
    // 基础参数配置
    // -----------------------------------
    config["mixed-port"] = 7890;        // 混合端口（HTTP/SOCKS5）
    config["allow-lan"] = true;         // 允许局域网连接
    config["bind-address"] = "*";       // 绑定地址
    config["mode"] = "rule";            // 代理模式：规则模式
    config["log-level"] = "info";       // 日志等级

    config["tcp-concurrent"] = true; // TCP 并发连接
    config["geodata-mode"] = true;   // 启用 GeoData 模式
    config["find-process-mode"] = "strict";

    config.sniffer = {
        enable: true,
        "parse-pure-ip": true,
        "force-dns-mapping": true,
        "override-destination": false,
        sniff: {
            HTTP: {
                ports: [80, 443],
                "override-destination": false
            },
            TLS: {
                ports: [443]
            }
        },
        "skip-domain": [
            "+.push.apple.com"
        ],
        "skip-dst-address": [
            "91.105.192.0/23",
            "91.108.4.0/22",
            "91.108.8.0/21",
            "91.108.16.0/21",
            "91.108.56.0/22",
            "95.161.64.0/20",
            "149.154.160.0/20",
            "185.76.151.0/24",
            "2001:67c:4e8::/48",
            "2001:b28:f23c::/47",
            "2001:b28:f23f::/48",
            "2a0a:f280:203::/48"
        ]
    };

    // -----------------------------------
    // DNS 配置
    // -----------------------------------
    config["dns"] = {
        enable: true,
        ipv6: true,
        "respect-rules": false,
        "enhanced-mode": "fake-ip",
        "fake-ip-range": "198.18.0.1/16",
        "fake-ip-filter": [
            '"*"',
            '+.lan',
            '+.local',
            'time.*.com',
            'ntp.*.com',
            '+.market.xiaomi.com'
        ],

        // 用于解析DNS服务器的域名（如dns.google -> 8.8.8.8），必须为IP
        "default-nameserver": ["223.5.5.5", "119.29.29.29"],

        // 代理节点域名解析服务器，仅用于解析代理节点的域名
        "proxy-server-nameserver": ["https://dns.alidns.com/dns-query", "https://d.atri.ink/dns-query"],
        "proxy-server-nameserver-policy": {
            // CTC-02机场
            "+.ctcxianyu.com": ['https://38.76.213.238:8080/dns-query', 'https://sublol.iotechn.com:10086/dns-query'],
            "+.525536.xyz": ['https://38.76.213.238:8080/dns-query', 'https://sublol.iotechn.com:10086/dns-query'],
        },

        // 适用于直连国外服务器时，通过国外的DNS解析得到可靠的IP
        "nameserver-policy": {
            "geosite:gfw": [
                "https://cloudflare-dns.com/dns-query#默认代理",
                "https://d.atri.ink/dns-query"
            ]
        },
        "nameserver": [
            "system",
            "223.5.5.5",
        ],

        // 查询得到虚假IP时使用fallback的结果
        "fallback-filter": {
            "ipcidr": [
                "240.0.0.0/4",
                "0.0.0.0/32",
                "127.0.0.1/32"
            ],
        },
        "fallback": [
            "https://cloudflare-dns.com/dns-query#默认代理",
            "https://d.atri.ink/dns-query",
            'https://38.76.213.238:8080/dns-query'
        ],
    };

    // ===================================
    // 节点组配置
    // ===================================

    const ICON_BASE = 'https://raw.githubusercontent.com/Huffer342-WSH/routing-rules/refs/heads/main/icon';
    const INVALID_NODE_PATTERN = /剩余|套餐|网址|客服|过滤|时间|境外/;
    const AI_REGION_NAMES = ['美国', '日本', '新加坡', '台湾', '英国', '韩国', '法国', '德国'];
    const SERVICE_GROUP_META_LIST = [
        ['Microsoft Copilot', 'Microsoft%20Copilot.png'],
        ['战网', 'Battle.png'],
        ['Telegram', 'Telegram.png'],
        ['苹果服务', 'Apple.png'],
        ['微软服务 - CN', 'Microsoft.png'],
        ['微软服务', 'Microsoft.png'],
    ];

    /**
     * 从“节点名数组”中过滤高倍率节点，返回仍可用于自动测速的节点名数组。
     * @param {string[]} proxyNodeNames 节点名字数组
     * @returns {string[]} 节点名字数组
     */
    function filterHighMultiplierNodes(proxyNodeNames) {
        const regex = /(\d+\.?\d*)\s*[倍xX]|[倍xX]\s*(\d+\.?\d*)/;
        return proxyNodeNames.filter(name => {
            const match = name.match(regex);
            if (!match) return true;
            const num = parseFloat(match[1] || match[2]);
            return num <= 1;
        });
    }

    /**
     * 创建一个 select 类型的“节点组元素”。
     * @param {string} groupName 节点组名字
     * @param {string[]} proxyOptionNames 节点组候选项名字数组，可包含节点名、节点组名和 DIRECT
     * @param {string} [iconUrl] 图标地址
     * @returns {object} 节点组元素
     */
    function createSelectGroupItem(groupName, proxyOptionNames, iconUrl) {
        return {
            name: groupName,
            ...(iconUrl ? { icon: iconUrl } : {}),
            type: 'select',
            proxies: proxyOptionNames,
        };
    }

    /**
     * 创建一个 url-test 类型的“节点组元素”。
     * @param {string} groupName 节点组名字
     * @param {string[]} proxyNodeNames 参与测速的节点名字数组
     * @param {object} [options] 覆盖默认测速参数
     * @returns {object} 节点组元素
     */
    function createUrlTestGroupItem(groupName, proxyNodeNames, options = {}) {
        return {
            name: groupName,
            type: 'url-test',
            proxies: proxyNodeNames,
            url: netTestUrl,
            interval: autoSelectInterval,
            ...options,
        };
    }

    /**
     * 创建一个 load-balance 类型的“节点组元素”。
     * @param {string} groupName 节点组名字
     * @param {string[]} proxyNodeNames 参与负载均衡的节点名字数组
     * @param {string} strategy 负载均衡策略
     * @returns {object} 节点组元素
     */
    function createLoadBalanceGroupItem(groupName, proxyNodeNames, strategy) {
        return {
            name: groupName,
            type: 'load-balance',
            proxies: proxyNodeNames,
            url: netTestUrl,
            interval: autoSelectInterval,
            strategy,
            lazy: true,
        };
    }

    /**
     * 根据地区规则创建一组地区节点组元素：手动选择组 + 自动测速组。
     * @param {string[]} usableProxyNodeNames 可用节点名字数组
     * @param {object} regionMatcher 地区匹配规则
     * @returns {object|null} 地区节点组结果，包含两个节点组元素
     */
    function createRegionGroupItems(usableProxyNodeNames, regionMatcher) {
        const matchedProxyNodeNames = usableProxyNodeNames.filter(proxyNodeName =>
            regionMatcher.match.some(pattern => pattern.test(proxyNodeName))
        );

        if (matchedProxyNodeNames.length === 0) return null;

        const regionSelectGroupName = `节点组-${regionMatcher.emoji}${regionMatcher.name}`;
        const regionAutoGroupName = `♻️${regionMatcher.emoji}${regionMatcher.name}-自动选择`;
        const regionProxyOptionNames = [regionAutoGroupName, ...matchedProxyNodeNames];

        return {
            regionName: regionMatcher.name,
            autoGroupItem: createUrlTestGroupItem(
                regionAutoGroupName,
                filterHighMultiplierNodes(matchedProxyNodeNames),
                { interval: 300, tolerance: 50 }
            ),
            selectGroupItem: createSelectGroupItem(
                regionSelectGroupName,
                regionProxyOptionNames
            ),
        };
    }

    // 地区识别规则。英文缩写按完整片段匹配，避免 US 误命中 AUS。
    const regionMatchers = [
        { name: '美国', emoji: '🇺🇸', match: [/美国/, /(^|[^A-Z])US(?=$|[^A-Z])/, /States/, /🇺🇸/] },
        { name: '香港', emoji: '🇭🇰', match: [/香港/, /(^|[^A-Z])HK(?=$|[^A-Z])/, /Hong/, /🇭🇰/] },
        { name: '台湾', emoji: '🇹🇼', match: [/台湾/, /(^|[^A-Z])TW(?=$|[^A-Z])/, /Tai/, /🇹🇼/] },
        { name: '日本', emoji: '🇯🇵', match: [/日本/, /(^|[^A-Z])JP(?=$|[^A-Z])/, /Japan/, /🇯🇵/] },
        { name: '新加坡', emoji: '🇸🇬', match: [/新加坡/, /(^|[^A-Z])SG(?=$|[^A-Z])/, /Singapore/, /🇸🇬/] },
        { name: '韩国', emoji: '🇰🇷', match: [/韩国/, /(^|[^A-Z])KR(?=$|[^A-Z])/, /Korea/, /🇰🇷/] },
        { name: '英国', emoji: '🇬🇧', match: [/英国/, /(^|[^A-Z])UK(?=$|[^A-Z])/, /Kingdom/, /🇬🇧/] },
        { name: '法国', emoji: '🇫🇷', match: [/法国/, /(^|[^A-Z])FR(?=$|[^A-Z])/, /France/, /🇫🇷/] },
        { name: '德国', emoji: '🇩🇪', match: [/德国/, /(^|[^A-Z])DE(?=$|[^A-Z])/, /Germany/, /🇩🇪/] },
        { name: '澳大利亚', emoji: '🇦🇺', match: [/澳大利亚/, /(^|[^A-Z])AU(?=$|[^A-Z])/, /Australia/, /🇦🇺/] },
        { name: '加拿大', emoji: '🇨🇦', match: [/加拿大/, /(^|[^A-Z])CA(?=$|[^A-Z])/, /Canada/, /🇨🇦/] },
        { name: '土耳其', emoji: '🇹🇷', match: [/土耳其/, /(^|[^A-Z])TR(?=$|[^A-Z])/, /Turkey/, /🇹🇷/] },
        { name: '阿根廷', emoji: '🇦🇷', match: [/阿根廷/, /(^|[^A-Z])AR(?=$|[^A-Z])/, /Argentina/, /🇦🇷/] },
        { name: '印度', emoji: '🇮🇳', match: [/印度/, /(^|[^A-Z])IN(?=$|[^A-Z])/, /India/, /🇮🇳/] },
        { name: '越南', emoji: '🇻🇳', match: [/越南/, /(^|[^A-Z])VN(?=$|[^A-Z])/, /Vietnam/, /🇻🇳/] },
        { name: '俄罗斯', emoji: '🇷🇺', match: [/俄罗斯/, /(^|[^A-Z])RU(?=$|[^A-Z])/, /Russia/, /🇷🇺/] },
    ];

    // ===================================
    // 节点组生成
    // ===================================

    // NodeNames: 真实节点的 name 字段数组。
    const rawProxyNodeNames = (config.proxies || []).map(proxy => proxy.name);
    const usableProxyNodeNames = rawProxyNodeNames.filter(name => !INVALID_NODE_PATTERN.test(name));
    const autoTestProxyNodeNames = filterHighMultiplierNodes(usableProxyNodeNames);

    // GroupItems: 完整节点组对象数组，会写入 config['proxy-groups']。
    const autoProxyGroupItems = [];
    const regionSelectGroupItems = [];
    const serviceProxyGroupItems = [];

    // GroupNames: 节点组名字数组；OptionNames: Clash proxies 候选项名字数组。
    const regionSelectGroupNames = [];
    const aiAutoProxyNodeNames = [];
    const aiProxyOptionNames = ['自动选择-AI'];

    regionMatchers.forEach(regionMatcher => {
        const regionGroupItems = createRegionGroupItems(usableProxyNodeNames, regionMatcher);
        if (!regionGroupItems) return;

        autoProxyGroupItems.push(regionGroupItems.autoGroupItem);
        regionSelectGroupItems.push(regionGroupItems.selectGroupItem);
        regionSelectGroupNames.push(regionGroupItems.selectGroupItem.name);

        if (AI_REGION_NAMES.includes(regionGroupItems.regionName)) {
            aiProxyOptionNames.push(regionGroupItems.selectGroupItem.name);
            aiAutoProxyNodeNames.push(...regionGroupItems.autoGroupItem.proxies);
        }
    });

    const commonProxyOptionNames = [
        '默认代理',
        'DIRECT',
        '自动选择',
        '负载均衡-轮询',
        '负载均衡-一致性哈希',
        ...regionSelectGroupNames,
        ...usableProxyNodeNames,
    ];

    const defaultProxyOptionNames = [
        '自动选择',
        'DIRECT',
        '负载均衡-轮询',
        '负载均衡-一致性哈希',
        ...regionSelectGroupNames,
        ...rawProxyNodeNames,
    ];

    aiProxyOptionNames.push(...aiAutoProxyNodeNames);

    const defaultProxyGroupItem = createSelectGroupItem(
        '默认代理',
        defaultProxyOptionNames,
        `${ICON_BASE}/Default.png`
    );
    const aiProxyGroupItem = createSelectGroupItem('AI', aiProxyOptionNames, `${ICON_BASE}/OpenAI.png`);
    const catchAllProxyGroupItem = createSelectGroupItem('漏网之鱼', commonProxyOptionNames);

    SERVICE_GROUP_META_LIST.forEach(([groupName, iconFileName]) => {
        serviceProxyGroupItems.push(
            createSelectGroupItem(groupName, commonProxyOptionNames, `${ICON_BASE}/${iconFileName}`)
        );
    });

    autoProxyGroupItems.unshift(
        createUrlTestGroupItem('自动选择', autoTestProxyNodeNames),
        createUrlTestGroupItem('自动选择-AI', aiAutoProxyNodeNames),
        createLoadBalanceGroupItem('负载均衡-轮询', autoTestProxyNodeNames, 'round-robin'),
        createLoadBalanceGroupItem('负载均衡-一致性哈希', autoTestProxyNodeNames, 'consistent-hashing'),
    );

    config['proxy-groups'] = [
        defaultProxyGroupItem,
        aiProxyGroupItem,
        ...serviceProxyGroupItems,
        catchAllProxyGroupItem,
        ...regionSelectGroupItems,
        ...autoProxyGroupItems,
    ];

    // ===================================
    // 规则集提供者（Rule Providers）
    // ===================================

    // 定义外部规则集，方便集中管理和更新
    config['rule-providers'] = {
        // Loyalsoldier
        'reject': {
            type: 'http',
            behavior: 'domain',
            url: 'https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/reject.txt',
            interval: rulesetUpdateInterval // 每天更新
        },
        'domain-proxy': {
            type: 'http',
            format: 'mrs',
            behavior: 'domain',
            url: 'https://raw.githubusercontent.com/Huffer342-WSH/routing-rules/refs/heads/rules/domain/proxy.mrs',
            interval: rulesetUpdateInterval
        },
        'domain-direct': {
            type: 'http',
            format: 'mrs',
            behavior: 'domain',
            url: 'https://raw.githubusercontent.com/Huffer342-WSH/routing-rules/refs/heads/rules/domain/direct.mrs',
            interval: rulesetUpdateInterval
        },
        'domain-ai': {
            type: 'http',
            format: 'mrs',
            behavior: 'domain',
            url: "https://raw.githubusercontent.com/Huffer342-WSH/routing-rules/refs/heads/rules/domain/category-ai-chat-!cn.mrs",
            interval: rulesetUpdateInterval
        }
    };

    // ===================================
    // 规则列表（Rules）
    // ===================================
    const hasJapanGroup = Array.isArray(config['proxy-groups']) &&
        config['proxy-groups'].some(group => group && group.name === '节点组-🇯🇵日本');

    const newRules = [
        // -----------------------------------
        // 1. 强制直连/代理规则（覆盖规则集）
        // -----------------------------------

        // 战网
        'PROCESS-NAME,Battle.net,战网',
        'PROCESS-NAME,Battle.net.exe,战网',
        'DOMAIN-SUFFIX,battle.net,战网',
        'DOMAIN-SUFFIX,blizzard.com,战网',

        // Steam (社区代理，下载直连)
        'DOMAIN-SUFFIX,alipay.com,DIRECT',        // 支付直连
        'DOMAIN-SUFFIX,alipayobjects.com,DIRECT',
        'DOMAIN,steamcommunity.com,默认代理',
        'DOMAIN,api.steampowered.com,默认代理',
        'PROCESS-NAME,steamwebhelper,默认代理',
        'PROCESS-NAME,steamwebhelper.exe,默认代理',
        'PROCESS-NAME,steam,DIRECT',               // Steam 主进程直连
        'PROCESS-NAME,steam.exe,DIRECT',

        // epic
        'DOMAIN,fastly-download.epicgames.com,DIRECT',
        'PROCESS-NAME,EpicWebHelper.exe,默认代理',
        'PROCESS-NAME,EpicGamesLauncher.exe,DIRECT',

        // Matlab (安装/激活直连，部分服务走代理)
        'PROCESS-NAME,MathWorksProductInstaller,DIRECT',
        'PROCESS-NAME,MathWorksProductInstaller.exe,DIRECT',
        'PROCESS-NAME,MATLABWindow,DIRECT',
        'PROCESS-NAME,MATLABWindow.exe,DIRECT',
        'DOMAIN,esd.mathworks.com,DIRECT',
        'DOMAIN-SUFFIX,mathworks.com,默认代理',

        // 雀魂
        'DOMAIN,game.maj-soul.com,默认代理',
        'DOMAIN-KEYWORD,majsoul,DIRECT',

        // 柚子社（仅当存在“节点组-🇯🇵日本”时启用）
        ...(hasJapanGroup ? [
            'DOMAIN-SUFFIX,yuzu-soft.com,节点组-🇯🇵日本',
            'DOMAIN-SUFFIX,dmm.co.jp,节点组-🇯🇵日本',
        ] : []),

        // -----------------------------------
        // 2. 外部规则集调用（Rule-Set Providers）
        // -----------------------------------
        // 服务专用组规则
        'GEOSITE,telegram,Telegram',
        'GEOSITE,microsoft@cn,微软服务 - CN',
        'GEOSITE,microsoft,微软服务',

        // AI
        'RULE-SET,domain-ai,AI',
        'IP-CIDR,160.79.104.0/21,AI', //claude
        'IP-CIDR6,2607:6bc0::/32,AI',
        'IP-ASN,399358,AI',

        // 通用代理
        'RULE-SET,reject,REJECT',
        'RULE-SET,domain-direct,DIRECT',
        'GEOSITE,private,DIRECT',
        'RULE-SET,domain-proxy,默认代理',
        'GEOSITE,gfw,默认代理',
        'GEOSITE,geolocation-!cn,默认代理',

        // IP
        'GEOIP,private,DIRECT,no-resolve',
        'GEOIP,telegram,Telegram',
        'GEOIP,LAN,DIRECT',
        'GEOIP,CN,DIRECT',

        // 任何未匹配的流量都走 '漏网之鱼' 代理组
        'MATCH,漏网之鱼'
    ];

    config['rules'] = newRules;

    // 返回修改后的配置
    return config;
}
