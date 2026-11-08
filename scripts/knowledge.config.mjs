/**
 * 知识中心的结构配置。模块本身的事实（标题、摘要、行数、标签）一律写在
 * knowledge/*.md 的 frontmatter 里；这里只放分区、导航顺序与固定文案。
 */

export const site = {
  skills: 9,
  coverage: '电力系统通识、电力现货与省间交易、电价、新能源与并网、储能与 EMS、零碳园区、碳市场、虚拟电厂、需求响应与市场风险信用结算',
};

export const sections = [
  {
    id: 'foundation',
    cat: 'foundation',
    num: '04 / BASE',
    title: '通识与经济学',
    navLabel: '通识与经济学',
    comment: '03 Foundation',
    desc: '先建立物理与制度直觉：电从哪里来、谁在管、为什么改革，以及市场为什么需要集中调度兜底。{n}份笔记，适合零基础起步。',
  },
  {
    id: 'spot',
    cat: 'spot',
    num: '05 / SPOT',
    title: '电力现货与省间交易',
    navLabel: '现货与省间交易',
    comment: '04 Spot',
    desc: '从《电力现货市场101问》的基础、出清结算与技术支持系统，到《电力现货市场实务》的国内外实践，再到 2026 年省间与跨区交易、量化报价风控与风险信用结算。{n}份笔记覆盖机制、算例、治理与制度链路。',
  },
  {
    id: 'price',
    cat: 'price',
    num: '06 / PRICE',
    title: '电价',
    navLabel: '电价',
    comment: '05 Price',
    desc: '从历史沿革、制度谱系到 2026 年现行文件与用户侧查证，再加一套国际比较方法。回答“电价多少”之前，先把环节与口径定下来。',
  },
  {
    id: 'renewable',
    cat: 'renewable',
    num: '07 / RENEWABLE',
    title: '新能源与并网',
    navLabel: '新能源与并网',
    comment: '06 Renewable',
    desc: '项目侧看资源、机制电价与 LCOE；运行侧看涉网性能、考核电量与免考。{n}份笔记把“能不能建”和“建完怎么被考核”接起来。',
  },
  {
    id: 'storage',
    cat: 'storage',
    num: '08 / STORAGE',
    title: '储能与 EMS',
    navLabel: '储能与 EMS',
    comment: '07 Storage',
    desc: '技术侧看路线、安全与构网；投资侧看政策、成本、时长折算与考核；调度侧看 MILP、多市场堆叠、SOC/退化与 MPC。两份 EMS 笔记分别覆盖独立储能与微网。',
  },
  {
    id: 'park',
    cat: 'park',
    num: '09 / PARK',
    title: '综合能源与零碳园区',
    navLabel: '零碳园区',
    comment: '08 Park',
    desc: '把“零碳园区、绿电直连、源网荷储、微网、VPP”几个近义词拆开，再用一套合成算例回答“直连能不能算得过账”。',
  },
  {
    id: 'carbon',
    cat: 'carbon',
    num: '10 / CARBON',
    title: '碳市场与碳管理',
    navLabel: '碳市场与碳管理',
    comment: '09 Carbon',
    desc: '从碳定价与 EU ETS、三层核算与电力排放因子，到 2026 年履约参数、CCER、碳金融与 CBAM。机制、方法与操作层分开读。',
  },
  {
    id: 'vpp',
    cat: 'vpp',
    num: '11 / VPP',
    title: '虚拟电厂',
    navLabel: '虚拟电厂',
    comment: '10 VPP',
    desc: '一本成书于 2020 年的系统读物，补齐概念辨析、资源测算、省级样板与三阶段演进；新增需求响应与车网互动模块，补上基线、考核结算与 V2G 入市。',
  },
  {
    id: 'index',
    cat: 'index',
    num: '12 / INDEX',
    title: '索引、查证与工具',
    navLabel: '索引与查证',
    comment: '11 Index',
    desc: '回答前的四个入口：文号与口径、省级状态、高频问答、英文摘要。先查状态与来源级别，再下结论。',
  },
  {
    id: 'research',
    cat: 'research',
    num: '13 / RESEARCH',
    title: '调研底稿',
    navLabel: '调研底稿',
    comment: '12 Research',
    desc: '{n}份按时间归档的增量调研。它们保留信源日期、核实状态与冲突口径，是“为什么这么写”的证据链；正式引用仍以索引与原文为准。',
  },
];

/** 侧栏顺序与计数来源：total / section / 固定数字。 */
export const nav = [
  { href: '#top', n: '00', label: '总览', count: 'total' },
  { href: '#all', n: '01', label: '模块检索', count: 'total' },
  { href: '#map', n: '02', label: '知识地图', count: 5 },
  { href: '#atlas', n: '03', label: '专题图谱', count: 7 },
  ...sections.map((s, i) => ({
    href: `#${s.id}`,
    n: String(i + 4).padStart(2, '0'),
    label: s.navLabel,
    count: 'section',
    section: s.id,
  })),
  { href: '#method', n: '14', label: '使用与口径', count: 'skills' },
];
