"""四類模板服務層（Epic 1 · 原 `database.py` 第 1545 行起的整段搬移：**純結構重構、零邏輯改動**）

職責：白名單常數 / 默認骨架 / `schema_json` 校驗層（只攔不清）/ 存取與狀態機（單事務歸檔舊 active）。
對齊：docs/epic1-template-design-v1.md §3（狀態機）、§4（版本規則）、§9（四類 schema_json 契約）、
      §9.4（藥味字段與白名單）、§10.2（錯誤碼）。

依賴方向（**單向**：本模組只在呼叫時才碰 `database`，絕不在 import 期反向 import）：
    1. `database.py` 頂部 re-export 本模組全部公開名 → 舊調用點 `database.validate_template_schema`
       等一字不改；若本模組在 import 期 `import database`，`database ↔ template_service` 會互相
       看到半初始化模組（ImportError），故連接與存量白名單一律走下方延遲 shim。
    2. 白名單常數仍定義在 `database.py`（`PRESCRIPTION_ROLES` / `PRESCRIPTION_COOKING_METHODS`，
       與前端 `HERB_ROLES` / `COOKING_METHODS` 同步），本模組只讀不寫、且**不清洗**（§9.4）。
"""
import json
import os
import re
import sqlite3
from datetime import datetime


def get_connection():
    """轉發 `database.get_connection()`（DB_PATH / row_factory 仍由 database.py 持有）。

    刻意保持同名：搬移前它就是本區塊所在模組的全域名，同名後下方 800 行程式碼一字不改。
    """
    import database
    return database.get_connection()


def _prescription_roles():
    """延遲取 `database.PRESCRIPTION_ROLES`（君臣佐使白名單）。"""
    import database
    return database.PRESCRIPTION_ROLES


def _prescription_cooking_methods():
    """延遲取 `database.PRESCRIPTION_COOKING_METHODS`（煎法白名單）。"""
    import database
    return database.PRESCRIPTION_COOKING_METHODS


# ============================================================================
# 【Epic 1 新增】四類模板（templates）：白名單 / 默認骨架 / 校驗層 / 存取與狀態機
# ============================================================================
# 對齊：docs/epic1-template-design-v1.md §3（狀態機）、§4（版本規則）、§9（四類 schema_json
#       字段級契約）、§10（CRUD 接口）、§11（發佈 / 歸檔 / 派生）、§12.4（legacy 兼容）。
#
# 本節五條紀律（寫在這裏即約束）：
#   1. `type` / `status` 不加 CHECK（存量全庫無 CHECK）→ Python 白名單 + 本層校驗，非法值一律 400，
#      **絕不清洗**（不對照 clean_prescription_role 的「不合法落成空串」語義）；
#   2. `schema_json` 原樣存 TEXT（`json.dumps(..., ensure_ascii=False)`，沿用 teacher_settings /
#      prescriptions.items_json 慣例）；未知鍵「忽略且原樣保留」，不補默認值、不刪鍵（前向兼容，§9.0）；
#   3. 校驗入口 `validate_template_schema(type, obj)` → `(ok, errors)`，errors = `[{"path","msg"}]`
#      （path 用 JS 風格，如 `fields[2].label`）；`validate_template_schema_for_publish()` 在其上疊加
#      「發佈級完整性」——草稿允許半成品，發佈必須完整（§9.0 校驗時機）；
#   4. `active` / `archived` 行內容不可原地改（§3.3，接口層回 409）；狀態機切換**全部在同一 SQLite
#      事務內**完成（先歸檔舊 active、再置新 active，順序不可換，否則瞬時違反 uq_templates_active_one，§11.1）；
#   5. 本模組是運行時讀寫入口，**不建表**：`templates` DDL 唯一來源是遷移 0001（§1.1 / §6.1）。
#
# 錯誤約定：服務層拋 `TemplateError(code, msg)`，由接口層（template_api.py）翻譯成真實 HTTP 狀態碼；
#           存在性 / 歸屬類錯誤由接口層在調用前攔（404 template_not_found / 403 template_forbidden）。

TEMPLATE_TYPES = ("inquiry", "record", "treatment", "prescription")
TEMPLATE_STATUSES = ("draft", "active", "archived")
# 顯示名（繁體古字，§9.1 表 / §13.2 頁簽文案）：新建時 name 的缺省值 + 前端頁簽徽章
TEMPLATE_TYPE_LABELS = {
    "inquiry": "問診",
    "record": "病歷",
    "treatment": "施治",
    "prescription": "開方",
}
TEMPLATE_SCHEMA_VERSION = 1                # 契約版本，Epic 1 恒為 1（§9.0）
TEMPLATE_MAX_STRING_LEN = 2000             # 單個字符串 ≤ 2000 字（§9.0）
TEMPLATE_MAX_SCHEMA_BYTES = 64 * 1024      # schema_json 序列化後 ≤ 64 KB（§9.0，超限 400 schema_too_large）
TEMPLATE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")   # fields[].key / sections[].key（§9.1 / §9.2）
ANSWER_TYPES = ("text", "number", "choice")               # inquiry fields[].answer_type
WRITABLE_BY_VALUES = ("ai", "teacher")                    # record sections[].writable_by（teacher = 智能體永不填）
TREATMENT_FORMATS = ("text",)                             # Epic 1 僅 text（blocks 預留，§9.3）
LEGACY_SOURCE_PLAN_TEMPLATES = "plan_templates"           # 與遷移 0001 的 meta.legacy_source 同名同值


class TemplateError(Exception):
    """模板服務層錯誤：帶機器碼，由接口層翻譯成 HTTP 狀態碼（映射表見 template_api.py）。"""

    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code
        self.msg = msg


# ---------- 默認骨架（§9.1 / §9.2 / §9.3 / §9.4）----------

# 十問歌默認骨架：key 與順序 = agent.TEN_QUESTIONS（agent.py:303-314），**順序不可變**；
# label / ask 按 §9.1 表給老師口徑的繁體古字（炁 / 氣 按語義區分，禁止全局簡繁替換）。
_DEFAULT_INQUIRY_FIELDS = (
    ("cold_heat", "寒熱", "你最近是怕冷多一點，還是怕熱多一點？"),
    ("sweat", "汗", "平時出汗多不多？是白天易汗，還是睡著了出汗？"),
    ("head_body", "頭身", "頭或身體有哪裏不舒服？頭暈、頭痛、身重痠沉？"),
    ("urine_stool", "二便", "大小便如何？有無乾結、稀軟、次數變多？"),
    ("diet", "飲食", "近來胃口與口味如何？吃東西香不香？"),
    ("chest_abdomen", "胸腹", "胸口或腹部有無發悶、發脹、隱隱作痛？"),
    ("ear", "耳", "耳朵有沒有響，或聽東西不太清楚？"),
    ("thirst", "口渴", "會覺得口渴嗎？想喝熱水還是涼水？"),
    ("old_illness", "舊病", "以前得過什麼病？有無長期服藥？"),
    ("cause", "病因", "這次不適大約從何時起？你覺得與什麼有關？"),
)

# 病歷默認骨架：對齊 agent.DOCTOR_PROMPT 的輸出模板 / main.build_draft_template（§9.2 表）。
# writable_by='teacher' = 智能體永不填內容（憲法硬約束：AI 永不辨證）。
_DEFAULT_RECORD_SECTIONS = (
    ("chief_complaint", "主訴（學生原話）", "ai"),
    ("past_records", "既往病歷參考", "ai"),
    ("tongue", "舌象", "teacher"),
    ("pulse", "脈象", "teacher"),
    ("pattern", "辨證", "teacher"),
    ("treatment_plan", "施治方案", "teacher"),
)

# tone.forbidden 默認值 = 術語鐵律詞表（agent.py:189-192「原文保留、不許換近義詞」，§9.2）
_DEFAULT_RECORD_FORBIDDEN = ("脈象", "舌象", "主訴", "現病史", "伴隨症狀", "辨證")


def default_template_schema(template_type):
    """該類型的默認骨架（每次返回全新副本，調用方可隨意改）。

    未知類型返回 None（由接口層回 400 `invalid_type`，本層不拋異常，方便探測調用）。
    """
    if template_type == "inquiry":
        return {
            "version": TEMPLATE_SCHEMA_VERSION,
            "fields": [
                {
                    "key": key,
                    "label": label,
                    "ask": ask,
                    "order": index + 1,
                    "required": False,
                    "answer_type": "text",
                    "choices": [],
                    "follow_up": "",
                }
                for index, (key, label, ask) in enumerate(_DEFAULT_INQUIRY_FIELDS)
            ],
            "meta": {},
        }
    if template_type == "record":
        return {
            "version": TEMPLATE_SCHEMA_VERSION,
            "sections": [
                {
                    "key": key,
                    "title": title,
                    "hint": "",
                    "order": index + 1,
                    "required": False,
                    "writable_by": writable_by,
                }
                for index, (key, title, writable_by) in enumerate(_DEFAULT_RECORD_SECTIONS)
            ],
            "tone": {"style": "", "forbidden": list(_DEFAULT_RECORD_FORBIDDEN)},
            "meta": {},
        }
    if template_type == "treatment":
        return {
            "version": TEMPLATE_SCHEMA_VERSION,
            "format": "text",
            "content": "",
            "placeholders": [],
            "meta": {},
        }
    if template_type == "prescription":
        return {
            "version": TEMPLATE_SCHEMA_VERSION,
            "herbs": [],
            "formulas": [],
            "defaults": {"cooking_method": "常规", "remote": False},
            "meta": {},
        }
    return None


# ---------- 校驗層（§9）：只攔截、不清洗 ----------

_MISSING = object()   # 區分「鍵缺失」與「值為 None / ''」


def _err(errors, path, msg):
    errors.append({"path": path, "msg": msg})


def _is_int(value):
    """布爾不是整數（`True` 會被 isinstance(..., int) 命中，必須排除）。"""
    return isinstance(value, int) and not isinstance(value, bool)


def _check_text(errors, path, value, *, required, max_len=None, min_len=0):
    """字串字段校驗。`required=True` 表示鍵必須存在（值可為空串，除非 min_len > 0）。"""
    if value is _MISSING or value is None:
        if required:
            _err(errors, path, "必填")
        return
    if not isinstance(value, str):
        _err(errors, path, "必須是字串")
        return
    if len(value) < min_len:
        _err(errors, path, "不得少於 %d 字" % min_len)
    if max_len is not None and len(value) > max_len:
        _err(errors, path, "不得超過 %d 字" % max_len)


def _check_bool(errors, path, value):
    if value is not _MISSING and value is not None and not isinstance(value, bool):
        _err(errors, path, "必須是布爾值")


def _check_order(errors, path, value):
    if value is _MISSING or value is None:
        _err(errors, path, "必填（>= 1 的整數）")
    elif not _is_int(value) or value < 1:
        _err(errors, path, "必須是 >= 1 的整數")


def _check_list(errors, path, value, *, max_items=None, min_items=None):
    """列表字段校驗；返回 True 表示類型正確（調用方可繼續逐項校驗）。"""
    if value is _MISSING or value is None:
        return False
    if not isinstance(value, list):
        _err(errors, path, "必須是陣列")
        return False
    if max_items is not None and len(value) > max_items:
        _err(errors, path, "最多 %d 項" % max_items)
    if min_items is not None and len(value) < min_items:
        _err(errors, path, "至少 %d 項" % min_items)
    return True


def _scan_items(items, errors, base, validator, unique_fields):
    """逐項校驗 + 組內唯一性（key / order / herb_name…）。`validator` 傳 None 表示只查唯一性。"""
    seen = {}
    for index, item in enumerate(items):
        path = "%s[%d]" % (base, index)
        if not isinstance(item, dict):
            _err(errors, path, "必須是 JSON 物件")
            continue
        if validator is not None:
            validator(item, errors, path)
        for field in unique_fields:
            value = item.get(field, _MISSING)
            if value is _MISSING or value is None or isinstance(value, bool) or not isinstance(value, (str, int)):
                continue
            bucket = seen.setdefault(field, {})
            if value in bucket:
                _err(errors, "%s.%s" % (path, field),
                     "%s 必須唯一（與 %s[%d] 重複）" % (field, base, bucket[value]))
            else:
                bucket[value] = index


def _validate_inquiry_field(item, errors, path):
    """§9.1 `fields[]` 一項。"""
    key = item.get("key", _MISSING)
    if key is _MISSING or key is None:
        _err(errors, path + ".key", "必填")
    elif not isinstance(key, str) or not TEMPLATE_KEY_RE.match(key):
        _err(errors, path + ".key", "鍵名需符合 ^[a-z][a-z0-9_]{0,31}$")
    _check_text(errors, path + ".label", item.get("label", _MISSING), required=True, min_len=1, max_len=16)
    _check_text(errors, path + ".ask", item.get("ask", _MISSING), required=False, max_len=120)
    _check_order(errors, path + ".order", item.get("order", _MISSING))
    _check_bool(errors, path + ".required", item.get("required", _MISSING))
    _check_text(errors, path + ".follow_up", item.get("follow_up", _MISSING), required=False, max_len=120)

    answer_type = item.get("answer_type", _MISSING)
    if answer_type is not _MISSING and answer_type is not None:
        if answer_type not in ANSWER_TYPES:
            _err(errors, path + ".answer_type", "只能是 text / number / choice")
        elif answer_type == "choice":
            _validate_choices(item.get("choices", _MISSING), errors, path + ".choices")


def _validate_choices(value, errors, path):
    """§9.1 `fields[].choices`：`answer_type='choice'` 時必填，2–12 項且去重。"""
    if value is _MISSING or value is None:
        _err(errors, path, "answer_type='choice' 時必填（2–12 項）")
        return
    if not _check_list(errors, path, value, min_items=2, max_items=12):
        return
    seen = set()
    for index, choice in enumerate(value):
        if not isinstance(choice, str) or not choice.strip():
            _err(errors, "%s[%d]" % (path, index), "選項必須是非空字串")
        elif choice in seen:
            _err(errors, "%s[%d]" % (path, index), "選項重複")
        else:
            seen.add(choice)


def _validate_record_section(item, errors, path):
    """§9.2 `sections[]` 一段。"""
    key = item.get("key", _MISSING)
    if key is _MISSING or key is None:
        _err(errors, path + ".key", "必填")
    elif not isinstance(key, str) or not TEMPLATE_KEY_RE.match(key):
        _err(errors, path + ".key", "鍵名需符合 ^[a-z][a-z0-9_]{0,31}$")
    _check_text(errors, path + ".title", item.get("title", _MISSING), required=True, min_len=1, max_len=20)
    _check_text(errors, path + ".hint", item.get("hint", _MISSING), required=False, max_len=120)
    _check_order(errors, path + ".order", item.get("order", _MISSING))
    _check_bool(errors, path + ".required", item.get("required", _MISSING))
    writable_by = item.get("writable_by", _MISSING)
    if writable_by is not _MISSING and writable_by is not None and writable_by not in WRITABLE_BY_VALUES:
        _err(errors, path + ".writable_by", "只能是 ai（智能體可填）/ teacher（留待老師）")


def _validate_herb_fields(item, errors, path, *, amount_key):
    """§9.4 藥味字段（`herbs[]` 與 `formulas[].composition[]` 共用，分量鍵名不同：default_amount / amount）。"""
    roles = _prescription_roles()               # database.PRESCRIPTION_ROLES（延遲取用）
    methods = _prescription_cooking_methods()    # database.PRESCRIPTION_COOKING_METHODS
    _check_text(errors, path + ".herb_name", item.get("herb_name", _MISSING), required=True, min_len=1, max_len=20)
    amount = item.get(amount_key, _MISSING)
    if amount is not _MISSING and amount is not None:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            _err(errors, path + "." + amount_key, "必須是數字")
        elif amount < 0 or amount > 1000:
            _err(errors, path + "." + amount_key, "只能是 0（未預填）或 0–1000 克")
    role = item.get("role", _MISSING)
    if role is not _MISSING and role is not None and role not in ("",) + roles:
        # 刻意「直接拒」：不走 clean_prescription_role 的清洗，否則老師會以為存成功了（§9.4）
        _err(errors, path + ".role", "君臣佐使只能是 君 / 臣 / 佐 / 使（或留空）")
    cooking_method = item.get("cooking_method", _MISSING)
    if cooking_method is not _MISSING and cooking_method is not None and cooking_method not in methods:
        _err(errors, path + ".cooking_method", "煎法只能是 %s" % " / ".join(methods))


def _validate_prescription_herb(item, errors, path):
    _validate_herb_fields(item, errors, path, amount_key="default_amount")
    order = item.get("order", _MISSING)
    if order is not _MISSING and order is not None and (not _is_int(order) or order < 1):
        _err(errors, path + ".order", "必須是 >= 1 的整數")


def _validate_formula(item, errors, path):
    """§9.4 `formulas[]`：`{name(≤20字), composition:[{herb_name, amount, role, cooking_method}]≤20}`。"""
    _check_text(errors, path + ".name", item.get("name", _MISSING), required=True, min_len=1, max_len=20)
    composition = item.get("composition", _MISSING)
    if composition is _MISSING or composition is None:
        return
    if not _check_list(errors, path + ".composition", composition, max_items=20):
        return
    for index, part in enumerate(composition):
        sub = "%s.composition[%d]" % (path, index)
        if not isinstance(part, dict):
            _err(errors, sub, "必須是 JSON 物件")
            continue
        _validate_herb_fields(part, errors, sub, amount_key="amount")
    _scan_items(composition, errors, path + ".composition", None, ("herb_name",))


def _validate_inquiry(schema_obj, errors):
    """§9.1：`3 ≤ len(fields) ≤ 20`（下限屬發佈級）；key / order 唯一，逐項見 `_validate_inquiry_field`。"""
    fields = schema_obj.get("fields", _MISSING)
    if fields is _MISSING or fields is None:
        _err(errors, "fields", "必填（陣列，發佈時 3–20 項）")
        return
    if not _check_list(errors, "fields", fields, max_items=20):
        return
    _scan_items(fields, errors, "fields", _validate_inquiry_field, ("key", "order"))


def _validate_record(schema_obj, errors):
    """§9.2：`2 ≤ len(sections) ≤ 12`（下限屬發佈級）+ `tone.style` / `tone.forbidden`。"""
    sections = schema_obj.get("sections", _MISSING)
    if sections is _MISSING or sections is None:
        _err(errors, "sections", "必填（陣列，發佈時 2–12 段）")
    elif _check_list(errors, "sections", sections, max_items=12):
        _scan_items(sections, errors, "sections", _validate_record_section, ("key", "order"))

    tone = schema_obj.get("tone", _MISSING)
    if tone is _MISSING or tone is None:
        return
    if not isinstance(tone, dict):
        _err(errors, "tone", "必須是 JSON 物件")
        return
    _check_text(errors, "tone.style", tone.get("style", _MISSING), required=False, max_len=120)
    forbidden = tone.get("forbidden", _MISSING)
    if forbidden is _MISSING or forbidden is None:
        return
    if not _check_list(errors, "tone.forbidden", forbidden, max_items=20):
        return
    for index, word in enumerate(forbidden):
        if not isinstance(word, str) or not word.strip():
            _err(errors, "tone.forbidden[%d]" % index, "必須是非空字串")


def _validate_treatment(schema_obj, errors):
    """§9.3：`format` 僅 text（Epic 1）；`content` 鍵必填（可為空串，發佈時不可為空）；`placeholders` ≤ 8 項。"""
    fmt = schema_obj.get("format", _MISSING)
    if fmt is not _MISSING and fmt is not None and fmt not in TREATMENT_FORMATS:
        _err(errors, "format", "Epic 1 僅支援 format='text'")
    _check_text(errors, "content", schema_obj.get("content", _MISSING), required=True, max_len=2000)
    placeholders = schema_obj.get("placeholders", _MISSING)
    if placeholders is _MISSING or placeholders is None:
        return
    if not _check_list(errors, "placeholders", placeholders, max_items=8):
        return
    for index, item in enumerate(placeholders):
        _check_text(errors, "placeholders[%d]" % index, item, required=True, min_len=1, max_len=60)


def _validate_prescription(schema_obj, errors):
    """§9.4：`len(herbs) ≤ 40`、`formulas ≤ 10`、`defaults` 白名單。"""
    methods = _prescription_cooking_methods()    # database.PRESCRIPTION_COOKING_METHODS
    herbs = schema_obj.get("herbs", _MISSING)
    if herbs is not _MISSING and herbs is not None and _check_list(errors, "herbs", herbs, max_items=40):
        _scan_items(herbs, errors, "herbs", _validate_prescription_herb, ("herb_name", "order"))
    formulas = schema_obj.get("formulas", _MISSING)
    if formulas is not _MISSING and formulas is not None and _check_list(errors, "formulas", formulas, max_items=10):
        _scan_items(formulas, errors, "formulas", _validate_formula, ("name",))
    defaults = schema_obj.get("defaults", _MISSING)
    if defaults is _MISSING or defaults is None:
        return
    if not isinstance(defaults, dict):
        _err(errors, "defaults", "必須是 JSON 物件")
        return
    cooking_method = defaults.get("cooking_method", _MISSING)
    if cooking_method is not _MISSING and cooking_method is not None and cooking_method not in methods:
        _err(errors, "defaults.cooking_method", "煎法只能是 %s" % " / ".join(methods))
    _check_bool(errors, "defaults.remote", defaults.get("remote", _MISSING))


def _check_string_lengths(node, errors, path):
    """§9.0：單個字符串 ≤ 2000 字（遞歸進未知鍵，防前端誤塞大文本）。"""
    if isinstance(node, str):
        if len(node) > TEMPLATE_MAX_STRING_LEN:
            _err(errors, path, "單個字串不得超過 %d 字" % TEMPLATE_MAX_STRING_LEN)
    elif isinstance(node, dict):
        for key, value in node.items():
            _check_string_lengths(value, errors, ("%s.%s" % (path, key)) if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _check_string_lengths(value, errors, "%s[%d]" % (path, index))


def validate_template_schema(template_type, schema_obj):
    """【格式校驗】§9 四類字段級契約。返回 `(ok, errors)`，errors = `[{"path","msg"}]`。

    只攔截、不清洗：非法值原樣報錯（例如 `role` 不在白名單 → 接口層 400 `schema_invalid`）；
    未知鍵忽略且原樣保留（前向兼容）；`version` 缺失視為 1（存量回填行沒有該鍵，派生後仍須可保存 / 發佈）。
    """
    errors = []
    if template_type not in TEMPLATE_TYPES:
        _err(errors, "type", "未知模板類型：%s" % template_type)
        return False, errors
    if not isinstance(schema_obj, dict):
        _err(errors, "", "schema_json 必須是 JSON 物件")
        return False, errors

    version = schema_obj.get("version", _MISSING)
    if version is not _MISSING and version is not None and (not _is_int(version) or version < 1):
        _err(errors, "version", "version 必須是 >= 1 的整數")
    meta = schema_obj.get("meta", _MISSING)
    if meta is not _MISSING and meta is not None and not isinstance(meta, dict):
        _err(errors, "meta", "meta 必須是 JSON 物件")

    if template_type == "inquiry":
        _validate_inquiry(schema_obj, errors)
    elif template_type == "record":
        _validate_record(schema_obj, errors)
    elif template_type == "treatment":
        _validate_treatment(schema_obj, errors)
    else:
        _validate_prescription(schema_obj, errors)

    _check_string_lengths(schema_obj, errors, "")
    return (not errors), errors


def validate_template_schema_for_publish(template_type, schema_obj):
    """【發佈級校驗】= 格式校驗 + 完整性（§9.1「至少 1 項必問」/ §9.2「至少 1 段留待老師」/ §9.3「content 非空」）。

    草稿允許半成品（`POST` / `PUT` 只跑格式校驗），發佈必須完整（§9.0 校驗時機）。
    """
    ok, errors = validate_template_schema(template_type, schema_obj)
    if not ok or not isinstance(schema_obj, dict):
        return False, errors

    if template_type == "inquiry":
        fields = schema_obj.get("fields") or []
        if len(fields) < 3:
            _err(errors, "fields", "發佈前至少要有 3 項問診（目前 %d 項）" % len(fields))
        if not any(isinstance(f, dict) and f.get("required") is True for f in fields):
            _err(errors, "fields", "發佈前請至少標記 1 項為「必問」")
    elif template_type == "record":
        sections = schema_obj.get("sections") or []
        if len(sections) < 2:
            _err(errors, "sections", "發佈前至少要有 2 段（目前 %d 段）" % len(sections))
        if not any(isinstance(s, dict) and s.get("writable_by") == "teacher" for s in sections):
            _err(errors, "sections", "發佈前請至少保留 1 段「留待老師」（智能體永不填寫）")
    elif template_type == "treatment":
        if not str(schema_obj.get("content") or "").strip():
            _err(errors, "content", "發佈前施治內容不可為空")
    return (not errors), errors


def serialize_template_schema(schema_obj):
    """序列化為 TEXT 存庫（§9.0）。超過 64 KB → `TemplateError('schema_too_large')`。"""
    text = json.dumps(schema_obj, ensure_ascii=False)
    if len(text.encode("utf-8")) > TEMPLATE_MAX_SCHEMA_BYTES:
        raise TemplateError(
            "schema_too_large",
            "模板內容超過 %d KB" % (TEMPLATE_MAX_SCHEMA_BYTES // 1024),
        )
    return text


def parse_template_schema(text):
    """反序列化；髒數據（非法 JSON / 非物件）一律降級為 `{}`，不讓列表 / 詳情接口 500。"""
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ---------- 存取與狀態機（§10 / §11）----------

_SCOPE_WHERE = "lineage_id = ? AND teacher_id = ? AND type = ?"


def template_store_ready():
    """`templates` 表是否就位：遷移未跑（或表被改名）→ False，接口層回 503 `template_store_unavailable`（§7）。"""
    try:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'templates'"
            ).fetchone()
        finally:
            conn.close()
        return row is not None
    except sqlite3.Error:
        return False


def _template_row_to_dict(row, include_schema=True):
    """模板行 → 接口響應物件（§10.1 表）。`is_legacy` = 存量回填而來（前端顯示「存量遷移」標籤）。"""
    data = dict(row)
    schema_obj = parse_template_schema(data.get("schema_json"))
    meta = schema_obj.get("meta")
    data["is_legacy"] = isinstance(meta, dict) and meta.get("legacy_source") == LEGACY_SOURCE_PLAN_TEMPLATES
    if include_schema:
        data["schema_json"] = schema_obj
    else:
        data.pop("schema_json", None)
    return data


def _fetch_template(cur, template_id):
    return cur.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()


def _find_scope_draft(cur, teacher_id, template_type, lineage_id=""):
    """同 scope 的草稿（語義上最多一條；取版本號最大者兜底）。§4.3 第 4 條：不產生第二份草稿。"""
    return cur.execute(
        "SELECT * FROM templates WHERE " + _SCOPE_WHERE + " AND status = 'draft' "
        "ORDER BY version DESC, id DESC LIMIT 1",
        (lineage_id, teacher_id, template_type),
    ).fetchone()


def _scope_max_version(cur, teacher_id, template_type, lineage_id=""):
    row = cur.execute(
        "SELECT MAX(version) AS v FROM templates WHERE " + _SCOPE_WHERE,
        (lineage_id, teacher_id, template_type),
    ).fetchone()
    return row["v"] or 0


def create_or_reuse_template(teacher_id, template_type, name, schema_obj, lineage_id=""):
    """§10.2 #4：同 scope 已有 `draft` → 複用（`reused=True`，不新建第二份草稿）；否則新建草稿。

    版本號：首次創建 = 1；同 scope 已有版本（例如存量回填的 v1 仍生效）→ 取下一號，
    保證鏈內 `version` 單調不重複（§4.2 公式在「無父版本」情形的退化，見 §4.2 公式說明）。
    返回 `(row, reused)`。
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        existing = _find_scope_draft(cur, teacher_id, template_type, lineage_id)
        if existing is not None:
            return _template_row_to_dict(existing), True
        version = _scope_max_version(cur, teacher_id, template_type, lineage_id) + 1
        now = datetime.now().isoformat()
        cur.execute(
            "INSERT INTO templates (type, lineage_id, teacher_id, name, schema_json, version, "
            "parent_template_id, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, 'draft', ?, ?)",
            (template_type, lineage_id, teacher_id, name, serialize_template_schema(schema_obj), version, now, now),
        )
        new_id = cur.lastrowid
        conn.commit()
        return _template_row_to_dict(_fetch_template(cur, new_id)), False
    finally:
        conn.close()


def get_template(template_id):
    """單條模板（含解析後的 `schema_json`）；不存在返回 None（接口層回 404）。"""
    conn = get_connection()
    try:
        row = _fetch_template(conn.cursor(), template_id)
    finally:
        conn.close()
    return _template_row_to_dict(row) if row is not None else None


def list_templates(teacher_id, template_type=None, status=None, include_schema=True):
    """§10.2 #1：該老師的模板列表（排序 `type asc, version desc`）+ 四類總數 `counts`。

    `counts` 是「該老師該類型全部模板數」，**不受** type / status 過濾影響（前端頁簽徽章用）。
    """
    conn = get_connection()
    try:
        conditions = ["teacher_id = ?"]
        params = [teacher_id]
        if template_type:
            conditions.append("type = ?")
            params.append(template_type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        rows = conn.execute(
            "SELECT * FROM templates WHERE " + " AND ".join(conditions) +
            " ORDER BY type ASC, version DESC, id DESC",
            params,
        ).fetchall()
        counts = {key: 0 for key in TEMPLATE_TYPES}
        for row in conn.execute(
            "SELECT type, COUNT(*) AS c FROM templates WHERE teacher_id = ? GROUP BY type", (teacher_id,)
        ):
            if row["type"] in counts:
                counts[row["type"]] = row["c"]
    finally:
        conn.close()
    return [_template_row_to_dict(row, include_schema) for row in rows], counts


def get_active_template(teacher_id, template_type, lineage_id=""):
    """§10.2 #3：該 scope 的生效模板；None = 無生效模板（生成側回落內置骨架，不報錯，§11.2）。"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM templates WHERE " + _SCOPE_WHERE + " AND status = 'active' LIMIT 1",
            (lineage_id, teacher_id, template_type),
        ).fetchone()
    finally:
        conn.close()
    return _template_row_to_dict(row) if row is not None else None


def list_template_chain(template_id):
    """§10.2 #2 的 `chain`：同 scope（lineage_id / teacher_id / type）全部版本，`version` 降序。

    Epic 1 `lineage_id` 恒為 `''`，故「鏈」= 該老師該類型的全部版本（§4.2 版本鏈）。
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        row = _fetch_template(cur, template_id)
        if row is None:
            return []
        rows = cur.execute(
            "SELECT id, version, status, updated_at FROM templates WHERE " + _SCOPE_WHERE +
            " ORDER BY version DESC, id DESC",
            (row["lineage_id"], row["teacher_id"], row["type"]),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def update_template_draft(template_id, name=None, schema_obj=None):
    """§10.2 #5：只允許改 `name` / `schema_json`，且只在 `draft` 狀態。

    `status != 'draft'` → `TemplateError('template_published_immutable')`（批復 3：已發佈版本不可原地改，
    前端據此改走「基於此版本修訂」→ §11.4 derive）。返回 `(row, changed)`。
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        row = _fetch_template(cur, template_id)
        if row is None:
            raise TemplateError("template_not_found", "找不到該模板")
        if row["status"] != "draft":
            raise TemplateError(
                "template_published_immutable",
                "已發佈或已歸檔的版本不可直接修改，請用「基於此版本修訂」派生新版本",
            )
        assignments = []
        params = []
        if name is not None:
            assignments.append("name = ?")
            params.append(name)
        if schema_obj is not None:
            assignments.append("schema_json = ?")
            params.append(serialize_template_schema(schema_obj))
        if not assignments:
            return _template_row_to_dict(row), False
        assignments.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(template_id)
        cur.execute("UPDATE templates SET " + ", ".join(assignments) + " WHERE id = ?", params)
        conn.commit()
        return _template_row_to_dict(_fetch_template(cur, template_id)), True
    finally:
        conn.close()


def _scope_active_ids(cur, teacher_id, template_type, lineage_id, exclude_id):
    return [
        row["id"]
        for row in cur.execute(
            "SELECT id FROM templates WHERE " + _SCOPE_WHERE + " AND status = 'active' AND id != ?",
            (lineage_id, teacher_id, template_type, exclude_id),
        )
    ]


def set_template_active(template_id):
    """§11.1 publish / §11.3 activate 共用的**原子**切換（同一 SQLite 事務）：

    ① SELECT 該 scope 現有 `active`（排除本行）→ ② UPDATE 這些行 → `archived`，id 收進 `archived_ids`
    → ③ UPDATE 本行 → `active` → ④ COMMIT。順序不可換：否則瞬時違反 `uq_templates_active_one`；
    失敗整體回滾 → 不會出現「scope 無 active」的空窗。返回 `(row, archived_ids, changed)`。
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        row = _fetch_template(cur, template_id)
        if row is None:
            raise TemplateError("template_not_found", "找不到該模板")
        stale = _scope_active_ids(cur, row["teacher_id"], row["type"], row["lineage_id"], template_id)
        if row["status"] == "active":
            if not stale:
                # §11.1 冪等：本行已是 active 且 scope 無其它 active → 200 changed=False
                return _template_row_to_dict(row), [], False
            # 理論上不可達（部分唯一索引已擋住兩條 active）；兜底按併發衝突處理，不悄悄改數據。
            raise TemplateError("template_active_conflict", "同一類型已存在生效版本，請重試")

        now = datetime.now().isoformat()
        archived_ids = list(stale)
        if archived_ids:
            placeholders = ", ".join("?" for _ in archived_ids)
            cur.execute(
                "UPDATE templates SET status = 'archived', updated_at = ? WHERE id IN (" + placeholders + ")",
                [now] + archived_ids,
            )
        cur.execute("UPDATE templates SET status = 'active', updated_at = ? WHERE id = ?", (now, template_id))
        conn.commit()
        return _template_row_to_dict(_fetch_template(cur, template_id)), archived_ids, True
    except TemplateError:
        conn.rollback()
        raise
    except sqlite3.IntegrityError as exc:
        # §11.1 併發兜底：翻譯成 409 template_active_conflict（附「請重試」），不暴露原始錯誤
        conn.rollback()
        raise TemplateError("template_active_conflict", "同一類型已存在生效版本，請重試") from exc
    finally:
        conn.close()


def archive_template(template_id):
    """§11.2：`active` / `draft` → `archived`；已是 `archived` → 冪等 `changed=False`。返回 `(row, changed)`。"""
    conn = get_connection()
    try:
        cur = conn.cursor()
        row = _fetch_template(cur, template_id)
        if row is None:
            raise TemplateError("template_not_found", "找不到該模板")
        if row["status"] == "archived":
            return _template_row_to_dict(row), False
        cur.execute(
            "UPDATE templates SET status = 'archived', updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), template_id),
        )
        conn.commit()
        return _template_row_to_dict(_fetch_template(cur, template_id)), True
    finally:
        conn.close()


def derive_template_from(source_id, teacher_id, parent_template_id=None, name=None):
    """§11.4 派生新版本（前端「基於此版本修訂」）。返回 `(row, reused_draft)`。

    強校驗（§4.3 五條，全部走 TemplateError → 接口層 400 / 403）：
      ① 來源（即父版本）必須存在 → `template_parent_not_found`；
      ② 父與來源必須同 `teacher_id` / `lineage_id` / `type` → `template_parent_scope_mismatch`
         （`parent_template_id` 由前端可選上報，必須與路徑來源一致，禁跨老師 / 跨師門 / 跨類型掛鏈）；
      ③ 自引用（行的 `parent_template_id` 指向自身，髒數據）→ `template_parent_self_reference`；
      ④ 不可派生指向未來版本的行 → `template_parent_future_version`；
      ⑤ 同鏈已有 `draft` → **複用該行**（不產生第二份草稿）。

    版本號 = `max(父版本 + 1, 鏈內現有 max(version) + 1)`（§4.2：單調遞增，處理「歸檔草稿占用版本號」）。
    新草稿的 `schema_json` 逐字節複製父行（凍結快照，§4.4 歷史零回溯）。
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        source = _fetch_template(cur, source_id)
        if source is None:
            raise TemplateError("template_parent_not_found", "找不到要修訂的版本")
        if source["teacher_id"] != teacher_id:
            raise TemplateError("template_parent_scope_mismatch", "不可跨老師修訂模板")
        if parent_template_id is not None and parent_template_id != source_id:
            parent = _fetch_template(cur, parent_template_id)
            if parent is None:
                raise TemplateError("template_parent_not_found", "找不到指定的父版本")
            if (parent["teacher_id"], parent["lineage_id"], parent["type"]) != (
                source["teacher_id"], source["lineage_id"], source["type"]
            ):
                raise TemplateError("template_parent_scope_mismatch", "父版本與來源不屬於同一老師 / 師門 / 類型")
            raise TemplateError("template_parent_scope_mismatch", "parent_template_id 必須與來源模板一致")
        if source["parent_template_id"] == source["id"]:
            raise TemplateError("template_parent_self_reference", "父版本不可指向自身")
        scope_max = _scope_max_version(cur, source["teacher_id"], source["type"], source["lineage_id"])
        if source["version"] > scope_max:
            raise TemplateError("template_parent_future_version", "不可基於未來版本修訂")
        existing_draft = _find_scope_draft(cur, source["teacher_id"], source["type"], source["lineage_id"])
        if existing_draft is not None:
            return _template_row_to_dict(existing_draft), True

        now = datetime.now().isoformat()
        cur.execute(
            "INSERT INTO templates (type, lineage_id, teacher_id, name, schema_json, version, "
            "parent_template_id, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)",
            (
                source["type"],
                source["lineage_id"],
                source["teacher_id"],
                name or source["name"],
                source["schema_json"],
                max(source["version"] + 1, scope_max + 1),
                source_id,
                now,
                now,
            ),
        )
        new_id = cur.lastrowid
        conn.commit()
        return _template_row_to_dict(_fetch_template(cur, new_id)), False
    finally:
        conn.close()


def template_herb_warnings(teacher_name, schema_obj):
    """§9.4：`prescription` 模板裏的藥材不在該老師 `herb_inventory` → **200 通過** + `warnings` 黃字提醒。

    不阻斷保存（老師可能先配模板、後補庫存）。返回 `[{"code": "herb_not_in_inventory", "herb_name": …}]`。
    """
    if not isinstance(schema_obj, dict):
        return []
    names = []
    for herb in schema_obj.get("herbs") or []:
        if isinstance(herb, dict) and isinstance(herb.get("herb_name"), str) and herb["herb_name"]:
            names.append(herb["herb_name"])
    for formula in schema_obj.get("formulas") or []:
        if not isinstance(formula, dict):
            continue
        for part in formula.get("composition") or []:
            if isinstance(part, dict) and isinstance(part.get("herb_name"), str) and part["herb_name"]:
                names.append(part["herb_name"])
    if not names:
        return []
    conn = get_connection()
    try:
        known = {
            row["herb_name"]
            for row in conn.execute("SELECT herb_name FROM herb_inventory WHERE teacher_name = ?", (teacher_name,))
        }
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    warnings = []
    seen = set()
    for herb_name in names:
        if herb_name in known or herb_name in seen:
            continue
        seen.add(herb_name)
        warnings.append({"code": "herb_not_in_inventory", "herb_name": herb_name})
    return warnings


# ---------- 生成接入與 legacy 雙寫（§12.2 / §12.4）----------

# feature flag 取值語義（與 template_api.py 的 `_enabled()` 同一套；默認 off，§5.2 第 5 條）
TEMPLATE_API_ENABLED_VALUES = ("on", "1", "true", "yes")


def template_api_enabled():
    """`TEMPLATE_API_ENABLED` 每次調用現讀（便於灰度切換 / 測試，不必重啟）。**默認 off。**

    這是兩條「非接口」路徑的唯一閘門（與 `/api/templates*` 的 404 同一語義，§5.2 第 5 條）：
      · 舊寫入通道的單向雙寫（`sync_legacy_plan_template`，§12.4）；
      · 生成接入取生效 `record` 模板（`get_active_record_template`，§12.2）。
    flag off = 與今天 1:1：不讀 `templates`、不寫 `templates`、生成輸出一字不改。
    """
    return os.environ.get("TEMPLATE_API_ENABLED", "off").strip().lower() in TEMPLATE_API_ENABLED_VALUES


def get_active_record_template(teacher_name):
    """§12.2：生成前取該老師生效的 `record` 模板（`None` = **走今天的既有路徑**，§3.4）。

    降級口徑（任一命中即返回 None，不拋異常、不打斷生成）：
      flag off / `templates` 表未就緒（遷移未跑）/ 該 scope 無 `active` / 讀庫異常（表被改名、庫被鎖）/
      `schema_json.version` 非本版本支持的 `TEMPLATE_SCHEMA_VERSION`（§12.2 第 2 條：版本不支持也走今天路徑）。
    """
    if not template_api_enabled():
        return None
    try:
        if not template_store_ready():
            return None
        row = get_active_template(teacher_name, "record")
        if row is None:
            return None
        schema_obj = row.get("schema_json")
        if not isinstance(schema_obj, dict) or schema_obj.get("version") != TEMPLATE_SCHEMA_VERSION:
            print(
                "[warn] 病歷模板 schema 版本不受支持（生成側回落今天路徑）：template_id=%s"
                % row.get("id")
            )
            return None
        return row
    except sqlite3.Error as exc:
        print(
            "[warn] 取生效病歷模板失敗（生成側回落今天路徑）：%s: %s" % (type(exc).__name__, exc)
        )
        return None
    except sqlite3.Error as exc:
        print(
            "[warn] 取生效病歷模板失敗（生成側回落今天路徑）：%s: %s" % (type(exc).__name__, exc)
        )
        return None


def record_section_skeleton(template_row):
    """§12.2：active `record` 模板 → 交給生成智能體的「段落骨架提示」文本（多行）。

    `writable_by='teacher'` 的段一律標註「（留待老師）」：AI 永不填舌象 / 脈象 / 辨證 / 施治方案
    （憲法硬約束，§12.2 第 4 條）。`template_row` 形狀不對 / 無有效段落 → 空串（＝生成側一個字都不加）。
    """
    schema_obj = (template_row or {}).get("schema_json")
    if not isinstance(schema_obj, dict):
        return ""
    lines = []
    for section in schema_obj.get("sections") or []:
        if not isinstance(section, dict):
            continue
        title = section.get("title") or section.get("key") or ""
        if not title:
            continue
        lines.append("- %s%s" % (title, "（留待老師）" if section.get("writable_by") == "teacher" else ""))
    return "\n".join(lines)


def sync_legacy_plan_template(teacher_name, content):
    """§5.2 第 4 條 / §12.4：legacy 通道（`plan_templates`）→ 新表（`templates`）單向雙寫，**永不反向**。

    調用前提：`plan_templates` 已寫入並 `COMMIT`（舊接口的成功已 100% 落地）。本函數的異常
    **由調用方 catch 成日誌告警**（§12.4：`templates` 壞掉不能連帶舊接口 500）。返回 dict 或 None：

    · flag off → None（今天行為 1:1，一個字都不寫）；
    · 同 scope 已有 `draft` → **原地更新**該草稿的 `schema_json.content`（草稿可變，§3.3），
      其餘鍵（placeholders / 未知鍵）原樣保留；
    · 同 scope 無 `draft` → **派生新草稿**（`active` 是凍結快照，永不原地改，§3.3）：
      父 = 同 scope 的 `active`（若有，含存量回填行），`version = max(父+1, 鏈內 max+1)`；
      無 `active` 則為該 scope 首版（`name` = 類型顯示名「施治」）；
    · `content` 為空且無 `draft` → None（與 `get_plan_template` 的空語義一致：空 = 沒有模板；
      但**已有草稿**時仍同步為空 —— 老師清空後，新接口看到的也是空草稿）。

    派生行的 `meta.legacy_source` 會被移除：「存量遷移」標籤只屬於遷移 0001 的回填行，
    這條草稿的內容是老師在舊鏈路上寫的，不該被標成遷移行。
    """
    if not template_api_enabled():
        return None

    conn = get_connection()
    try:
        cur = conn.cursor()
        now = datetime.now().isoformat()

        draft = _find_scope_draft(cur, teacher_name, "treatment")
        if draft is not None:
            schema_obj = parse_template_schema(draft["schema_json"])
            schema_obj["content"] = content or ""
            cur.execute(
                "UPDATE templates SET schema_json = ?, updated_at = ? WHERE id = ?",
                (serialize_template_schema(schema_obj), now, draft["id"]),
            )
            conn.commit()
            return {"draft_id": draft["id"], "version": draft["version"], "derived": False}

        if not (content or "").strip():
            return None

        active = cur.execute(
            "SELECT * FROM templates WHERE " + _SCOPE_WHERE + " AND status = 'active' "
            "ORDER BY version DESC, id DESC LIMIT 1",
            ("", teacher_name, "treatment"),
        ).fetchone()
        if active is not None:
            schema_obj = parse_template_schema(active["schema_json"])
            parent_id = active["id"]
            version = max(active["version"] + 1, _scope_max_version(cur, teacher_name, "treatment") + 1)
            name = active["name"]
        else:
            schema_obj = default_template_schema("treatment")
            parent_id = None
            version = _scope_max_version(cur, teacher_name, "treatment") + 1
            name = TEMPLATE_TYPE_LABELS["treatment"]

        meta = schema_obj.get("meta")
        if isinstance(meta, dict):
            # 「存量遷移」標籤的判定鍵是 `meta.legacy_source`（見 `_template_row_to_dict()` 的 is_legacy）：
            # 派生草稿的內容是老師在舊鏈路寫的，去掉這個鍵才不會被標成回填行。
            meta.pop("legacy_source", None)
        schema_obj["content"] = content

        cur.execute(
            "INSERT INTO templates (type, lineage_id, teacher_id, name, schema_json, version, "
            "parent_template_id, status, created_at, updated_at) "
            "VALUES ('treatment', '', ?, ?, ?, ?, ?, 'draft', ?, ?)",
            (teacher_name, name, serialize_template_schema(schema_obj), version, parent_id, now, now),
        )
        new_id = cur.lastrowid
        conn.commit()
        return {"draft_id": new_id, "version": version, "derived": True}
    finally:
        conn.close()
