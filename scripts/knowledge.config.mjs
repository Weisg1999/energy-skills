/**
 * 知识中心的结构配置。模块本身的事实（标题、摘要、行数、标签）一律写在
 * knowledge/*.md 的 frontmatter 里；这里只放分区、导航顺序与固定文案。
 */

export const site = {
  skills: 9,
  repository: 'https://github.com/Weisg1999/energy-skills',
  coverage: '电力系统通识、电力现货与省间交易、海外十一市场（澳/德/英/意/西/法/荷/波/比·北欧/美/日）、横向专题（并网合规、容量机制、辅助服务、储能收益与数据源、PPA/绿证、同口径快照与投决日历）、电价、新能源与并网、储能、EMS 与 SCADA 数据链路、零碳园区、碳市场与绿证/CCER/CBAM 衔接、虚拟电厂、需求响应与市场风险信用结算、术语与口径字典',
};

export const sections = [
  {
    id: 'foundation',
    cat: 'foundation',
    num: '01 · BASE',
    title: '通识与经济学',
    navLabel: '通识与经济学',
    comment: '03 Foundation',
    desc: '先建立物理与制度直觉：电从哪里来、谁在管、为什么改革，以及市场为什么需要集中调度兜底。{n}份笔记，适合零基础起步；篇末附 2026 年装机、市场主体与现货省份快照。',
  },
  {
    id: 'spot',
    cat: 'spot',
    num: '02 · SPOT',
    title: '电力现货与省间交易',
    navLabel: '现货与省间交易',
    comment: '04 Spot',
    desc: '从《电力现货市场101问》的基础、出清结算与技术支持系统，到《电力现货市场实务》的国内外实践，再到 2026 年省间与跨区交易、量化报价风控与风险信用结算。{n}份笔记覆盖机制、算例、治理与制度链路。',
  },
  {
    id: 'intl',
    cat: 'intl',
    num: '03 · GLOBAL',
    title: '海外市场',
    navLabel: '海外市场',
    comment: '05 Global',
    desc: '澳大利亚 NEM、德国、英国、意大利、西班牙、法国、荷兰、波兰、比利时/北欧、美国（ERCOT/PJM/CAISO）与日本是十一套设计取向不同的市场：澳洲用区域价 + 5 分钟结算，德国用欧盟耦合 + 平衡市场，英国用单一市场 + 平衡机制 + 容量市场，意大利用七个报价区 + MACSE 长周期储能拍卖，西班牙用伊比利亚双区 + 15 分钟结算 + 2026 年容量市场，法国用核电主导 + RTE 单一买方容量机制 + ARENH 退场，荷兰用单一报价区 + 无容量市场 + 拥堵接入，波兰用容量市场 + OZE 拍卖 + 储能补贴，比利时/北欧用 CRM 与分区水电市场，美国用 ISO/RTO 拼图 + 能量-only/容量市场/RA 三种范式，日本用 30 分钟现货 + 容量市场 + LTDA。{n}份笔记只讲交易与结算，不替代当地法律意见。',
  },
  {
    id: 'cross',
    cat: 'cross',
    num: '04 · CROSS',
    title: '横向专题',
    navLabel: '横向专题',
    comment: '06 Cross',
    desc: '把散落在十一市场模块里的“同一类问题”横向拉平：海外并网与合规、容量机制、辅助服务与平衡市场、储能收益建模与数据源、跨国 PPA/绿证/tolling、同口径快照与投决日历。{n}份笔记不重复单市场规则，只做跨市场对照、投决口径与查证入口。',
  },
  {
    id: 'price',
    cat: 'price',
    num: '05 · PRICE',
    title: '电价',
    navLabel: '电价',
    comment: '07 Price',
    desc: '从历史沿革、制度谱系到 2026 年现行文件与用户侧查证，再加一套国际比较方法。回答“电价多少”之前，先把环节与口径定下来。',
  },
  {
    id: 'renewable',
    cat: 'renewable',
    num: '06 · RENEWABLE',
    title: '新能源与并网',
    navLabel: '新能源与并网',
    comment: '08 Renewable',
    desc: '项目侧看资源、机制电价与 LCOE；运行侧看涉网性能、考核电量与免考。{n}份笔记把“能不能建”和“建完怎么被考核”接起来。',
  },
  {
    id: 'storage',
    cat: 'storage',
    num: '07 · STORAGE',
    title: '储能与 EMS',
    navLabel: '储能与 EMS',
    comment: '09 Storage',
    desc: '技术侧看路线、安全与构网；投资侧看政策、成本、时长折算与考核；调度侧看 MILP、多市场堆叠、SOC/退化与 MPC；数据侧看 SCADA 点表、通信、时延、时钟同步与安全防护。两份 EMS 笔记分别覆盖独立储能与微网。',
  },
  {
    id: 'park',
    cat: 'park',
    num: '08 · PARK',
    title: '综合能源与零碳园区',
    navLabel: '零碳园区',
    comment: '10 Park',
    desc: '把“零碳园区、绿电直连、源网荷储、微网、VPP”几个近义词拆开，再用一套合成算例回答“直连能不能算得过账”。',
  },
  {
    id: 'carbon',
    cat: 'carbon',
    num: '09 · CARBON',
    title: '碳市场与碳管理',
    navLabel: '碳市场与碳管理',
    comment: '11 Carbon',
    desc: '从碳定价与 EU ETS、三层核算与电力排放因子，到 2026 年履约参数、CCER、碳金融与 CBAM，并附“配额缺口 + CCER 5% + CBAM”履约成本算例。机制、方法与操作层分开读。',
  },
  {
    id: 'vpp',
    cat: 'vpp',
    num: '10 · VPP',
    title: '虚拟电厂',
    navLabel: '虚拟电厂',
    comment: '12 VPP',
    desc: '2026 版核心模块补齐聚合资源、准入接入、云边控制、市场参与、结算分成、商业模式与省级门槛；另有 2020 年系统读物与需求响应/车网互动模块，分别补概念源流与基线考核。',
  },
  {
    id: 'index',
    cat: 'index',
    num: '11 · INDEX',
    title: '索引、查证与工具',
    navLabel: '索引与查证',
    comment: '13 Index',
    desc: '回答前的四个入口：文号与口径、省级状态、高频问答、英文摘要。先查状态与来源级别，再下结论。',
  },
  {
    id: 'research',
    cat: 'research',
    num: '12 · RESEARCH',
    title: '调研底稿',
    navLabel: '调研底稿',
    comment: '14 Research',
    desc: '{n}份按时间归档的增量调研。它们保留信源日期、核实状态与冲突口径，是“为什么这么写”的证据链；正式引用仍以索引与原文为准。',
  },
];

/**
 * 配套技能：只登记展示信息，SKILL.md 自身 frontmatter 保持不动，
 * 以免破坏技能包格式。构建时按中英两份文件各生成一个阅读页。
 */
export const skillDocs = [
  {
    slug: 'electricity-trading-expert',
    title: '电力交易专家',
    titleEn: 'Electricity Trading Expert',
    summary: '现货报价、结算、风险与市场分析',
    summaryEn: 'Spot bidding, settlement, risk and market analysis',
    tags: ['技能', '现货', '结算', '风控'],
    tagsEn: ['skill', 'spot', 'settlement', 'risk'],
    modules: ['m-spot-a', 'm-spot-b', 'm-spot-c', 'm-spot-interprovincial', 'm-quant-risk', 'm-risk-credit'],
  },
  {
    slug: 'virtual-power-plant',
    title: '虚拟电厂专家',
    titleEn: 'Virtual Power Plant Expert',
    summary: '聚合、响应、市场参与与运营',
    summaryEn: 'Aggregation, demand response, market participation and operations',
    tags: ['技能', 'VPP', '聚合', '商业模式'],
    tagsEn: ['skill', 'VPP', 'aggregation', 'business model'],
    modules: ['m-vpp-core', 'm-vpp-book', 'm-dr-v2g'],
  },
  {
    slug: 'carbon-asset-expert',
    title: '碳资产管理专家',
    titleEn: 'Carbon Asset Management Expert',
    summary: '履约、CCER、碳足迹与碳金融',
    summaryEn: 'Compliance, CCER, carbon footprint and carbon finance',
    tags: ['技能', '履约', 'CCER', 'CBAM'],
    tagsEn: ['skill', 'compliance', 'CCER', 'CBAM'],
    modules: ['m-carbon-trade', 'm-carbon-mgmt', 'm-carbon-asset', 'm-carbon-link'],
  },
  {
    slug: 'storage-investment-operations',
    title: '储能投资与运营',
    titleEn: 'Storage Investment & Operations',
    summary: '收益堆叠、投决、退化与考核',
    summaryEn: 'Revenue stacking, investment decisions, degradation and assessment',
    tags: ['技能', '储能', '投决', 'LCOS'],
    tagsEn: ['skill', 'storage', 'investment', 'LCOS'],
    modules: ['m-storage-invest', 'm-storage-tech', 'm-storage-ems'],
  },
  {
    slug: 'renewable-project-development',
    title: '新能源开发与并网',
    titleEn: 'Renewable Project Development & Grid Connection',
    summary: '资源、LCOE、机制电价与并网',
    summaryEn: 'Resources, LCOE, mechanism pricing and grid connection',
    tags: ['技能', '新能源', 'LCOE', '并网'],
    tagsEn: ['skill', 'renewables', 'LCOE', 'grid'],
    modules: ['m-renewable', 'm-grid', 'm-price-policy'],
  },
  {
    slug: 'spot-bidding-quant',
    title: '现货报价量化',
    titleEn: 'Spot Bidding Quant',
    summary: '预测、报价、仿真与回测',
    summaryEn: 'Forecasting, bidding, simulation and backtesting',
    tags: ['技能', '预测', '报价', '回测'],
    tagsEn: ['skill', 'forecast', 'bidding', 'backtest'],
    modules: ['m-quant-risk', 'm-spot-b', 'm-spot-c'],
  },
  {
    slug: 'ems-dispatch',
    title: 'EMS 优化调度',
    titleEn: 'EMS Dispatch',
    summary: '96 点调度、SOC、需量与可交付性',
    summaryEn: '96-interval dispatch, SOC, demand charges and deliverability',
    tags: ['技能', 'EMS', 'SOC', '需量'],
    tagsEn: ['skill', 'EMS', 'SOC', 'demand charge'],
    modules: ['m-storage-ems', 'm-micro-ems', 'm-scada'],
  },
  {
    slug: 'tariff-bill-optimization',
    title: '电价与电费优化',
    titleEn: 'Tariff & Bill Optimization',
    summary: '账单科目、基本电费、分时与套餐比价',
    summaryEn: 'Bill line items, demand charges, TOU and package comparison',
    tags: ['技能', '电费', '两部制', '套餐'],
    tagsEn: ['skill', 'tariff', 'two-part', 'packages'],
    modules: ['m-price-system', 'm-price-policy', 'm-price-history'],
  },
  {
    slug: 'retail-electricity-risk',
    title: '售电零售与风险',
    titleEn: 'Retail Electricity Sales & Risk',
    summary: '套餐定价、客户组合、偏差与保函',
    summaryEn: 'Package pricing, customer portfolio, deviation and guarantees',
    tags: ['技能', '零售', '偏差', '保函'],
    tagsEn: ['skill', 'retail', 'deviation', 'guarantee'],
    modules: ['m-risk-credit', 'm-province', 'm-vpp-core'],
  },
].map((item, i) => ({ ...item, order: i + 1 }));

/** 阅读页英文侧栏标题；首页仍只使用中文。 */
export const sectionTitlesEn = {
  foundation: 'Foundations & economics',
  spot: 'Spot & interprovincial trading',
  intl: 'Overseas markets',
  cross: 'Cross-cutting topics',
  price: 'Electricity tariffs',
  renewable: 'Renewables & grid connection',
  storage: 'Storage & EMS',
  park: 'Integrated energy & zero-carbon parks',
  carbon: 'Carbon markets & management',
  vpp: 'Virtual power plants',
  index: 'Index & verification',
  research: 'Research records',
};

/**
 * 侧栏只保留六个页面级入口；十二个内容分区改由首页分类筛选承载。
 * 顺序必须与首页 DOM 的真实顺序一致，滚动高亮才能单调推进。
 */
export const nav = [
  { href: '#top', n: '00', label: '总览', count: 'total' },
  { href: '#all', n: '01', label: '模块检索', count: 'total' },
  { href: '#map', n: '02', label: '知识地图', count: 6 },
  { href: '#atlas', n: '03', label: '专题图谱', count: 8 },
  { href: '#skills', n: '04', label: '配套技能', count: 'skills' },
  { href: '#method', n: '05', label: '使用与口径' },
];
