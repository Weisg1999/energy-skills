/**
 * 五张核心架构图的人工语义化渲染。
 *
 * 输入仍是 Markdown 代码围栏中的原始示意图；这里只负责把已确认的结构
 * 重排为 HTML。每个规格都带 anchors，源图的标题或关键节点改名后构建会
 * 直接失败，避免语义版与原文悄悄漂移。
 */

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const chips = (items, cls = 'arch-chip') => (items || []).map((item) => `<span class="${cls}">${esc(item)}</span>`).join('');

function head(kicker, meta, title) {
  return `<figcaption class="diagram-head">
    <span class="diagram-head-row">
      <span class="diagram-kicker">${esc(kicker)}</span>
      <span class="diagram-meta">${esc(meta)}</span>
    </span>
    <span class="diagram-title">${esc(title)}</span>
  </figcaption>`;
}

function connector(label = '') {
  return `<div class="arch-connector"><span class="arch-connector-mark" aria-hidden="true">↕</span>${label ? `<span>${esc(label)}</span>` : ''}</div>`;
}

function layer({ zone, tag, tone, title, items, pipeline, modules }) {
  return `<section class="arch-layer" data-tone="${tone}">
    <div class="arch-layer-head">
      <span class="arch-zone">${esc(zone)}</span>
      ${tag ? `<span class="arch-tag">${esc(tag)}</span>` : ''}
    </div>
    <div class="arch-layer-body">
      <span class="arch-layer-title">${esc(title)}</span>
      ${items && items.length ? `<div class="arch-chips">${chips(items)}</div>` : ''}
      ${pipeline && pipeline.length ? `<div class="arch-inline-flow">${pipeline.map((item, i) => `${i ? '<span class="arch-inline-arrow" aria-hidden="true">→</span>' : ''}<span>${esc(item)}</span>`).join('')}</div>` : ''}
      ${modules && modules.length ? `<div class="arch-modules">${modules.map((mod) => `<div class="arch-module"><span class="arch-module-title">${esc(mod.title)}</span><div class="arch-chips">${chips(mod.items)}</div></div>`).join('')}</div>` : ''}
    </div>
  </section>`;
}

function renderScada() {
  const layers = [
    {
      zone: '管理信息区', tag: '安全 III / IV', tone: 'teal', title: 'VPP 云平台',
      items: ['交易申报', '结算对账', '经营看板', '运维工单'],
    },
    {
      zone: '安全接入区', tag: '受控边界', tone: 'amber', title: '代理转发 · 端到端认证',
      items: ['不直连生产控制区'],
    },
    {
      zone: '生产控制区', tag: '安全 I / II', tone: 'slate', title: '实时监控与站控',
      pipeline: ['SCADA 前置（FEP 双机）', '实时库', '历史/时序库', '告警/HMI'],
      modules: [
        { title: '站控层 / 边缘网关', items: ['点表映射', '协议转换', '本地联锁', '断点续传'] },
        { title: '通信', items: ['104 / 61850 / Modbus'] },
        { title: '时钟同步', items: ['北斗 / NTP / PTP'] },
      ],
    },
    {
      zone: '现场设备层', tag: '现场', tone: 'blue', title: '设备与测点',
      items: ['测控', '保护', '关口表', 'BMS', 'PCS', '逆变器', '充电桩', 'PLC'],
    },
  ];
  const links = [
    '受控上行（隔离装置） / 云边下行（TLS/APN，经安全接入区）',
    '纵向加密 / 受控通道',
    '现场总线 / 工业以太网 / 串口',
  ];
  return `<figure class="arch-diagram arch-layered" data-arch-id="scada-zones" aria-label="SCADA 分层安全架构">
    ${head('安全分区 · ZONES', '4 个安全区', 'SCADA 分层安全架构')}
    <div class="arch-layers">${layers.map((item, i) => `${i ? connector(links[i - 1]) : ''}${layer(item)}`).join('')}</div>
    <p class="diagram-note arch-legend"><span class="arch-legend-label">图例：</span><span><b aria-hidden="true">↕</b> 数据/控制流</span><span>分区边界按安全区划分</span><span><b>FEP</b> 前置处理器</span></p>
  </figure>`;
}

function renderVppPipeline() {
  const nodes = [
    { title: '现场表计/RTU/PLC', note: '设备状态', dir: 'up' },
    { title: '边缘网关', note: '本地自治', dir: 'down' },
    { title: '站级 SCADA/EMS', note: '市场报价/结算', dir: 'down' },
    { title: 'VPP 平台' },
    { title: '交易/调度系统' },
  ];
  return `<figure class="arch-diagram arch-pipeline-figure" data-arch-id="vpp-data-chain" aria-label="VPP 与 EMS 数据链路">
    ${head('数据链路 · DATA FLOW', '5 个节点', 'VPP / EMS 数据链路')}
    <div class="arch-pipeline">${nodes.map((node, i) => `${i ? '<span class="arch-pipe-arrow" aria-hidden="true">→</span>' : ''}<article class="arch-node">
      <span class="arch-node-index" aria-hidden="true">${String(i + 1).padStart(2, '0')}</span>
      <span class="arch-node-title">${esc(node.title)}</span>
      ${node.note ? `<span class="arch-node-note" data-dir="${node.dir}"><span aria-hidden="true">${node.dir === 'up' ? '↑' : '↓'}</span>${esc(node.note)}</span>` : ''}
    </article>`).join('')}</div>
  </figure>`;
}

function renderV2g() {
  const nodes = [
    { title: '车辆 BMS', detail: 'SOC/温度' },
    { title: '双向充电桩/直流桩', detail: '功率/计量/通信' },
    { title: '台区/配变/保护', detail: '容量/电压/谐波' },
    { title: '聚合平台/VPP', detail: '预测/策略/结算' },
  ];
  return `<figure class="arch-diagram arch-v2g" data-arch-id="v2g-chain" aria-label="V2G 技术架构">
    ${head('技术架构 · V2G', '4 个环节', 'V2G 技术架构')}
    <div class="arch-v2g-row">${nodes.map((node, i) => `${i ? '<span class="arch-bi-arrow" aria-hidden="true">↔</span>' : ''}<article class="arch-node arch-node-detail">
      <span class="arch-node-index" aria-hidden="true">${String(i + 1).padStart(2, '0')}</span>
      <span class="arch-node-title">${esc(node.title)}</span>
      <span class="arch-node-detail">${esc(node.detail)}</span>
    </article>`).join('')}</div>
    <div class="arch-v2g-drop"><span aria-hidden="true">↕</span></div>
    <article class="arch-upstream-node">
      <span class="arch-node-title">电网调度 / 交易中心 / 负荷管理中心</span>
      <div class="arch-chips">${chips(['邀约', '出清', '考核', '结算'], 'arch-chip arch-chip-strong')}</div>
    </article>
    <p class="sr-only">车辆、充电桩、台区与聚合平台之间为双向连接。</p>
  </figure>`;
}

function renderQuantReference() {
  const stages = [
    {
      title: '源系统',
      items: ['交易中心', '调度', '气象', '计量', 'ERP', '信用平台'],
      link: 'API / 文件 / 消息',
    },
    {
      title: '接入层',
      items: ['采集、解析、校验、去重、补采、血缘'],
    },
    {
      title: '数据层',
      items: ['数据湖', '时序库', '特征库', '规则库', '合约库'],
    },
    {
      title: '服务层',
      services: [
        { title: '预测服务', items: ['价格/负荷/出力'] },
        { title: '策略/优化服务', items: ['报价/组合/储能'] },
        { title: '校验/审批服务', items: ['规则/限额/双人复核'] },
      ],
    },
    {
      title: '申报网关',
      items: ['回执/改单/留痕'],
    },
    {
      title: '结果',
      items: ['出清结果', '结算单', '计量数据'],
    },
    {
      title: '分析闭环',
      items: ['对账', '归因', '风控', '绩效'],
    },
  ];
  return `<figure class="arch-diagram arch-reference" data-arch-id="quant-reference" aria-label="量化交易参考架构">
    ${head('参考架构 · REFERENCE', '7 个层次 · 闭环', '量化交易参考架构')}
    <div class="arch-stages">${stages.map((stage, i) => `${i ? `<div class="arch-stage-link"><span aria-hidden="true">↓</span>${stages[i - 1].link ? `<small>${esc(stages[i - 1].link)}</small>` : ''}</div>` : ''}<section class="arch-stage">
      <span class="arch-stage-index" aria-hidden="true">${String(i + 1).padStart(2, '0')}</span>
      <div class="arch-stage-body">
        <span class="arch-stage-title">${esc(stage.title)}</span>
        ${stage.items ? `<div class="arch-chips">${chips(stage.items)}</div>` : ''}
        ${stage.services ? `<div class="arch-services">${stage.services.map((svc) => `<div class="arch-service"><span>${esc(svc.title)}</span><small>${esc(svc.items.join(' / '))}</small></div>`).join('')}</div>` : ''}
      </div>
    </section>`).join('')}</div>
    <div class="arch-feedback"><span class="arch-feedback-icon" aria-hidden="true">↺</span><span>反馈到规则、模型、限额</span></div>
  </figure>`;
}

function renderResourceMap() {
  const categories = [
    { title: '电源侧', tone: 'teal', items: ['煤电灵活性', '气电顶峰', '抽水蓄能', '新能源+储能', '可中断新能源'] },
    { title: '电网侧', tone: 'amber', items: ['独立储能', 'SVG/调相机', '互联互济', '配网重构', '需求侧资源库'] },
    { title: '负荷侧', tone: 'blue', items: ['工业可中断/可转移', '楼宇空调/居民', '数据中心/算力', '电解铝/钢铁/水泥', '充电桩/换电站'] },
    { title: '储侧', tone: 'plum', items: ['用户侧储能', 'V2G', '备电/共享', '移动储能', '热储能'] },
  ];
  return `<figure class="arch-diagram arch-resource" data-arch-id="flex-resource-map" aria-label="灵活性资源地图">
    ${head('资源地图 · RESOURCE MAP', '4 类 · 20 项', '灵活性资源地图')}
    <div class="arch-resource-root"><span>灵活性资源</span><small>电源侧 · 电网侧 · 负荷侧 · 储侧</small></div>
    <div class="arch-resource-grid">${categories.map((cat) => `<section class="arch-resource-card" data-tone="${cat.tone}">
      <div class="arch-resource-head"><span>${esc(cat.title)}</span><small>${cat.items.length}</small></div>
      <ul class="arch-resource-list">${cat.items.map((item) => `<li>${esc(item)}</li>`).join('')}</ul>
    </section>`).join('')}</div>
  </figure>`;
}

const SPECS = [
  {
    id: 'scada-zones',
    fingerprint: (body) => body.includes('管理信息区（安全 III / IV）') && body.includes('SCADA 前置（FEP 双机）'),
    anchors: ['管理信息区（安全 III / IV）', '安全接入区', '生产控制区（安全 I / II）', '现场设备层', 'SCADA 前置（FEP 双机）', '站控层 / 边缘网关', '104 / 61850 / Modbus', '北斗 / NTP / PTP'],
    render: renderScada,
  },
  {
    id: 'vpp-data-chain',
    fingerprint: (body) => body.includes('现场表计/RTU/PLC') && body.includes('交易/调度系统') && body.includes('本地自治'),
    anchors: ['现场表计/RTU/PLC', '边缘网关', '站级 SCADA/EMS', 'VPP 平台', '交易/调度系统', '设备状态', '本地自治', '市场报价/结算'],
    render: renderVppPipeline,
  },
  {
    id: 'v2g-chain',
    fingerprint: (body) => body.includes('车辆 BMS') && body.includes('双向充电桩/直流桩'),
    anchors: ['车辆 BMS', '双向充电桩/直流桩', '台区/配变/保护', '聚合平台/VPP', '电网调度 / 交易中心 / 负荷管理中心', '邀约 / 出清 / 考核 / 结算'],
    render: renderV2g,
  },
  {
    id: 'quant-reference',
    fingerprint: (body) => body.includes('源系统：交易中心') && body.includes('申报网关'),
    anchors: ['源系统：交易中心', '接入层：采集', '数据层：数据湖', '预测服务', '策略/优化服务', '校验/审批服务', '申报网关', '对账 / 归因 / 风控 / 绩效', '反馈到规则、模型、限额'],
    render: renderQuantReference,
  },
  {
    id: 'flex-resource-map',
    fingerprint: (body) => body.includes('┌') && body.includes('灵活性资源') && body.includes('煤电灵活性') && body.includes('数据中心/算力'),
    anchors: ['灵活性资源', '煤电灵活性', '独立储能', '工业可中断/可转移', '用户侧储能', '数据中心/算力', '移动储能'],
    render: renderResourceMap,
  },
];

export const CURATED_ARCH_IDS = SPECS.map((spec) => spec.id);

export function renderCuratedArchitecture(body) {
  for (const spec of SPECS) {
    if (!spec.fingerprint(body)) continue;
    const missing = spec.anchors.filter((anchor) => !body.includes(anchor));
    if (missing.length) throw new Error(`架构图 ${spec.id} 的源图已变化，请同步 semantic spec：${missing.join('、')}`);
    return spec.render();
  }
  return null;
}
