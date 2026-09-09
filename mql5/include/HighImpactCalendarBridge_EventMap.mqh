//+------------------------------------------------------------------+
//| HighImpactCalendarBridge_EventMap.mqh                             |
//|                                                                    |
//| Exact, static (event_code, currency, country_code, country_id) -> |
//| canonical-code lookup table for the High-Impact Calendar Bridge   |
//| producer.                                                          |
//|                                                                    |
//| Every entry below was confirmed against a live MetaQuotes         |
//| Economic Calendar discovery session (raw Experts log), never      |
//| guessed. No substring/regex/localized-name matching is used        |
//| anywhere in this file - lookup is exact 4-tuple equality only.    |
//| An unmapped provider record is left unresolved by design: the     |
//| caller must drop it, never fabricate a canonical code for it.     |
//|                                                                    |
//| Deliberately EXCLUDED from this table (present in the live        |
//| calendar but out of V1 scope):                                    |
//|   marginal-lending-facility-rate-decision (EUR/EU/999, MODERATE)  |
//|   chicago-pmi                              (USD/US/840)           |
//|   fomc-minutes                             (USD/US/840, MODERATE) |
//|   fomc-economic-projections                (USD/US/840, MODERATE) |
//+------------------------------------------------------------------+
#ifndef HIGH_IMPACT_CALENDAR_BRIDGE_EVENT_MAP_MQH
#define HIGH_IMPACT_CALENDAR_BRIDGE_EVENT_MAP_MQH

struct SHighImpactEventMapEntry
{
   string event_code;
   string currency;
   string country_code;
   long   country_id;
   string canonical_code;
};

// Exact provider identity -> canonical code. Multiple rows per canonical
// code are expected and supported (e.g. CPI mm + yy) - the producer/gate
// never deduplicates by event_time; see the approved design closure,
// "Multiple provider records -> one canonical code".
const SHighImpactEventMapEntry g_high_impact_event_map[] =
{
   {"consumer-price-index-mm",              "USD", "US", 840, "US_CPI"},
   {"consumer-price-index-yy",              "USD", "US", 840, "US_CPI"},
   {"consumer-price-index-ex-food-energy-mm","USD", "US", 840, "US_CORE_CPI"},
   {"consumer-price-index-ex-food-energy-yy","USD", "US", 840, "US_CORE_CPI"},
   {"pce-price-index-mm",                   "USD", "US", 840, "US_PCE"},
   {"pce-price-index-yy",                   "USD", "US", 840, "US_PCE"},
   {"core-pce-price-index-mm",              "USD", "US", 840, "US_CORE_PCE"},
   {"core-pce-price-index-yy",              "USD", "US", 840, "US_CORE_PCE"},
   {"nonfarm-payrolls",                     "USD", "US", 840, "US_NFP"},
   {"unemployment-rate",                    "USD", "US", 840, "US_UNEMPLOYMENT"},
   {"ecb-deposit-rate-decision",            "EUR", "EU", 999, "ECB_RATE_DECISION"},
   {"ecb-interest-rate-decision",           "EUR", "EU", 999, "ECB_RATE_DECISION"},
   {"consumer-price-index-yy",              "EUR", "EU", 999, "EUROZONE_CPI"},
   {"boe-interest-rate-decision",           "GBP", "GB", 826, "BOE_RATE_DECISION"},
   {"cpi-yy",                               "GBP", "GB", 826, "UK_CPI"},
   {"boj-interest-rate-decision",           "JPY", "JP", 392, "BOJ_RATE_DECISION"},
   {"eia-crude-oil-stocks-change",          "USD", "US", 840, "EIA_CRUDE_INVENTORIES"},
   {"gross-domestic-product-qq",            "USD", "US", 840, "US_GDP"},
   {"ism-manufacturing-pmi",                "USD", "US", 840, "US_ISM"},
   {"ism-non-manufacturing-pmi",            "USD", "US", 840, "US_ISM"},
   {"markit-manufacturing-pmi",             "USD", "US", 840, "US_MAJOR_PMI"},
   {"markit-services-pmi",                  "USD", "US", 840, "US_MAJOR_PMI"},
   {"markit-composite-pmi",                 "USD", "US", 840, "US_MAJOR_PMI"},
   {"fomc-meeting-statement",                "USD", "US", 840, "FOMC"},
   {"fomc-press-conference",                 "USD", "US", 840, "FOMC"},
};

//+------------------------------------------------------------------+
//| Exact-match lookup only. No StringFind/StringSubstr/regex of any  |
//| kind - a miss on any one of the four fields is a miss, full stop. |
//+------------------------------------------------------------------+
bool HighImpactEventMap_TryResolve(const string event_code,
                                    const string currency,
                                    const string country_code,
                                    const long   country_id,
                                    string       &canonical_code_out)
{
   int n = ArraySize(g_high_impact_event_map);
   for(int i = 0; i < n; i++)
   {
      if(g_high_impact_event_map[i].event_code   == event_code &&
         g_high_impact_event_map[i].currency      == currency &&
         g_high_impact_event_map[i].country_code  == country_code &&
         g_high_impact_event_map[i].country_id    == country_id)
      {
         canonical_code_out = g_high_impact_event_map[i].canonical_code;
         return true;
      }
   }
   canonical_code_out = "";
   return false;
}

#endif // HIGH_IMPACT_CALENDAR_BRIDGE_EVENT_MAP_MQH
