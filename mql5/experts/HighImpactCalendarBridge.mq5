//+------------------------------------------------------------------+
//| HighImpactCalendarBridge.mq5                                      |
//|                                                                    |
//| Read-only MQL5 Economic Calendar producer for the High-Impact      |
//| Event Risk Gate bridge. Publishes a local FILE_COMMON JSON file    |
//| the Python side (app.high_impact_event_bridge.file_reader) reads.  |
//|                                                                    |
//| SAFETY: this Expert Advisor performs NO trading of any kind. It    |
//| contains no OrderSend, no CTrade, no position/pending-order        |
//| operations, no WebRequest, no DLL imports (no #import), no         |
//| sockets. It only reads the built-in Economic Calendar API and      |
//| writes one local FILE_COMMON file. OnTick is deliberately not      |
//| implemented - there is no tick-driven behavior of any kind.        |
//|                                                                    |
//| TIMEZONE: MqlCalendarValue.time is trade-SERVER-local time. This   |
//| EA never appends "Z" to it and never claims it is UTC - MQL5       |
//| exposes no API that can prove a broker's server-clock offset for  |
//| an arbitrary FUTURE date (only TimeGMT()/TimeTradeServer() "now"). |
//| event_time_server is emitted as a naive (no timezone suffix) wall- |
//| clock string; the Python-side adapter performs the actual,        |
//| DST-safe UTC conversion via an operator-declared IANA timezone     |
//| (zoneinfo carries forward-published DST rules MQL5 does not        |
//| expose). observed_offset_seconds is carried for operator           |
//| audit/drift-detection only and must never be used as a substitute  |
//| conversion. generated_at IS a producer "now" fact (not a calendar  |
//| value) and is emitted as an aware, "Z"-suffixed UTC instant via    |
//| TimeGMT(), per the approved design closure.                        |
//+------------------------------------------------------------------+
#property strict
#property description "Read-only High-Impact Calendar Bridge producer. No trading of any kind."

#include "..\include\HighImpactCalendarBridge_EventMap.mqh"

input string InpTargetFileName = "high_impact_calendar_bridge.json"; // FILE_COMMON-relative target path
input int    InpTimerSeconds   = 300;                                 // refresh cadence (5 minutes)
input int    InpPastMinutes    = 30;                                  // export window: look-back
input int    InpFutureHours    = 48;                                  // export window: look-ahead

const string PRODUCER_NAME    = "mt5_calendar_bridge";
const int    SCHEMA_VERSION   = 2; // event_time -> event_time_server + observed_offset_seconds is a wire-incompatible change

//+------------------------------------------------------------------+
int OnInit()
{
   PublishHighImpactCalendarSnapshot();
   EventSetTimer(InpTimerSeconds);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
}

//+------------------------------------------------------------------+
void OnTimer()
{
   PublishHighImpactCalendarSnapshot();
}

// Deliberately no OnTick(): this EA has no tick-driven behavior at all.

//+------------------------------------------------------------------+
//| Query the calendar, build one JSON snapshot, and publish it - or  |
//| leave the previously-published file untouched on query failure.  |
//+------------------------------------------------------------------+
void PublishHighImpactCalendarSnapshot()
{
   datetime now_server = TimeTradeServer();
   datetime from_time   = now_server - InpPastMinutes * 60;
   datetime to_time     = now_server + InpFutureHours * 3600;

   MqlCalendarValue values[];
   int count = CalendarValueHistory(values, from_time, to_time, NULL, NULL);

   if(count < 0)
   {
      PrintFormat("HighImpactCalendarBridge: CalendarValueHistory failed (err=%d) - query failure, "
                  "NOT publishing, previous published file (if any) is left untouched", GetLastError());
      return;
   }

   // count == 0 (successful, zero provider rows) and count > 0 but zero
   // mapped V1 events both fall through to the same fresh "events": []
   // publish below - both are genuine, current, successful facts.

   long observed_offset_seconds = (long)(TimeGMT() - TimeTradeServer());

   string events_json = "";
   int emitted = 0;

   for(int i = 0; i < count; i++)
   {
      MqlCalendarEvent event_info;
      if(!CalendarEventById(values[i].event_id, event_info))
         continue; // unknown/unavailable event metadata - ignore, never fabricate

      MqlCalendarCountry country_info;
      if(!CalendarCountryById(event_info.country_id, country_info))
         continue; // unresolvable country - ignore, never fabricate

      string canonical_code = "";
      bool mapped = HighImpactEventMap_TryResolve(
         event_info.event_code, country_info.currency, country_info.code, event_info.country_id, canonical_code);
      if(!mapped)
         continue; // unknown/unmapped MetaQuotes event - ignore, never invent a canonical code

      string provider_event_id  = IntegerToString((long)event_info.id) + ":" + IntegerToString((long)values[i].id);
      string event_time_server  = ServerTimeToNaiveIsoText(values[i].time);
      string importance_text    = CalendarImportanceToText(event_info.importance);

      if(emitted > 0)
         events_json += ",";
      events_json += "{";
      events_json += "\"provider_event_id\":\"" + JsonEscapeText(provider_event_id) + "\",";
      events_json += "\"event_time_server\":\"" + event_time_server + "\",";
      events_json += "\"observed_offset_seconds\":" + IntegerToString((int)observed_offset_seconds) + ",";
      events_json += "\"importance\":\"" + importance_text + "\",";
      events_json += "\"scope\":[\"" + JsonEscapeText(country_info.currency) + "\"],";
      events_json += "\"event_code\":\"" + JsonEscapeText(canonical_code) + "\",";
      events_json += "\"name\":\"" + JsonEscapeText(event_info.name) + "\"";
      events_json += "}";
      emitted++;
   }

   string generated_at = ServerNowToUtcIsoText();

   string body = "{";
   body += "\"schema_version\":" + IntegerToString(SCHEMA_VERSION) + ",";
   body += "\"producer\":\"" + PRODUCER_NAME + "\",";
   body += "\"generated_at\":\"" + generated_at + "\",";
   body += "\"events\":[" + events_json + "]";
   body += "}";

   if(!WriteAndPublishJson(body))
      Print("HighImpactCalendarBridge: publication failed - previous published file (if any) remains the live one");
}

//+------------------------------------------------------------------+
//| Write-to-temp-then-FileMove publish. MQL5 documents no guaranteed |
//| atomicity for FileMove - this is a best-effort replace, never     |
//| claimed as atomic. On any failure, no fabricated success is       |
//| reported and the previously-published target file is left as-is  |
//| (this function never deletes the target itself).                 |
//+------------------------------------------------------------------+
bool WriteAndPublishJson(const string &json_body)
{
   string tmp_name = InpTargetFileName + ".tmp";

   int handle = FileOpen(tmp_name, FILE_WRITE | FILE_BIN | FILE_COMMON);
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("HighImpactCalendarBridge: FileOpen(%s) failed, err=%d", tmp_name, GetLastError());
      return false;
   }

   uchar utf8_bytes[];
   int encoded_len = StringToCharArray(json_body, utf8_bytes, 0, -1, CP_UTF8);
   // StringToCharArray appends a trailing NUL terminator - do not write it.
   int write_len = (encoded_len > 0) ? encoded_len - 1 : 0;
   if(write_len > 0)
      FileWriteArray(handle, utf8_bytes, 0, write_len);
   FileClose(handle);

   bool moved = FileMove(tmp_name, FILE_COMMON, InpTargetFileName, FILE_COMMON | FILE_REWRITE);
   if(!moved)
   {
      PrintFormat("HighImpactCalendarBridge: FileMove(%s -> %s) failed, err=%d - target left untouched",
                  tmp_name, InpTargetFileName, GetLastError());
      FileDelete(tmp_name, FILE_COMMON);
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Naive (no timezone suffix) trade-server-local ISO-8601 text.      |
//| Deliberately NEVER "Z"-suffixed - this is not claimed to be UTC.  |
//+------------------------------------------------------------------+
string ServerTimeToNaiveIsoText(datetime server_time)
{
   string text = TimeToString(server_time, TIME_DATE | TIME_SECONDS); // "yyyy.mm.dd hh:mi:ss"
   StringReplace(text, ".", "-");
   StringReplace(text, " ", "T");
   return text; // e.g. "2027-03-14T13:30:00"
}

//+------------------------------------------------------------------+
//| Aware, "Z"-suffixed UTC "now" via TimeGMT() - a producer-authored |
//| fact about this write, never a calendar value.                    |
//+------------------------------------------------------------------+
string ServerNowToUtcIsoText()
{
   datetime gmt_now = TimeGMT();
   string text = TimeToString(gmt_now, TIME_DATE | TIME_SECONDS);
   StringReplace(text, ".", "-");
   StringReplace(text, " ", "T");
   return text + "Z";
}

//+------------------------------------------------------------------+
string CalendarImportanceToText(const ENUM_CALENDAR_EVENT_IMPORTANCE importance)
{
   switch(importance)
   {
      case CALENDAR_IMPORTANCE_HIGH:     return "HIGH";
      case CALENDAR_IMPORTANCE_MODERATE: return "MODERATE";
      case CALENDAR_IMPORTANCE_LOW:      return "LOW";
      default:                           return "NONE";
   }
}

//+------------------------------------------------------------------+
string JsonEscapeText(const string raw_text)
{
   string escaped = raw_text;
   StringReplace(escaped, "\\", "\\\\");
   StringReplace(escaped, "\"", "\\\"");
   return escaped;
}
