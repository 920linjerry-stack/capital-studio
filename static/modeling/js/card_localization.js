// V5.9.6 Card Localization & Visual Readability — deterministic local display map.
//
// Pure front-end, deterministic, offline display localization for the frozen
// 100-company US deck (V5.11.2). It changes NO truth: financial fields, source_meta, the
// pairs payload, precompute, the A/D engine, Match Points and the robot strategy
// are all untouched. This module only maps a company card to a player-friendly
// Chinese display name + Chinese sector for the card renderers, with a safe
// fallback chain so an unknown / future ticker never crashes and never renders
// "undefined".
//
// Maintainability: this is the SINGLE source of the display mapping — renderers
// in arena.js / arena_match.js / arena_play.js all read it instead of hardcoding
// strings of their own. The Chinese sector is a game-readability label (e.g.
// NVDA -> 半导体, MCD -> 餐饮), not an academic GICS translation, and it is NOT a
// tier / rating and never enters any economic, viability or scoring layer.
//
// No network, no LLM, no randomness, no storage, no per-user state.
(function () {
  "use strict";

  // Per-ticker display: { name = Chinese (or stable brand) short name, sector =
  // Chinese game-readability industry label }. Keyed by UPPERCASE ticker. Every
  // ticker in the current real deck is covered (a coverage test enforces this);
  // a few globally-Latin brands (Meta / Visa / Adobe / Salesforce / ServiceNow /
  // AMD / RTX) keep their brand as the stable display name on purpose.
  const COMPANY_CN = {
    AAPL:  { name: "苹果",         sector: "科技" },
    MSFT:  { name: "微软",         sector: "科技" },
    GOOGL: { name: "谷歌",         sector: "通信服务" },
    AMZN:  { name: "亚马逊",       sector: "电商 · 云计算" },
    META:  { name: "Meta",         sector: "社交媒体" },
    NVDA:  { name: "英伟达",       sector: "半导体" },
    DIS:   { name: "迪士尼",       sector: "娱乐传媒" },
    HD:    { name: "家得宝",       sector: "家居零售" },
    AVGO:  { name: "博通",         sector: "半导体" },
    ORCL:  { name: "甲骨文",       sector: "企业软件" },
    CRM:   { name: "Salesforce",   sector: "企业软件" },
    COST:  { name: "好市多",       sector: "零售" },
    CAT:   { name: "卡特彼勒",     sector: "工程机械" },
    XOM:   { name: "埃克森美孚",   sector: "能源" },
    V:     { name: "Visa",         sector: "支付网络" },
    MA:    { name: "万事达",       sector: "支付网络" },
    ADBE:  { name: "Adobe",        sector: "创意软件" },
    NOW:   { name: "ServiceNow",   sector: "企业软件" },
    PANW:  { name: "Palo Alto",    sector: "网络安全" },
    AMD:   { name: "AMD",          sector: "半导体" },
    QCOM:  { name: "高通",         sector: "半导体" },
    AMAT:  { name: "应用材料",     sector: "半导体设备" },
    TMO:   { name: "赛默飞世尔",   sector: "生命科学工具" },
    ABT:   { name: "雅培",         sector: "医疗健康" },
    LLY:   { name: "礼来",         sector: "制药" },
    KO:    { name: "可口可乐",     sector: "必需消费" },
    PG:    { name: "宝洁",         sector: "必需消费" },
    MCD:   { name: "麦当劳",       sector: "餐饮" },
    RTX:   { name: "RTX",          sector: "航空航天与防务" },
    NFLX:  { name: "奈飞",         sector: "流媒体" },
    WMT:   { name: "沃尔玛",       sector: "零售" },
    PEP:   { name: "百事",         sector: "必需消费" },
    JNJ:   { name: "强生",         sector: "医疗健康" },
    PFE:   { name: "辉瑞",         sector: "制药" },
    SBUX:  { name: "星巴克",       sector: "餐饮" },
    NKE:   { name: "耐克",         sector: "运动消费" },
    ISRG:  { name: "直觉外科",     sector: "医疗设备" },
    DHR:   { name: "丹纳赫",       sector: "生命科学工具" },
    AMGN:  { name: "安进",         sector: "生物科技" },
    INTU:  { name: "财捷",         sector: "金融软件" },
    TXN:   { name: "德州仪器",     sector: "半导体" },
    LRCX:  { name: "泛林集团",     sector: "半导体设备" },
    MU:    { name: "美光科技",     sector: "存储芯片" },
    UPS:   { name: "联合包裹",     sector: "物流" },
    LMT:   { name: "洛克希德·马丁", sector: "航空航天与防务" },
    // ── V5.11.2 US Wave 3 (55 cards) ──────────────────────────────────────
    // Red
    UBER:  { name: "优步",         sector: "出行 · 配送" },
    VRT:   { name: "维谛技术",     sector: "数据中心设备" },
    FTNT:  { name: "飞塔",         sector: "网络安全" },
    ANET:  { name: "Arista",       sector: "云网络" },
    // Blue
    BKNG:  { name: "Booking",      sector: "在线旅游" },
    LOW:   { name: "劳氏",         sector: "家居零售" },
    TJX:   { name: "TJX",          sector: "折扣零售" },
    CMG:   { name: "Chipotle",     sector: "快餐" },
    CL:    { name: "高露洁",       sector: "日用消费" },
    SPGI:  { name: "标普全球",     sector: "金融数据" },
    ICE:   { name: "洲际交易所",   sector: "交易所" },
    CME:   { name: "芝商所",       sector: "衍生品交易所" },
    ADP:   { name: "ADP",          sector: "人力资源服务" },
    TT:    { name: "特灵科技",     sector: "暖通空调" },
    FDX:   { name: "联邦快递",     sector: "物流" },
    CSCO:  { name: "思科",         sector: "网络设备" },
    KLAC:  { name: "科磊",         sector: "半导体设备" },
    CDNS:  { name: "Cadence",      sector: "EDA软件" },
    SNPS:  { name: "新思科技",     sector: "EDA软件" },
    HCA:   { name: "HCA医疗",      sector: "医院运营" },
    SYK:   { name: "史赛克",       sector: "医疗设备" },
    MDT:   { name: "美敦力",       sector: "医疗设备" },
    // Green
    YUM:   { name: "百胜餐饮",     sector: "餐饮" },
    ROST:  { name: "Ross",         sector: "折扣零售" },
    TGT:   { name: "塔吉特",       sector: "零售" },
    KR:    { name: "克罗格",       sector: "食品零售" },
    GIS:   { name: "通用磨坊",     sector: "食品" },
    KMB:   { name: "金佰利",       sector: "日用消费" },
    HSY:   { name: "好时",         sector: "食品" },
    MRSH:  { name: "威达信",       sector: "保险经纪" },
    AON:   { name: "怡安",         sector: "保险经纪" },
    AJG:   { name: "Gallagher",    sector: "保险经纪" },
    FIS:   { name: "FIS",          sector: "金融科技" },
    PAYX:  { name: "Paychex",      sector: "人力资源服务" },
    GWW:   { name: "固安捷",       sector: "工业分销" },
    FAST:  { name: "Fastenal",     sector: "工业分销" },
    URI:   { name: "联合租赁",     sector: "设备租赁" },
    CARR:  { name: "开利",         sector: "暖通空调" },
    PH:    { name: "派克汉尼汾",   sector: "工业设备" },
    ODFL:  { name: "Old Dominion", sector: "货运物流" },
    LH:    { name: "徕博科",       sector: "医学检验" },
    BDX:   { name: "碧迪",         sector: "医疗器械" },
    VLO:   { name: "瓦莱罗",       sector: "炼油" },
    EOG:   { name: "EOG能源",      sector: "油气开采" },
    // White
    MKC:   { name: "味好美",       sector: "调味品" },
    CLX:   { name: "高乐氏",       sector: "日用消费" },
    HRL:   { name: "荷美尔",       sector: "食品" },
    CHD:   { name: "Church & Dwight", sector: "日用消费" },
    TRV:   { name: "旅行者保险",   sector: "财产保险" },
    JBHT:  { name: "JB Hunt",      sector: "货运物流" },
    DGX:   { name: "奎斯特",       sector: "医学检验" },
    DRI:   { name: "达登餐饮",     sector: "餐饮" },
    CPB:   { name: "金宝汤",       sector: "食品" },
    AKAM:  { name: "阿卡迈",       sector: "云服务" },
    CAH:   { name: "卡地纳健康",   sector: "医药分销" },
  };

  // Coarse English-sector -> Chinese fallback, used ONLY when a ticker is not in
  // COMPANY_CN (e.g. a future card). Keeps an unknown card readable in Chinese.
  const SECTOR_CN = {
    "Technology": "科技",
    "Communication Services": "通信服务",
    "Consumer Discretionary": "可选消费",
    "Consumer Staples": "必需消费",
    "Health Care": "医疗健康",
    "Financials": "金融",
    "Financial Technology": "金融科技",
    "Energy": "能源",
    "Industrials": "工业",
  };

  function tickerOf(card) {
    if (!card) return "";
    return String(card.ticker || "").toUpperCase();
  }

  function entry(card) {
    return COMPANY_CN[tickerOf(card)] || null;
  }

  // Chinese display name. Fallback: explicit map -> English deck name -> ticker.
  function nameCn(card) {
    const e = entry(card);
    if (e && e.name) return e.name;
    if (card && card.name) return String(card.name);
    const t = tickerOf(card);
    return t || "—";
  }

  // Chinese sector label. Fallback: explicit map -> English-sector map -> raw
  // deck sector -> dash. Never returns undefined/null/empty.
  function sectorCn(card) {
    const e = entry(card);
    if (e && e.sector) return e.sector;
    const raw = card && card.sector ? String(card.sector) : "";
    if (raw && SECTOR_CN[raw]) return SECTOR_CN[raw];
    return raw || "—";
  }

  // English company name, for the small secondary subtitle. May be empty.
  function enName(card) {
    return card && card.name ? String(card.name) : "";
  }

  // True when this card has an explicit (non-fallback) localization entry.
  function isLocalized(card) {
    return !!entry(card);
  }

  window.CardLocalization = {
    COMPANY_CN: COMPANY_CN,
    SECTOR_CN: SECTOR_CN,
    nameCn: nameCn,
    sectorCn: sectorCn,
    enName: enName,
    isLocalized: isLocalized,
  };
})();
