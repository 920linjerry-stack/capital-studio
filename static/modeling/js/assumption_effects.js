// v3.4.2: assumption effects mapping (AA seed).
// Locked by G/Jerry review. Do NOT edit without re-review.
//
// Constraint: DRIVER_ASSUMPTION_EFFECTS[driverId] keys MUST be a subset of
// ontology drivers.json[driverId].affects.
//
// effect direction semantics:
//   "positive": driver stronger → assumption dimension 上行 (+1)
//   "negative": driver stronger → assumption dimension 下行 (-1)
// direction sign does NOT imply good/bad. e.g. risk_discount 上行 = 风险更高,
// capex 上行 = 投入更多 (可能是扩张, 也可能压现金流).
//
// final_direction = effect_sign × state_sign
//   state_sign: stronger=+1, stable=0, weaker=-1, unknown=N/A
//
// Cross-version note: Bridge 按中长期方向解释 driver effect, 不处理短期过渡期噪音
// (例如 node_transition 短期良率爬坡 / 折旧压力).

const DRIVER_ASSUMPTION_EFFECTS = {

  // ========== 消费 / 品牌 ==========

  pricing_power: {
    revenue_growth: "positive",  // 定价权增强 → 公司能在不大幅牺牲销量的前提下提价，推升收入
    margin: "positive"            // 提价直接转化为更高的毛利率与净利率
  },

  premiumization: {
    revenue_growth: "positive",  // 产品结构上移 → ASP 提升 → 收入端上行
    margin: "positive"            // 高端 SKU 通常带更高单位毛利
  },

  consumer_recovery: {
    revenue_growth: "positive"   // 终端消费回暖 → 销量恢复 → 收入端上行
  },

  brand_moat: {
    margin: "positive",          // 强品牌支撑溢价与重复购买，毛利与营销效率上行
    terminal_confidence: "positive"  // 品牌护城河增强 → 永续期份额可持续性更强
  },

  channel_expansion: {
    revenue_growth: "positive",  // 渠道铺设增加 → 触达更多终端 → 收入端上行
    capex: "positive"             // 新渠道建设（门店/分销网络/物流）→ 资本支出上行（方向中性，不暗示好坏）
  },

  // ========== SaaS / 订阅 ==========

  nrr: {
    revenue_growth: "positive"   // 净收入留存上行 → 存量客户收入扩张 → 整体收入增长上行
  },

  cac_payback: {
    margin: "positive"           // 获客回收效率增强 → 回本更快 → 单位获客成本占收入比下行 → margin 上行
                                  // 注：cac_payback stronger 语义锁定为"回收效率更好/回本更快"，
                                  // 不是"周期变长"。不进 NEGATIVE_POLARITY_DRIVERS。
  },

  gross_churn: {
    revenue_growth: "negative"   // 流失率上行 → 收入流失加剧 → 收入增长下行
                                  // 注：gross_churn 已在 v3.4.0 §1.3 NEGATIVE_POLARITY_DRIVERS，
                                  // Bull 默认 weaker，Bear 默认 stronger，配合 negative effect 推导正确
  },

  // ========== 半导体 / 周期 ==========

  fab_utilization: {
    margin: "positive"           // 产能利用率上行 → 固定成本摊薄 → 毛利率上行
  },

  ai_demand: {
    revenue_growth: "positive",  // AI 算力需求上行 → 出货量与单价双升 → 收入端上行
    margin: "positive"            // 需求紧张 + 产品溢价 → 毛利率上行
  },

  capex_cycle: {
    capex: "positive"            // 资本开支周期上行 → capex 支出上行（方向中性，不暗示好坏）
  },

  node_transition: {
    margin: "positive",          // 制程升级成功后 → 新工艺溢价 + 良率成熟后毛利上行
                                  // 注：Bridge 按中长期方向解释，不处理过渡期良率/折旧压力
    capex: "positive"             // 制程升级期间设备投入显著上行（方向中性）
  },

  // ========== 平台 / 网络 ==========

  ecosystem_lockin: {
    margin: "positive",          // 生态锁定增强 → 议价能力与服务变现能力上行 → margin 上行
    terminal_confidence: "positive"  // 锁定效应 → 永续期份额与 churn 稳定性增强
  },

  network_effects: {
    revenue_growth: "positive",  // 网络效应增强 → 用户/商户双边规模放大 → 收入端上行
    terminal_confidence: "positive"  // 网络效应是远期护城河，永续期确定性上行
  },

  take_rate: {
    revenue_growth: "positive",  // 抽成率上行 → 单位 GMV 收入上行 → 收入端上行
    margin: "positive"            // 抽成是平台轻资产收入，几乎直接转化为利润
  },

  services_mix_shift: {
    margin: "positive",          // 服务收入毛利显著高于硬件/商品，结构上移 → margin 上行
    terminal_confidence: "positive"  // 服务收入粘性高、重复性强 → 永续期确定性上行
  },

  // ========== 利润率 / 成本 ==========

  operating_leverage: {
    margin: "positive"           // 经营杠杆释放 → 收入增长带动 margin 非线性上行
  },

  margin_recovery: {
    margin: "positive"           // 利润率修复 → margin 直接上行
  },

  input_cost_relief: {
    margin: "positive"           // 原材料成本下行红利更明显 → margin 上行
                                  // 注：stronger 语义锁定为"成本下行红利更显著"，不是"成本上升"
  },

  // ========== 产能 / 周转 ==========

  capacity_expansion: {
    revenue_growth: "positive",  // 产能扩张 → 可售货量上行 → 收入端上行
    capex: "positive"             // 扩产需投资 → capex 上行（方向中性）
  },

  asset_turnover: {
    revenue_growth: "positive",  // 资产周转效率上行 → 同等资产产生更多收入
    capex: "negative"             // 周转效率高 → 同等收入所需资本投入下行 → capex 下行
                                  // 注：唯一一条 capex negative。逻辑站在 per-unit-revenue 视角。
                                  // v3.4.2 不做 hover hint，未来用户混乱再加。
  },

  inventory_cycle: {
    revenue_growth: "positive",  // 库存周期上行 = 补库存阶段，下游订单回暖 → 收入端上行
                                  // 注：stronger 语义锁定为"补库存阶段更明显/周期位置改善"。
                                  // v3.4.2 不拆 driver，未来用户混乱再考虑 restocking/destocking 拆分。
    working_capital: "positive"  // 库存上行 → 营运资本占用上行（方向中性）
  },

  // ========== 市场 / 空间 ==========

  market_share_gain: {
    revenue_growth: "positive"   // 份额提升 → 在同等市场规模下收入上行
  },

  tam_expansion: {
    revenue_growth: "positive"   // 市场空间扩张 → 公司可触达池子放大 → 收入端上行
  },

  // ========== 风险 / 监管 ==========

  regulatory_headwind: {
    margin: "negative",          // 监管压力上行 → 合规成本上行、定价受限 → margin 下行
    risk_discount: "positive"    // 监管压力上行 → 风险溢价上行（方向中性，上行 = 折现率更高）
                                  // 注：regulatory_headwind 已在 NEGATIVE_POLARITY_DRIVERS，
                                  // Bull 默认 weaker → margin negative × weaker = +1 上行 ✓
                                  //                  → risk_discount positive × weaker = -1 下行 ✓
  }

};

if (typeof window !== "undefined") {
  window.DRIVER_ASSUMPTION_EFFECTS = DRIVER_ASSUMPTION_EFFECTS;
}

const DIMENSION_META = {
  revenue_growth: {
    display_name_cn: "收入增长",
    display_name_en: "Revenue Growth",
    neutral_description: "公司未来收入的扩张速度"
  },
  margin: {
    display_name_cn: "利润率",
    display_name_en: "Margin",
    neutral_description: "收入转化为利润的效率"
  },
  capex: {
    display_name_cn: "资本支出",
    display_name_en: "Capex",
    neutral_description: "维持和扩张业务的投资规模"
  },
  working_capital: {
    display_name_cn: "营运资本",
    display_name_en: "Working Capital",
    neutral_description: "日常运营占用的资金"
  },
  terminal_confidence: {
    display_name_cn: "长期确定性",
    display_name_en: "Terminal Confidence",
    neutral_description: "永续期假设的可靠程度"
  },
  risk_discount: {
    display_name_cn: "风险溢价",
    display_name_en: "Risk Discount",
    neutral_description: "折现率中反映不确定性的部分"
  }
};

if (typeof window !== "undefined") {
  window.DIMENSION_META = DIMENSION_META;
}

// Runtime sanity check: DRIVER_ASSUMPTION_EFFECTS keys must be subset of ontology affects.
// Non-blocking: logs to console but does not throw. Used to catch mapping/ontology drift.
function _v342SanityCheck() {
  if (typeof window === "undefined" || !window.ONTOLOGY_DRIVERS) {
    return; // ontology 还没加载，跳过
  }
  const errors = [];
  for (const driverId in DRIVER_ASSUMPTION_EFFECTS) {
    const ontologyDriver = window.ONTOLOGY_DRIVERS[driverId];
    if (!ontologyDriver) {
      errors.push(`[v3.4.2 sanity] driver "${driverId}" in mapping but not in ontology`);
      continue;
    }
    const affects = ontologyDriver.affects || [];
    for (const dim in DRIVER_ASSUMPTION_EFFECTS[driverId]) {
      if (!affects.includes(dim)) {
        errors.push(`[v3.4.2 sanity] driver "${driverId}" mapping has dim "${dim}" not in ontology affects [${affects.join(",")}]`);
      }
    }
  }
  if (errors.length > 0) {
    console.warn("[v3.4.2] DRIVER_ASSUMPTION_EFFECTS / ontology mismatch:");
    errors.forEach(e => console.warn("  " + e));
  }
}

if (typeof window !== "undefined") {
  window._v342SanityCheck = _v342SanityCheck;
  // 延迟执行，等 ontology 加载
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _v342SanityCheck);
  } else {
    _v342SanityCheck();
  }
}
