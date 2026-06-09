"""V5.11.2 US Wave 3 production company cards (build-time snapshot).

Generated from the reviewed docs/dev Wave 3 data pack after the V5.11.2
read-only source/quote data gate. Same frozen-snapshot posture as
real_seed_deck.py: no runtime fetch, no plugins, no auto-refresh.
Financial fields are USD millions; shares are diluted weighted-average
shares in millions (current-share basis where a split / issuance / stale
count required a data-gate correction); share_price is a USD quote
snapshot. BKNG / SNPS / HSY carry corrected share bases; KR / TRV / HCA /
BDX / MRSH carry explicit reconciliation caveats in source_meta.notes.
"""

from __future__ import annotations

from typing import Any


WAVE3_SEED_COMPANY_CARDS: list[dict[str, Any]] = [   {   'id': 'uber',
        'ticker': 'UBER',
        'name': 'Uber Technologies, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Industrials',
        'industry': 'Mobility / Delivery Marketplace',
        'revenue': 52017.0,
        'ebitda': 6284.0,
        'net_income': 10053.0,
        'cash': 7105.0,
        'debt': 10521.0,
        'shares': 2119.689,
        'share_price': 70.71,
        'arena_tier': 'red',
        'arena_tier_label': 'Elite',
        'arena_tier_name_cn': '红 / 精英',
        'arena_tier_reason': 'Wave 3 Elite card: Ride-hailing, delivery, and freight marketplace. '
                             'Role: high-beta / platform acquirer.',
        'tags': {   'industry_group': 'mobility_delivery_marketplace',
                    'strategic_tags': ['mobility', 'delivery_marketplace'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001543151-26-000015; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. SBC-heavy / '
                                    'growth-software profile can create EPS and EBITDA '
                                    'normalization artifacts. Debt convention should avoid '
                                    'double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1543151/000154315126000015/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001543151.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/UBER?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for UBER '
                                                               'on 2026-06-05'}}},
    {   'id': 'vrt',
        'ticker': 'VRT',
        'name': 'Vertiv Holdings Co',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Industrials',
        'industry': 'Data Center Power / Thermal',
        'revenue': 10229.9,
        'ebitda': 2138.3,
        'net_income': 1332.8,
        'cash': 1728.4,
        'debt': 2913.0,
        'shares': 390.653,
        'share_price': 300.51,
        'arena_tier': 'red',
        'arena_tier_label': 'Elite',
        'arena_tier_name_cn': '红 / 精英',
        'arena_tier_reason': 'Wave 3 Elite card: Data-center power, cooling, and infrastructure '
                             'equipment. Role: high-beta / infrastructure target.',
        'tags': {   'industry_group': 'data_center_power_thermal',
                    'strategic_tags': ['data_center_power', 'thermal'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001674101-26-000008; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1674101/000167410126000008/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001674101.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/VRT?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for VRT '
                                                               'on 2026-06-05'}}},
    {   'id': 'anet',
        'ticker': 'ANET',
        'name': 'Arista Networks, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Technology',
        'industry': 'Cloud Networking',
        'revenue': 9005.7,
        'ebitda': 3928.7,
        'net_income': 3511.4,
        'cash': 1963.9,
        'debt': 98.793,
        'shares': 1275.7,
        'share_price': 154.27,
        'arena_tier': 'red',
        'arena_tier_label': 'Elite',
        'arena_tier_name_cn': '红 / 精英',
        'arena_tier_reason': 'Wave 3 Elite card: Cloud networking and data-center switching. Role: '
                             'high-beta / strategic target.',
        'tags': {   'industry_group': 'cloud_networking',
                    'strategic_tags': ['cloud_networking'],
                    'sensitive_sectors': ['technology'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001596532-26-000013; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. SBC-heavy / '
                                    'growth-software profile can create EPS and EBITDA '
                                    'normalization artifacts. Debt convention should avoid '
                                    'double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1596532/000159653226000013/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001596532.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/ANET?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for ANET '
                                                               'on 2026-06-05'}}},
    {   'id': 'bkng',
        'ticker': 'BKNG',
        'name': 'Booking Holdings Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Discretionary',
        'industry': 'Online Travel',
        'revenue': 26917.0,
        'ebitda': 10071.0,
        'net_income': 5404.0,
        'cash': 17203.0,
        'debt': 18736.0,
        'shares': 794.0,
        'share_price': 165.84,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Global online travel and accommodation '
                             'marketplace. Role: acquirer / defensive.',
        'tags': {   'industry_group': 'online_travel',
                    'strategic_tags': ['online_travel'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001075531-26-000009; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it. Share basis corrected in '
                                    'V5.11.2: the draft mixed the post-split quote (165.84) with '
                                    'pre-split weighted-average shares (32.6M). Production uses '
                                    'post-split diluted weighted-average shares (794.0M) and '
                                    'FY2025 net income (5,404M per SEC NetIncomeLoss); market cap '
                                    'reconciles to ~131.7B vs provider ~128.5B (within ~2.5%).',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1075531/000107553126000009/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001075531.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/BKNG?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss FY2025 '
                                                              '(5,404M); the draft net income was '
                                                              'a parse error',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts diluted '
                                                          'weighted-average shares, post-split '
                                                          'basis (Q1 FY2026 ~794M); the draft '
                                                          'pre-split weighted-average was '
                                                          'inconsistent with the split-adjusted '
                                                          'quote',
                                                'share_price': 'Yahoo Finance chart close for BKNG '
                                                               'on 2026-06-05'}}},
    {   'id': 'low',
        'ticker': 'LOW',
        'name': "Lowe's Companies, Inc.",
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Discretionary',
        'industry': 'Home Improvement Retail',
        'revenue': 86286.0,
        'ebitda': 14288.0,
        'net_income': 6654.0,
        'cash': 982.0,
        'debt': 0.0,
        'shares': 560.0,
        'share_price': 210.74,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Home-improvement retailer. Role: both.',
        'tags': {   'industry_group': 'home_improvement_retail',
                    'strategic_tags': ['home_improvement_retail'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000060667-26-000029; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2026-01-30; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. EBITDA is derived for this '
                                    'draft and should not be presented as directly reported unless '
                                    'a filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/60667/000006066726000029/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000060667.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/LOW?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for LOW '
                                                               'on 2026-06-05'}}},
    {   'id': 'tjx',
        'ticker': 'TJX',
        'name': 'The TJX Companies, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Discretionary',
        'industry': 'Off-Price Retail',
        'revenue': 60372.0,
        'ebitda': 8546.0,
        'net_income': 5494.0,
        'cash': 6230.0,
        'debt': 2869.0,
        'shares': 1128.0,
        'share_price': 160.71,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Off-price apparel and home retailer. Role: '
                             'acquirer / target.',
        'tags': {   'industry_group': 'off_price_retail',
                    'strategic_tags': ['off-price_retail'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000109198-26-000008; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2026-01-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/109198/000010919826000008/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000109198.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/TJX?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax',
                                                'ebitda': 'Derived from SEC '
                                                          'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for TJX '
                                                               'on 2026-06-05'}}},
    {   'id': 'cmg',
        'ticker': 'CMG',
        'name': 'Chipotle Mexican Grill, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Discretionary',
        'industry': 'Fast Casual Restaurants',
        'revenue': 11925.601,
        'ebitda': 2297.18,
        'net_income': 1535.761,
        'cash': 350.545,
        'debt': 0.0,
        'shares': 1342.616,
        'share_price': 29.34,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Fast-casual restaurant operator. Role: acquirer / '
                             'target.',
        'tags': {   'industry_group': 'fast_casual_restaurants',
                    'strategic_tags': ['fast_casual_restaurants'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001058090-26-000009; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1058090/000105809026000009/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001058090.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/CMG?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts us-gaap:LongTermDebt; '
                                                        'operating leases excluded unless embedded '
                                                        'in issuer debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for CMG '
                                                               'on 2026-06-05'}}},
    {   'id': 'cl',
        'ticker': 'CL',
        'name': 'Colgate-Palmolive Company',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Staples',
        'industry': 'Household / Personal Care',
        'revenue': 20382.0,
        'ebitda': 3936.0,
        'net_income': 2132.0,
        'cash': 1288.0,
        'debt': 7986.0,
        'shares': 811.1,
        'share_price': 88.58,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Oral care, personal care, pet nutrition, and '
                             'home-care brands. Role: defensive / acquirer.',
        'tags': {   'industry_group': 'household_personal_care',
                    'strategic_tags': ['household', 'personal_care'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000021665-26-000006; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/21665/000002166526000006/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000021665.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/CL?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for CL '
                                                               'on 2026-06-05'}}},
    {   'id': 'spgi',
        'ticker': 'SPGI',
        'name': 'S&P Global Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Financials',
        'industry': 'Ratings / Data / Indices',
        'revenue': 15336.0,
        'ebitda': 7657.0,
        'net_income': 4471.0,
        'cash': 1745.0,
        'debt': 12770.0,
        'shares': 305.1,
        'share_price': 424.44,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Ratings, indices, data, and market-intelligence '
                             'platform. Role: acquirer / defensive.',
        'tags': {   'industry_group': 'ratings_data_indices',
                    'strategic_tags': ['ratings', 'data', 'indices'],
                    'sensitive_sectors': ['financials'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000064040-26-000013; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Financial-services, '
                                    'market-infrastructure, client-funds, or insurance economics '
                                    'may not behave like a plain industrial card in the current '
                                    'A/D engine. Debt convention should avoid double-counting '
                                    'current maturities and should exclude operating lease '
                                    'liabilities. EBITDA is derived for this draft and should not '
                                    'be presented as directly reported unless a filing line item '
                                    'supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/64040/000006404026000013/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000064040.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/SPGI?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for SPGI '
                                                               'on 2026-06-05'}}},
    {   'id': 'ice',
        'ticker': 'ICE',
        'name': 'Intercontinental Exchange, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Financials',
        'industry': 'Exchange / Market Infrastructure',
        'revenue': 12640.0,
        'ebitda': 6489.0,
        'net_income': 3315.0,
        'cash': 837.0,
        'debt': 20679.0,
        'shares': 575.0,
        'share_price': 141.5,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Exchanges, clearing, fixed income, data, and '
                             'mortgage technology. Role: acquirer / infrastructure.',
        'tags': {   'industry_group': 'exchange_market_infrastructure',
                    'strategic_tags': ['exchange', 'market_infrastructure'],
                    'sensitive_sectors': ['financials'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001571949-26-000004; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Financial-services, '
                                    'market-infrastructure, client-funds, or insurance economics '
                                    'may not behave like a plain industrial card in the current '
                                    'A/D engine. Debt convention should avoid double-counting '
                                    'current maturities and should exclude operating lease '
                                    'liabilities. EBITDA is derived for this draft and should not '
                                    'be presented as directly reported unless a filing line item '
                                    'supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1571949/000157194926000004/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001571949.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/ICE?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for ICE '
                                                               'on 2026-06-05'}}},
    {   'id': 'cme',
        'ticker': 'CME',
        'name': 'CME Group Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Financials',
        'industry': 'Derivatives Exchange',
        'revenue': 6520.6,
        'ebitda': 4337.0,
        'net_income': 4072.2,
        'cash': 4416.9,
        'debt': 0.0,
        'shares': 360.31,
        'share_price': 257.4,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Derivatives exchange and clearing operator. Role: '
                             'defensive / infrastructure.',
        'tags': {   'industry_group': 'derivatives_exchange',
                    'strategic_tags': ['derivatives_exchange'],
                    'sensitive_sectors': ['financials'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001156375-26-000009; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Financial-services, '
                                    'market-infrastructure, client-funds, or insurance economics '
                                    'may not behave like a plain industrial card in the current '
                                    'A/D engine. EBITDA is derived for this draft and should not '
                                    'be presented as directly reported unless a filing line item '
                                    'supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1156375/000115637526000009/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001156375.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/CME?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for CME '
                                                               'on 2026-06-05'}}},
    {   'id': 'adp',
        'ticker': 'ADP',
        'name': 'Automatic Data Processing, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Industrials',
        'industry': 'Payroll / HR Services',
        'revenue': 20560.9,
        'ebitda': 5892.5,
        'net_income': 4079.7,
        'cash': 3347.8,
        'debt': 3971.9,
        'shares': 408.7,
        'share_price': 231.95,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Payroll, HR outsourcing, and employer services. '
                             'Role: defensive / acquirer.',
        'tags': {   'industry_group': 'payroll_hr_services',
                    'strategic_tags': ['payroll', 'hr_services'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000008670-25-000037; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-06-30; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Financial-services, '
                                    'market-infrastructure, client-funds, or insurance economics '
                                    'may not behave like a plain industrial card in the current '
                                    'A/D engine. Client funds and related obligations should '
                                    'remain excluded from operating cash/debt conventions unless '
                                    'explicitly modeled. Debt convention should avoid '
                                    'double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/8670/000000867025000037/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000008670.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/ADP?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC '
                                                          'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for ADP '
                                                               'on 2026-06-05'}}},
    {   'id': 'tt',
        'ticker': 'TT',
        'name': 'Trane Technologies plc',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Industrials',
        'industry': 'HVAC / Climate Systems',
        'revenue': 21321.9,
        'ebitda': 4801.9,
        'net_income': 2918.6,
        'cash': 1763.3,
        'debt': 4733.8,
        'shares': 224.9,
        'share_price': 456.84,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: HVAC and climate-control systems. Role: acquirer / '
                             'defensive.',
        'tags': {   'industry_group': 'hvac_climate_systems',
                    'strategic_tags': ['hvac', 'climate_systems'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001628280-26-005731; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1466258/000162828026005731/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001466258.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/TT?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for TT '
                                                               'on 2026-06-05'}}},
    {   'id': 'fdx',
        'ticker': 'FDX',
        'name': 'FedEx Corporation',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Industrials',
        'industry': 'Parcel / Freight Logistics',
        'revenue': 87926.0,
        'ebitda': 12476.0,
        'net_income': 4092.0,
        'cash': 5502.0,
        'debt': 19899.0,
        'shares': 243.0,
        'share_price': 331.0,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Parcel delivery, freight, and logistics network. '
                             'Role: acquirer / cyclical.',
        'tags': {   'industry_group': 'parcel_freight_logistics',
                    'strategic_tags': ['parcel', 'freight_logistics'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001048911-25-000011; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-05-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Special working-capital, '
                                    'lease, financing, or distribution economics require '
                                    'source_meta notes before production promotion. Debt '
                                    'convention should avoid double-counting current maturities '
                                    'and should exclude operating lease liabilities. EBITDA is '
                                    'derived for this draft and should not be presented as '
                                    'directly reported unless a filing line item supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1048911/000104891125000011/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001048911.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/FDX?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts us-gaap:LongTermDebt; '
                                                        'operating leases excluded unless embedded '
                                                        'in issuer debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for FDX '
                                                               'on 2026-06-05'}}},
    {   'id': 'csco',
        'ticker': 'CSCO',
        'name': 'Cisco Systems, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Technology',
        'industry': 'Networking Hardware / Software',
        'revenue': 56654.0,
        'ebitda': 12460.0,
        'net_income': 10180.0,
        'cash': 8346.0,
        'debt': 24642.0,
        'shares': 3998.0,
        'share_price': 121.64,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Networking hardware, software, and security. Role: '
                             'acquirer / defensive.',
        'tags': {   'industry_group': 'networking_hardware_software',
                    'strategic_tags': ['networking_hardware', 'software'],
                    'sensitive_sectors': ['technology'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000858877-25-000111; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-07-26; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/858877/000085887725000111/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000858877.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/CSCO?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for CSCO '
                                                               'on 2026-06-05'}}},
    {   'id': 'klac',
        'ticker': 'KLAC',
        'name': 'KLA Corporation',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Technology',
        'industry': 'Semiconductor Process Control',
        'revenue': 12156.162,
        'ebitda': 5038.536,
        'net_income': 4061.643,
        'cash': 2078.908,
        'debt': 3469.67,
        'shares': 133.75,
        'share_price': 1929.2,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Semiconductor process-control and inspection '
                             'equipment. Role: acquirer / target.',
        'tags': {   'industry_group': 'semiconductor_process_control',
                    'strategic_tags': ['semiconductor_process_control'],
                    'sensitive_sectors': ['technology'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000319201-25-000024; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-06-30; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/319201/000031920125000024/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000319201.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/KLAC?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC '
                                                          'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for KLAC '
                                                               'on 2026-06-05'}}},
    {   'id': 'cdns',
        'ticker': 'CDNS',
        'name': 'Cadence Design Systems, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Technology',
        'industry': 'EDA Software',
        'revenue': 5296.759,
        'ebitda': 1811.518,
        'net_income': 1108.888,
        'cash': 3001.317,
        'debt': 0.0,
        'shares': 273.312,
        'share_price': 376.19,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Electronic design automation software. Role: niche '
                             'target / defensive.',
        'tags': {   'industry_group': 'eda_software',
                    'strategic_tags': ['eda_software'],
                    'sensitive_sectors': ['technology'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000813672-26-000016; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. SBC-heavy / '
                                    'growth-software profile can create EPS and EBITDA '
                                    'normalization artifacts. EBITDA is derived for this draft and '
                                    'should not be presented as directly reported unless a filing '
                                    'line item supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/813672/000081367226000016/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000813672.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/CDNS?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:NoInterestBearingDebtIdentifiedInReviewedSecDebtTags; '
                                                        'operating leases excluded unless embedded '
                                                        'in issuer debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for CDNS '
                                                               'on 2026-06-05'}}},
    {   'id': 'snps',
        'ticker': 'SNPS',
        'name': 'Synopsys, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Technology',
        'industry': 'EDA Software / IP',
        'revenue': 7054.178,
        'ebitda': 1575.357,
        'net_income': 1332.22,
        'cash': 2888.03,
        'debt': 13484.515,
        'shares': 192.144,
        'share_price': 464.85,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Electronic design automation software and '
                             'semiconductor IP. Role: acquirer / niche target.',
        'tags': {   'industry_group': 'eda_software_ip',
                    'strategic_tags': ['eda_software', 'ip'],
                    'sensitive_sectors': ['technology'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000883241-25-000028; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-10-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. SBC-heavy / '
                                    'growth-software profile can create EPS and EBITDA '
                                    'normalization artifacts. Debt convention should avoid '
                                    'double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it. Share basis refreshed in '
                                    'V5.11.2 to the current post-Ansys diluted weighted-average '
                                    "(~192.1M); the draft's 165.7M predated the Ansys share "
                                    'issuance. Market cap reconciles to ~89.3B vs provider ~89.0B '
                                    '(within ~0.5%). FY2025 net income reflects elevated '
                                    'acquisition-related charges.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/883241/000088324125000028/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000883241.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/SNPS?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts diluted '
                                                          'weighted-average shares, current '
                                                          'post-Ansys basis (~192.1M)',
                                                'share_price': 'Yahoo Finance chart close for SNPS '
                                                               'on 2026-06-05'}}},
    {   'id': 'hca',
        'ticker': 'HCA',
        'name': 'HCA Healthcare, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Health Care',
        'industry': 'Hospital Services',
        'revenue': 75600.0,
        'ebitda': 13355.0,
        'net_income': 6784.0,
        'cash': 1040.0,
        'debt': 46301.0,
        'shares': 239.495,
        'share_price': 372.13,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Hospital and healthcare-services operator. Role: '
                             'acquirer / defensive.',
        'tags': {   'industry_group': 'hospital_services',
                    'strategic_tags': ['hospital_services'],
                    'sensitive_sectors': ['health_care'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001193125-26-044769; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Special working-capital, '
                                    'lease, financing, or distribution economics require '
                                    'source_meta notes before production promotion. Debt '
                                    'convention should avoid double-counting current maturities '
                                    'and should exclude operating lease liabilities. EBITDA is '
                                    'derived for this draft and should not be presented as '
                                    'directly reported unless a filing line item supports it. '
                                    'Hospital-operator caveat: special working-capital and lease / '
                                    'financing economics; diluted weighted-average shares run ~8% '
                                    'above current shares outstanding (buybacks), reconciling '
                                    'within the warning band.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/860730/000119312526044769/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000860730.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/HCA?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC '
                                                          'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for HCA '
                                                               'on 2026-06-05'}}},
    {   'id': 'syk',
        'ticker': 'SYK',
        'name': 'Stryker Corporation',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Health Care',
        'industry': 'Medical Devices',
        'revenue': 25116.0,
        'ebitda': 6459.0,
        'net_income': 3246.0,
        'cash': 4011.0,
        'debt': 14859.0,
        'shares': 386.5,
        'share_price': 305.66,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Orthopedics, surgical, neurotechnology, and '
                             'medical devices. Role: acquirer / target.',
        'tags': {   'industry_group': 'medical_devices',
                    'strategic_tags': ['medical_devices'],
                    'sensitive_sectors': ['health_care'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000310764-26-000010; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/310764/000031076426000010/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000310764.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/SYK?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for SYK '
                                                               'on 2026-06-05'}}},
    {   'id': 'mdt',
        'ticker': 'MDT',
        'name': 'Medtronic plc',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Health Care',
        'industry': 'Medical Devices',
        'revenue': 33537.0,
        'ebitda': 8816.0,
        'net_income': 4662.0,
        'cash': 2218.0,
        'debt': 24916.0,
        'shares': 1289.9,
        'share_price': 81.67,
        'arena_tier': 'blue',
        'arena_tier_label': 'Core',
        'arena_tier_name_cn': '蓝 / 核心',
        'arena_tier_reason': 'Wave 3 Core card: Global medical-device platform. Role: acquirer / '
                             'defensive.',
        'tags': {   'industry_group': 'medical_devices',
                    'strategic_tags': ['medical_devices'],
                    'sensitive_sectors': ['health_care'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001613103-25-000091; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-04-25; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1613103/000161310325000091/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001613103.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/MDT?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for MDT '
                                                               'on 2026-06-05'}}},
    {   'id': 'yum',
        'ticker': 'YUM',
        'name': 'Yum! Brands, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Discretionary',
        'industry': 'Franchised Restaurants',
        'revenue': 8214.0,
        'ebitda': 3345.0,
        'net_income': 1559.0,
        'cash': 709.0,
        'debt': 3385.0,
        'shares': 281.0,
        'share_price': 150.87,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Global franchised restaurant brands. Role: '
                             'acquirer / defensive.',
        'tags': {   'industry_group': 'franchised_restaurants',
                    'strategic_tags': ['franchised_restaurants'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001041061-26-000084; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1041061/000104106126000084/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001041061.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/YUM?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for YUM '
                                                               'on 2026-06-05'}}},
    {   'id': 'rost',
        'ticker': 'ROST',
        'name': 'Ross Stores, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Discretionary',
        'industry': 'Off-Price Retail',
        'revenue': 22750.559,
        'ebitda': 3216.748,
        'net_income': 2145.044,
        'cash': 4594.392,
        'debt': 1517.606,
        'shares': 324.416,
        'share_price': 230.37,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Off-price apparel and home retailer. Role: '
                             'ordinary filler / target.',
        'tags': {   'industry_group': 'off_price_retail',
                    'strategic_tags': ['off-price_retail'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000745732-26-000006; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2026-01-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/745732/000074573226000006/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000745732.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/ROST?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for ROST '
                                                               'on 2026-06-05'}}},
    {   'id': 'tgt',
        'ticker': 'TGT',
        'name': 'Target Corporation',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Discretionary',
        'industry': 'Mass Retail',
        'revenue': 104780.0,
        'ebitda': 10868.0,
        'net_income': 3705.0,
        'cash': 5488.0,
        'debt': 15785.0,
        'shares': 455.6,
        'share_price': 122.57,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Mass-market retailer. Role: both.',
        'tags': {   'industry_group': 'mass_retail',
                    'strategic_tags': ['mass_retail'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000027419-26-000016; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2026-01-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/27419/000002741926000016/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000027419.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/TGT?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for TGT '
                                                               'on 2026-06-05'}}},
    {   'id': 'kr',
        'ticker': 'KR',
        'name': 'The Kroger Co.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Staples',
        'industry': 'Grocery Retail',
        'revenue': 147642.0,
        'ebitda': 5222.0,
        'net_income': 1016.0,
        'cash': 3334.0,
        'debt': 15875.0,
        'shares': 655.0,
        'share_price': 63.57,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Grocery retailer. Role: acquirer / '
                             'defensive.',
        'tags': {   'industry_group': 'grocery_retail',
                    'strategic_tags': ['grocery_retail'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001104659-26-037723; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2026-01-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it. Current share-count drift '
                                    'caveat: the diluted weighted-average shares run ~7% above '
                                    'current shares outstanding due to ongoing buybacks; market '
                                    'cap reconciles within the warning band.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/56873/000110465926037723/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000056873.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/KR?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for KR '
                                                               'on 2026-06-05'}}},
    {   'id': 'gis',
        'ticker': 'GIS',
        'name': 'General Mills, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Staples',
        'industry': 'Packaged Foods',
        'revenue': 19486.6,
        'ebitda': 4300.9,
        'net_income': 2295.2,
        'cash': 363.9,
        'debt': 677.0,
        'shares': 557.5,
        'share_price': 33.15,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Packaged food brands. Role: defensive / '
                             'ordinary filler.',
        'tags': {   'industry_group': 'packaged_foods',
                    'strategic_tags': ['packaged_foods'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001193125-25-147079; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-05-25; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. EBITDA is derived for this '
                                    'draft and should not be presented as directly reported unless '
                                    'a filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/40704/000119312525147079/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000040704.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/GIS?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for GIS '
                                                               'on 2026-06-05'}}},
    {   'id': 'kmb',
        'ticker': 'KMB',
        'name': 'Kimberly-Clark Corporation',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Staples',
        'industry': 'Household / Personal Care',
        'revenue': 16447.0,
        'ebitda': 3861.0,
        'net_income': 2021.0,
        'cash': 688.0,
        'debt': 7402.0,
        'shares': 333.2,
        'share_price': 99.04,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Tissue, diapers, and personal-care products. '
                             'Role: defensive / target.',
        'tags': {   'industry_group': 'household_personal_care',
                    'strategic_tags': ['household', 'personal_care'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001628280-26-007567; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/55785/000162828026007567/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000055785.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/KMB?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for KMB '
                                                               'on 2026-06-05'}}},
    {   'id': 'hsy',
        'ticker': 'HSY',
        'name': 'The Hershey Company',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Staples',
        'industry': 'Confectionery / Snacks',
        'revenue': 11692.576,
        'ebitda': 2142.345,
        'net_income': 883.259,
        'cash': 925.859,
        'debt': 4747.13,
        'shares': 202.84,
        'share_price': 184.58,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Chocolate and snack brands. Role: defensive '
                             '/ target.',
        'tags': {   'industry_group': 'confectionery_snacks',
                    'strategic_tags': ['confectionery', 'snacks'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001628280-26-008586; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it. Share count corrected in '
                                    'V5.11.2 to current common shares outstanding (202.8M); the '
                                    'draft used a stale higher count. Market cap reconciles to '
                                    '~37.4B vs provider ~37.4B. FY2025 net income (883M) reflects '
                                    'elevated cocoa input costs, materially below FY2024.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/47111/000162828026008586/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000047111.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/HSY?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:CommonStockSharesOutstanding, '
                                                          'current (2025-12-31 ~202.8M)',
                                                'share_price': 'Yahoo Finance chart close for HSY '
                                                               'on 2026-06-05'}}},
    {   'id': 'mrsh',
        'ticker': 'MRSH',
        'name': 'Marsh & McLennan Companies, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Financials',
        'industry': 'Insurance Brokerage / Consulting',
        'revenue': 26981.0,
        'ebitda': 6584.0,
        'net_income': 4160.0,
        'cash': 2687.0,
        'debt': 19855.0,
        'shares': 494.0,
        'share_price': 165.44,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Insurance brokerage, risk advisory, and '
                             'consulting. Role: acquirer / defensive.',
        'tags': {   'industry_group': 'insurance_brokerage_consulting',
                    'strategic_tags': ['insurance_brokerage', 'consulting'],
                    'sensitive_sectors': ['financials'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000062709-26-000022; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Ticker canonicalization '
                                    'required: freeze list used legacy MMC, but current '
                                    'quote/source lookup should use MRSH after the 2026 ticker '
                                    'change. Financial-services, market-infrastructure, '
                                    'client-funds, or insurance economics may not behave like a '
                                    'plain industrial card in the current A/D engine. Debt '
                                    'convention should avoid double-counting current maturities '
                                    'and should exclude operating lease liabilities. EBITDA is '
                                    'derived for this draft and should not be presented as '
                                    'directly reported unless a filing line item supports it. '
                                    'Ticker canonicalization: this is Marsh & McLennan, which '
                                    'changed its trading symbol from legacy MMC to MRSH effective '
                                    '2026-01-14. Production ticker/id is MRSH/mrsh; legacy MMC '
                                    'references resolve via the deck alias map. Financial-services '
                                    '/ insurance-brokerage economics may not behave like a plain '
                                    'industrial card.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/62709/000006270926000022/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000062709.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/MRSH?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for MRSH '
                                                               'on 2026-06-05'}}},
    {   'id': 'aon',
        'ticker': 'AON',
        'name': 'Aon plc',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Financials',
        'industry': 'Insurance Brokerage / Risk Advisory',
        'revenue': 17181.0,
        'ebitda': 4520.0,
        'net_income': 3695.0,
        'cash': 1195.0,
        'debt': 14660.0,
        'shares': 217.1,
        'share_price': 328.53,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Insurance brokerage and risk advisory. Role: '
                             'acquirer / defensive.',
        'tags': {   'industry_group': 'insurance_brokerage_risk_advisory',
                    'strategic_tags': ['insurance_brokerage', 'risk_advisory'],
                    'sensitive_sectors': ['financials'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001628280-26-008116; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Financial-services, '
                                    'market-infrastructure, client-funds, or insurance economics '
                                    'may not behave like a plain industrial card in the current '
                                    'A/D engine. Debt convention should avoid double-counting '
                                    'current maturities and should exclude operating lease '
                                    'liabilities. EBITDA is derived for this draft and should not '
                                    'be presented as directly reported unless a filing line item '
                                    'supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/315293/000162828026008116/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000315293.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/AON?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for AON '
                                                               'on 2026-06-05'}}},
    {   'id': 'ajg',
        'ticker': 'AJG',
        'name': 'Arthur J. Gallagher & Co.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Financials',
        'industry': 'Insurance Brokerage',
        'revenue': 13942.0,
        'ebitda': 2077.0,
        'net_income': 1494.0,
        'cash': 1396.0,
        'debt': 12744.0,
        'shares': 257.1,
        'share_price': 216.14,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Insurance brokerage and risk-management '
                             'services. Role: acquirer.',
        'tags': {   'industry_group': 'insurance_brokerage',
                    'strategic_tags': ['insurance_brokerage'],
                    'sensitive_sectors': ['financials'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001628280-26-008662; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Financial-services, '
                                    'market-infrastructure, client-funds, or insurance economics '
                                    'may not behave like a plain industrial card in the current '
                                    'A/D engine. Debt convention should avoid double-counting '
                                    'current maturities and should exclude operating lease '
                                    'liabilities. EBITDA is derived for this draft and should not '
                                    'be presented as directly reported unless a filing line item '
                                    'supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/354190/000162828026008662/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000354190.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/AJG?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC '
                                                          'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest '
                                                          'plus Depreciation',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:EntityCommonStockSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for AJG '
                                                               'on 2026-06-05'}}},
    {   'id': 'fis',
        'ticker': 'FIS',
        'name': 'Fidelity National Information Services, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Financial Technology',
        'industry': 'Banking / Payments Technology',
        'revenue': 10677.0,
        'ebitda': 4243.5,
        'net_income': 382.0,
        'cash': 599.0,
        'debt': 13082.0,
        'shares': 525.0,
        'share_price': 40.95,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Banking, merchant, and capital-markets '
                             'technology. Role: target / acquirer.',
        'tags': {   'industry_group': 'banking_payments_technology',
                    'strategic_tags': ['banking', 'payments_technology'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001136893-26-000013; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Financial-services, '
                                    'market-infrastructure, client-funds, or insurance economics '
                                    'may not behave like a plain industrial card in the current '
                                    'A/D engine. Debt convention should avoid double-counting '
                                    'current maturities and should exclude operating lease '
                                    'liabilities. EBITDA is derived for this draft and should not '
                                    'be presented as directly reported unless a filing line item '
                                    'supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1136893/000113689326000013/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001136893.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/FIS?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for FIS '
                                                               'on 2026-06-05'}}},
    {   'id': 'payx',
        'ticker': 'PAYX',
        'name': 'Paychex, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Industrials',
        'industry': 'Payroll / HR Services',
        'revenue': 5410.0,
        'ebitda': 2505.9,
        'net_income': 1657.3,
        'cash': 1628.6,
        'debt': 4966.8,
        'shares': 362.0,
        'share_price': 100.53,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Payroll and HR services for small and medium '
                             'businesses. Role: defensive / target.',
        'tags': {   'industry_group': 'payroll_hr_services',
                    'strategic_tags': ['payroll', 'hr_services'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000950170-25-095300; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-05-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Financial-services, '
                                    'market-infrastructure, client-funds, or insurance economics '
                                    'may not behave like a plain industrial card in the current '
                                    'A/D engine. Client funds and related obligations should '
                                    'remain excluded from operating cash/debt conventions unless '
                                    'explicitly modeled. Debt convention should avoid '
                                    'double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/723531/000095017025095300/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000723531.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/PAYX?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts us-gaap:ProfitLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for PAYX '
                                                               'on 2026-06-05'}}},
    {   'id': 'gww',
        'ticker': 'GWW',
        'name': 'W.W. Grainger, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Industrials',
        'industry': 'MRO Distribution',
        'revenue': 17942.0,
        'ebitda': 3079.0,
        'net_income': 1706.0,
        'cash': 585.0,
        'debt': 2488.0,
        'shares': 48.0,
        'share_price': 1300.01,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Maintenance, repair, and operating supplies '
                             'distribution. Role: acquirer / target.',
        'tags': {   'industry_group': 'mro_distribution',
                    'strategic_tags': ['mro_distribution'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000277135-26-000011; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/277135/000027713526000011/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000277135.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/GWW?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for GWW '
                                                               'on 2026-06-05'}}},
    {   'id': 'fast',
        'ticker': 'FAST',
        'name': 'Fastenal Company',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Industrials',
        'industry': 'Industrial Distribution',
        'revenue': 8200.5,
        'ebitda': 1834.9,
        'net_income': 1258.4,
        'cash': 276.8,
        'debt': 125.0,
        'shares': 1150.334,
        'share_price': 46.79,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Industrial and construction supplies '
                             'distribution. Role: target / ordinary filler.',
        'tags': {   'industry_group': 'industrial_distribution',
                    'strategic_tags': ['industrial_distribution'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000815556-26-000009; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/815556/000081555626000009/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000815556.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/FAST?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for FAST '
                                                               'on 2026-06-05'}}},
    {   'id': 'uri',
        'ticker': 'URI',
        'name': 'United Rentals, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Industrials',
        'industry': 'Equipment Rental',
        'revenue': 3695.0,
        'ebitda': 5656.0,
        'net_income': 2494.0,
        'cash': 459.0,
        'debt': 15879.0,
        'shares': 64.604,
        'share_price': 1067.77,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Equipment rental and services. Role: '
                             'cyclical / acquirer.',
        'tags': {   'industry_group': 'equipment_rental',
                    'strategic_tags': ['equipment_rental'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001067701-26-000007; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Special working-capital, '
                                    'lease, financing, or distribution economics require '
                                    'source_meta notes before production promotion. Debt '
                                    'convention should avoid double-counting current maturities '
                                    'and should exclude operating lease liabilities. EBITDA is '
                                    'derived for this draft and should not be presented as '
                                    'directly reported unless a filing line item supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1067701/000106770126000007/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001067701.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/URI?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts us-gaap:LongTermDebt + '
                                                        'us-gaap:DebtCurrent; operating leases '
                                                        'excluded unless embedded in issuer debt '
                                                        'tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for URI '
                                                               'on 2026-06-05'}}},
    {   'id': 'carr',
        'ticker': 'CARR',
        'name': 'Carrier Global Corporation',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Industrials',
        'industry': 'HVAC / Building Systems',
        'revenue': 21747.0,
        'ebitda': 3446.0,
        'net_income': 1484.0,
        'cash': 1555.0,
        'debt': 11473.0,
        'shares': 862.4,
        'share_price': 67.16,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: HVAC, refrigeration, and building systems. '
                             'Role: target / acquirer.',
        'tags': {   'industry_group': 'hvac_building_systems',
                    'strategic_tags': ['hvac', 'building_systems'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001783180-26-000008; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1783180/000178318026000008/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001783180.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/CARR?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for CARR '
                                                               'on 2026-06-05'}}},
    {   'id': 'ph',
        'ticker': 'PH',
        'name': 'Parker-Hannifin Corporation',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Industrials',
        'industry': 'Motion Control / Components',
        'revenue': 19850.0,
        'ebitda': 5254.0,
        'net_income': 3532.0,
        'cash': 467.0,
        'debt': 12559.459,
        'shares': 130.2,
        'share_price': 882.34,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Motion-control and engineered industrial '
                             'components. Role: acquirer / cyclical.',
        'tags': {   'industry_group': 'motion_control_components',
                    'strategic_tags': ['motion_control', 'components'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000076334-25-000035; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-06-30; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/76334/000007633425000035/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000076334.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/PH?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus Depreciation + '
                                                          'AmortizationOfIntangibleAssets',
                                                'net_income': 'SEC companyfacts us-gaap:ProfitLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for PH '
                                                               'on 2026-06-05'}}},
    {   'id': 'odfl',
        'ticker': 'ODFL',
        'name': 'Old Dominion Freight Line, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Industrials',
        'industry': 'LTL Freight',
        'revenue': 5496.389,
        'ebitda': 1725.728,
        'net_income': 1023.703,
        'cash': 120.091,
        'debt': 20.0,
        'shares': 211.598,
        'share_price': 242.57,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Less-than-truckload freight carrier. Role: '
                             'target / defensive.',
        'tags': {   'industry_group': 'ltl_freight',
                    'strategic_tags': ['ltl_freight'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001193125-26-067161; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/878927/000119312526067161/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000878927.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/ODFL?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for ODFL '
                                                               'on 2026-06-05'}}},
    {   'id': 'lh',
        'ticker': 'LH',
        'name': 'Labcorp Holdings Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Health Care',
        'industry': 'Diagnostics / Lab Services',
        'revenue': 13951.7,
        'ebitda': 2065.8,
        'net_income': 876.5,
        'cash': 532.3,
        'debt': 5584.7,
        'shares': 83.8,
        'share_price': 265.15,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Diagnostic testing and laboratory services. '
                             'Role: target / acquirer.',
        'tags': {   'industry_group': 'diagnostics_lab_services',
                    'strategic_tags': ['diagnostics', 'lab_services'],
                    'sensitive_sectors': ['health_care'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000920148-26-000111; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/920148/000092014826000111/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000920148.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/LH?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for LH '
                                                               'on 2026-06-05'}}},
    {   'id': 'bdx',
        'ticker': 'BDX',
        'name': 'Becton, Dickinson and Company',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Health Care',
        'industry': 'Medical Devices / Supplies',
        'revenue': 21840.0,
        'ebitda': 5041.0,
        'net_income': 1678.0,
        'cash': 641.0,
        'debt': 18373.0,
        'shares': 288.509,
        'share_price': 151.16,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Medical devices, supplies, and diagnostics. '
                             'Role: target / defensive.',
        'tags': {   'industry_group': 'medical_devices_supplies',
                    'strategic_tags': ['medical_devices', 'supplies'],
                    'sensitive_sectors': ['health_care'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000010795-25-000099; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-09-30; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it. Medical-device working-capital '
                                    'caveat; diluted weighted-average shares run modestly above '
                                    'current shares outstanding (buybacks); market cap reconciles '
                                    'within the pass band.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/10795/000001079525000099/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000010795.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/BDX?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for BDX '
                                                               'on 2026-06-05'}}},
    {   'id': 'vlo',
        'ticker': 'VLO',
        'name': 'Valero Energy Corporation',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Energy',
        'industry': 'Refining / Marketing',
        'revenue': 122687.0,
        'ebitda': 5086.0,
        'net_income': 2348.0,
        'cash': 4688.0,
        'debt': 9210.0,
        'shares': 309.0,
        'share_price': 255.82,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Petroleum refining and marketing. Role: '
                             'cyclical / target.',
        'tags': {   'industry_group': 'refining_marketing',
                    'strategic_tags': ['refining', 'marketing'],
                    'sensitive_sectors': ['energy'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001628280-26-011499; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1035002/000162828026011499/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001035002.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/VLO?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts us-gaap:LongTermDebt + '
                                                        'us-gaap:DebtCurrent; operating leases '
                                                        'excluded unless embedded in issuer debt '
                                                        'tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for VLO '
                                                               'on 2026-06-05'}}},
    {   'id': 'eog',
        'ticker': 'EOG',
        'name': 'EOG Resources, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Energy',
        'industry': 'Exploration / Production',
        'revenue': 22632.0,
        'ebitda': 10846.0,
        'net_income': 4980.0,
        'cash': 3396.0,
        'debt': 7936.0,
        'shares': 546.0,
        'share_price': 137.78,
        'arena_tier': 'green',
        'arena_tier_label': 'Specialist',
        'arena_tier_name_cn': '绿 / 专精',
        'arena_tier_reason': 'Wave 3 Specialist card: Oil and gas exploration and production. '
                             'Role: cyclical / target.',
        'tags': {   'industry_group': 'exploration_production',
                    'strategic_tags': ['exploration', 'production'],
                    'sensitive_sectors': ['energy'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000821189-26-000054; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/821189/000082118926000054/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000821189.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/EOG?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for EOG '
                                                               'on 2026-06-05'}}},
    {   'id': 'mkc',
        'ticker': 'MKC',
        'name': 'McCormick & Company, Incorporated',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Staples',
        'industry': 'Spices / Flavorings',
        'revenue': 6840.3,
        'ebitda': 1404.9,
        'net_income': 789.4,
        'cash': 95.9,
        'debt': 3996.3,
        'shares': 269.4,
        'share_price': 47.24,
        'arena_tier': 'white',
        'arena_tier_label': 'Basic',
        'arena_tier_name_cn': '白 / 基础',
        'arena_tier_reason': 'Wave 3 Basic card: Spices, seasonings, and flavorings. Role: '
                             'ordinary filler / target.',
        'tags': {   'industry_group': 'spices_flavorings',
                    'strategic_tags': ['spices', 'flavorings'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000063754-26-000037; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-11-30; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/63754/000006375426000037/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000063754.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/MKC?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for MKC '
                                                               'on 2026-06-05'}}},
    {   'id': 'clx',
        'ticker': 'CLX',
        'name': 'The Clorox Company',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Staples',
        'industry': 'Household Products',
        'revenue': 7104.0,
        'ebitda': 1462.0,
        'net_income': 810.0,
        'cash': 167.0,
        'debt': 2686.0,
        'shares': 124.287,
        'share_price': 94.14,
        'arena_tier': 'white',
        'arena_tier_label': 'Basic',
        'arena_tier_name_cn': '白 / 基础',
        'arena_tier_reason': 'Wave 3 Basic card: Household, cleaning, and lifestyle products. '
                             'Role: ordinary filler / defensive.',
        'tags': {   'industry_group': 'household_products',
                    'strategic_tags': ['household_products'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000021076-25-000039; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-06-30; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/21076/000002107625000039/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000021076.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/CLX?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC '
                                                          'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for CLX '
                                                               'on 2026-06-05'}}},
    {   'id': 'hrl',
        'ticker': 'HRL',
        'name': 'Hormel Foods Corporation',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Staples',
        'industry': 'Packaged Foods',
        'revenue': 12106.16,
        'ebitda': 982.504,
        'net_income': 478.197,
        'cash': 670.679,
        'debt': 3042.424,
        'shares': 550.496,
        'share_price': 23.62,
        'arena_tier': 'white',
        'arena_tier_label': 'Basic',
        'arena_tier_name_cn': '白 / 基础',
        'arena_tier_reason': 'Wave 3 Basic card: Packaged meat and food brands. Role: ordinary '
                             'filler / target.',
        'tags': {   'industry_group': 'packaged_foods',
                    'strategic_tags': ['packaged_foods'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000048465-25-000059; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-10-26; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/48465/000004846525000059/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000048465.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/HRL?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for HRL '
                                                               'on 2026-06-05'}}},
    {   'id': 'chd',
        'ticker': 'CHD',
        'name': 'Church & Dwight Co., Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Staples',
        'industry': 'Household / Personal Care',
        'revenue': 6203.2,
        'ebitda': 1325.0,
        'net_income': 736.8,
        'cash': 409.0,
        'debt': 2205.1,
        'shares': 244.3,
        'share_price': 96.74,
        'arena_tier': 'white',
        'arena_tier_label': 'Basic',
        'arena_tier_name_cn': '白 / 基础',
        'arena_tier_reason': 'Wave 3 Basic card: Household and personal-care brands. Role: '
                             'ordinary filler / target.',
        'tags': {   'industry_group': 'household_personal_care',
                    'strategic_tags': ['household', 'personal_care'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001193125-26-048139; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/313927/000119312526048139/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000313927.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/CHD?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for CHD '
                                                               'on 2026-06-05'}}},
    {   'id': 'trv',
        'ticker': 'TRV',
        'name': 'The Travelers Companies, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Financials',
        'industry': 'P&C Insurance',
        'revenue': 48828.0,
        'ebitda': 8476.0,
        'net_income': 6288.0,
        'cash': 842.0,
        'debt': 6461.0,
        'shares': 227.6,
        'share_price': 303.25,
        'arena_tier': 'white',
        'arena_tier_label': 'Basic',
        'arena_tier_name_cn': '白 / 基础',
        'arena_tier_reason': 'Wave 3 Basic card: Property and casualty insurance. Role: defensive '
                             '/ ordinary filler.',
        'tags': {   'industry_group': 'p_c_insurance',
                    'strategic_tags': ['p&c_insurance'],
                    'sensitive_sectors': ['financials'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000086312-26-000065; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Financial-services, '
                                    'market-infrastructure, client-funds, or insurance economics '
                                    'may not behave like a plain industrial card in the current '
                                    'A/D engine. Insurance balance sheet and investment assets '
                                    'require an explanatory caveat; do not treat as an ordinary '
                                    'industrial net-debt card. Debt convention should avoid '
                                    'double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it. Insurance balance-sheet caveat: '
                                    'investment assets and reserves are not an ordinary industrial '
                                    'net-debt card; diluted weighted-average shares run ~7% above '
                                    'current shares outstanding (buybacks).',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/86312/000008631226000065/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000086312.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/TRV?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC '
                                                          'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for TRV '
                                                               'on 2026-06-05'}}},
    {   'id': 'jbht',
        'ticker': 'JBHT',
        'name': 'J.B. Hunt Transport Services, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Industrials',
        'industry': 'Intermodal / Truck Brokerage',
        'revenue': 11999.096,
        'ebitda': 2294.639,
        'net_income': 598.282,
        'cash': 17.284,
        'debt': 1466.797,
        'shares': 97.688,
        'share_price': 284.95,
        'arena_tier': 'white',
        'arena_tier_label': 'Basic',
        'arena_tier_name_cn': '白 / 基础',
        'arena_tier_reason': 'Wave 3 Basic card: Intermodal, trucking, and logistics services. '
                             'Role: ordinary filler / target.',
        'tags': {   'industry_group': 'intermodal_truck_brokerage',
                    'strategic_tags': ['intermodal', 'truck_brokerage'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001437749-26-005294; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/728535/000143774926005294/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000728535.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/JBHT?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for JBHT '
                                                               'on 2026-06-05'}}},
    {   'id': 'dgx',
        'ticker': 'DGX',
        'name': 'Quest Diagnostics Incorporated',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Health Care',
        'industry': 'Diagnostics',
        'revenue': 11035.0,
        'ebitda': 2126.0,
        'net_income': 992.0,
        'cash': 420.0,
        'debt': 5671.0,
        'shares': 113.0,
        'share_price': 200.29,
        'arena_tier': 'white',
        'arena_tier_label': 'Basic',
        'arena_tier_name_cn': '白 / 基础',
        'arena_tier_reason': 'Wave 3 Basic card: Diagnostic testing services. Role: ordinary '
                             'filler / target.',
        'tags': {   'industry_group': 'diagnostics',
                    'strategic_tags': ['diagnostics'],
                    'sensitive_sectors': ['health_care'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001022079-26-000015; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1022079/000102207926000015/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001022079.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/DGX?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for DGX '
                                                               'on 2026-06-05'}}},
    {   'id': 'dri',
        'ticker': 'DRI',
        'name': 'Darden Restaurants, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Discretionary',
        'industry': 'Restaurants',
        'revenue': 12076.7,
        'ebitda': 1878.4,
        'net_income': 1049.6,
        'cash': 240.0,
        'debt': 901.0,
        'shares': 118.4,
        'share_price': 198.12,
        'arena_tier': 'white',
        'arena_tier_label': 'Basic',
        'arena_tier_name_cn': '白 / 基础',
        'arena_tier_reason': 'Wave 3 Basic card: Casual-dining restaurant operator. Role: ordinary '
                             'filler / defensive.',
        'tags': {   'industry_group': 'restaurants',
                    'strategic_tags': ['restaurants'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000940944-25-000038; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-05-25; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/940944/000094094425000038/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000940944.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/DRI?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent + '
                                                        'us-gaap:ShortTermBorrowings; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for DRI '
                                                               'on 2026-06-05'}}},
    {   'id': 'cpb',
        'ticker': 'CPB',
        'name': "The Campbell's Company",
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Consumer Staples',
        'industry': 'Packaged Foods',
        'revenue': 10253.0,
        'ebitda': 1558.0,
        'net_income': 602.0,
        'cash': 132.0,
        'debt': 2644.0,
        'shares': 300.0,
        'share_price': 21.68,
        'arena_tier': 'white',
        'arena_tier_label': 'Basic',
        'arena_tier_name_cn': '白 / 基础',
        'arena_tier_reason': 'Wave 3 Basic card: Packaged food and snack brands. Role: ordinary '
                             'filler / target.',
        'tags': {   'industry_group': 'packaged_foods',
                    'strategic_tags': ['packaged_foods'],
                    'sensitive_sectors': [],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000016732-25-000112; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-08-03; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Debt convention should '
                                    'avoid double-counting current maturities and should exclude '
                                    'operating lease liabilities. EBITDA is derived for this draft '
                                    'and should not be presented as directly reported unless a '
                                    'filing line item supports it.',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/16732/000001673225000112/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000016732.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/CPB?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtCurrent + '
                                                        'us-gaap:LongTermDebtNoncurrent; operating '
                                                        'leases excluded unless embedded in issuer '
                                                        'debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for CPB '
                                                               'on 2026-06-05'}}},
    {   'id': 'akam',
        'ticker': 'AKAM',
        'name': 'Akamai Technologies, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Technology',
        'industry': 'CDN / Security / Edge',
        'revenue': 4208.175,
        'ebitda': 1418.797,
        'net_income': 452.031,
        'cash': 930.231,
        'debt': 0.0,
        'shares': 147.023,
        'share_price': 149.32,
        'arena_tier': 'white',
        'arena_tier_label': 'Basic',
        'arena_tier_name_cn': '白 / 基础',
        'arena_tier_reason': 'Wave 3 Basic card: Content delivery, security, and edge cloud '
                             'services. Role: ordinary filler / target.',
        'tags': {   'industry_group': 'cdn_security_edge',
                    'strategic_tags': ['cdn', 'security', 'edge'],
                    'sensitive_sectors': ['technology'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001086222-26-000022; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. SBC-heavy / '
                                    'growth-software profile can create EPS and EBITDA '
                                    'normalization artifacts. EBITDA is derived for this draft and '
                                    'should not be presented as directly reported unless a filing '
                                    'line item supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1086222/000108622226000022/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001086222.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/AKAM?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:NoInterestBearingDebtIdentifiedInReviewedSecDebtTags; '
                                                        'operating leases excluded unless embedded '
                                                        'in issuer debt tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for AKAM '
                                                               'on 2026-06-05'}}},
    {   'id': 'cah',
        'ticker': 'CAH',
        'name': 'Cardinal Health, Inc.',
        'market': 'NYSE/NASDAQ',
        'currency': 'USD',
        'sector': 'Health Care',
        'industry': 'Healthcare Distribution',
        'revenue': 222578.0,
        'ebitda': 3390.0,
        'net_income': 1561.0,
        'cash': 3874.0,
        'debt': 2828.7,
        'shares': 242.0,
        'share_price': 205.71,
        'arena_tier': 'white',
        'arena_tier_label': 'Basic',
        'arena_tier_name_cn': '白 / 基础',
        'arena_tier_reason': 'Wave 3 Basic card: Healthcare products distribution and services. '
                             'Role: ordinary filler / defensive.',
        'tags': {   'industry_group': 'healthcare_distribution',
                    'strategic_tags': ['healthcare_distribution'],
                    'sensitive_sectors': ['health_care'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0000721371-25-000079; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-06-30; price snapshot '
                                                          '2026-06-05',
                           'as_of_date': '2026-06-05',
                           'notes': 'V5.11.2 US Wave 3 production card. Special working-capital, '
                                    'lease, financing, or distribution economics require '
                                    'source_meta notes before production promotion. Debt '
                                    'convention should avoid double-counting current maturities '
                                    'and should exclude operating lease liabilities. EBITDA is '
                                    'derived for this draft and should not be presented as '
                                    'directly reported unless a filing line item supports it.',
                           'confidence': 'medium',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/721371/000072137125000079/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000721371.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/CAH?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts us-gaap:Revenues',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization + '
                                                          'DepreciationAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts us-gaap:LongTermDebt + '
                                                        'us-gaap:DebtCurrent; operating leases '
                                                        'excluded unless embedded in issuer debt '
                                                        'tag',
                                                'shares': 'SEC companyfacts '
                                                          'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; '
                                                          'converted to millions',
                                                'share_price': 'Yahoo Finance chart close for CAH '
                                                               'on 2026-06-05'}}},
    {   'id': 'ftnt',
        'ticker': 'FTNT',
        'name': 'Fortinet, Inc.',
        'market': 'NASDAQ',
        'currency': 'USD',
        'sector': 'Technology',
        'industry': 'Cybersecurity / Network Security',
        'revenue': 6799.6,
        'ebitda': 2236.7,
        'net_income': 1853.443,
        'cash': 2223.8,
        'debt': 496.8,
        'shares': 742.8,
        'share_price': 144.68,
        'arena_tier': 'red',
        'arena_tier_label': 'Elite',
        'arena_tier_name_cn': '红 / 精英',
        'arena_tier_reason': 'Wave 3 Elite card: Network security and firewall platform. Role: '
                             'high-beta / strategic acquirer. (V5.11.2 replacement for '
                             'GAAP-unprofitable CRWD.)',
        'tags': {   'industry_group': 'cybersecurity_software',
                    'strategic_tags': ['cybersecurity_software'],
                    'sensitive_sectors': ['technology'],
                    'jurisdiction': 'US',
                    'market_position': 'wave3_candidate',
                    'state_linked': False},
        'source_meta': {   'source': 'SEC EDGAR + Yahoo Finance',
                           'source_document_or_provider': 'SEC companyfacts / '
                                                          '0001262039-26-000007; SEC 10-K; Yahoo '
                                                          'Finance chart',
                           'fiscal_period_or_as_of_date': 'FY ended 2025-12-31; price snapshot '
                                                          '2026-06-08',
                           'as_of_date': '2026-06-08',
                           'notes': 'V5.11.2 US Wave 3 production card. CRWD (CrowdStrike) was the '
                                    'original Wave 3 red cybersecurity candidate, but its FY GAAP '
                                    'net income and EBITDA are negative, which the A/D engine '
                                    'rejects for an acquirer; the listed backup ZS (Zscaler) is '
                                    'likewise GAAP-unprofitable, so Fortinet was substituted as '
                                    'the GAAP-profitable large-cap cybersecurity peer. EBITDA is '
                                    'operating income plus depreciation and amortization '
                                    '(derived). Debt is the senior-notes carrying amount and '
                                    'excludes leases. Market cap (diluted weighted-average shares '
                                    'times quote) reconciles to ~107.5B vs provider ~106.0B '
                                    '(within ~1.5%).',
                           'confidence': 'high',
                           'filing_url': 'https://www.sec.gov/Archives/edgar/data/1262039/000126203926000007/',
                           'companyfacts_url': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001262039.json',
                           'quote_url': 'https://query1.finance.yahoo.com/v8/finance/chart/FTNT?range=7d&interval=1d',
                           'field_sources': {   'revenue': 'SEC companyfacts '
                                                           'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                                                'ebitda': 'Derived from SEC OperatingIncomeLoss '
                                                          'plus '
                                                          'DepreciationDepletionAndAmortization',
                                                'net_income': 'SEC companyfacts '
                                                              'us-gaap:NetIncomeLoss',
                                                'cash': 'SEC companyfacts '
                                                        'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                                                'debt': 'SEC companyfacts '
                                                        'us-gaap:LongTermDebtNoncurrent (senior '
                                                        'notes carrying amount; leases excluded)',
                                                'shares': 'SEC companyfacts diluted '
                                                          'weighted-average shares (~742.8M)',
                                                'share_price': 'Yahoo Finance chart close for FTNT '
                                                               'on 2026-06-08'}}}]
