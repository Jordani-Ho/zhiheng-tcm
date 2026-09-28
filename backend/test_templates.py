"""【Epic 1】四類模板 CRUD / 校驗層 / 狀態機 守護測試

覆蓋設計 §9（四類 schema_json 字段級契約）、§10（CRUD 接口）、§11（發佈 / 歸檔 / 派生），
以及 §14.1 測試清單的 B / C / D / E 組與 F 組中屬於本子任務的三條（兼容 / 零回溯 / flag off）。

運行方式：
    cd backend
    ..\\venv\\Scripts\\python.exe -m pytest test_templates.py -v

前置：`conftest.py` 已把 `TEMPLATE_API_ENABLED` 置為 `on`（默認 off 的分支由
`test_templates_flag_off_returns_404` 自行 monkeypatch 覆蓋）。
"""
import json

import agent
import database

TEACHER = "李老师"
OTHER_TEACHER = "王老师"


# ============ 測試輔助 ============

def _auth(teacher=TEACHER, **extra):
    """帶齊 teacher_name / teacher_id 的鑑權參數（§10.1）。"""
    body = {"teacher_name": teacher, "teacher_id": teacher}
    body.update(extra)
    return body


def _create(client, template_type, schema=None, name=None, teacher=TEACHER):
    body = _auth(teacher, type=template_type)
    if name is not None:
        body["name"] = name
    if schema is not None:
        body["schema_json"] = schema
    return client.post("/api/templates", json=body)


def _publishable(template_type):
    """在默認骨架上補足「發佈級完整性」（§9）：問診至少 1 項必問、施治內容非空。"""
    schema = database.default_template_schema(template_type)
    if template_type == "inquiry":
        schema["fields"][0]["required"] = True
    elif template_type == "treatment":
        schema["content"] = "疏肝理氣，健脾和胃；忌生冷。"
    return schema


def _published(client, template_type, schema=None, teacher=TEACHER):
    """建草稿 → 發佈，返回 `(id, publish 響應體)`。"""
    payload = _publishable(template_type) if schema is None else schema
    created = _create(client, template_type, payload, teacher=teacher)
    assert created.status_code == 201, created.text
    template_id = created.json()["template"]["id"]
    published = client.post("/api/templates/%d/publish" % template_id, json=_auth(teacher))
    assert published.status_code == 200, published.text
    return template_id, published.json()


def _GET(client, template_id, teacher=TEACHER):
    return client.get("/api/templates/%d" % template_id, params=_auth(teacher))


# ============ B. CRUD ============

def test_create_default_skeleton_per_type(client):
    """四類不傳 schema_json → 默認骨架符合 §9 契約（問診 10 項 / 病歷 6 段 / 施治空 / 開方空）。"""
    schemas = {}
    for template_type in database.TEMPLATE_TYPES:
        r = _create(client, template_type)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["reused"] is False
        assert body["warnings"] == []
        tpl = body["template"]
        assert tpl["type"] == template_type
        assert tpl["status"] == "draft"
        assert tpl["version"] == 1
        assert tpl["parent_template_id"] is None
        assert tpl["lineage_id"] == ""
        assert tpl["teacher_id"] == TEACHER
        assert tpl["name"] == database.TEMPLATE_TYPE_LABELS[template_type]
        assert tpl["is_legacy"] is False
        assert tpl["created_at"] and tpl["updated_at"]
        assert tpl["schema_json"]["version"] == 1
        schemas[template_type] = tpl["schema_json"]

    # 問診：十問歌順序（agent.TEN_QUESTIONS 不可變，§9.1）
    assert [f["key"] for f in schemas["inquiry"]["fields"]] == [
        "cold_heat", "sweat", "head_body", "urine_stool", "diet",
        "chest_abdomen", "ear", "thirst", "old_illness", "cause",
    ]
    assert [f["order"] for f in schemas["inquiry"]["fields"]] == list(range(1, 11))
    assert len(agent.TEN_QUESTIONS) == len(schemas["inquiry"]["fields"])
    # 病歷：五段式 + 「留待老師」4 段（AI 永不辨證）+ 術語鐵律詞表
    assert [s["key"] for s in schemas["record"]["sections"]] == [
        "chief_complaint", "past_records", "tongue", "pulse", "pattern", "treatment_plan",
    ]
    assert [s["writable_by"] for s in schemas["record"]["sections"]].count("teacher") == 4
    assert schemas["record"]["tone"]["forbidden"] == ["脈象", "舌象", "主訴", "現病史", "伴隨症狀", "辨證"]
    # 施治：承載舊 plan_templates.content
    assert schemas["treatment"]["format"] == "text" and schemas["treatment"]["content"] == ""
    # 開方：空藥味 + 空方劑 + 默認煎法
    assert schemas["prescription"]["herbs"] == [] and schemas["prescription"]["formulas"] == []
    assert schemas["prescription"]["defaults"] == {"cooking_method": "常规", "remote": False}


def test_create_reuses_existing_draft(client):
    """同 scope 二次 POST → 200 + reused=True，id 相同（冪等，不產生第二份草稿）。"""
    first = _create(client, "inquiry")
    assert first.status_code == 201
    first_id = first.json()["template"]["id"]

    again = _create(client, "inquiry", database.default_template_schema("inquiry"), name="改名試探")
    assert again.status_code == 200, again.text
    assert again.json()["reused"] is True
    assert again.json()["template"]["id"] == first_id
    assert again.json()["template"]["name"] == database.TEMPLATE_TYPE_LABELS["inquiry"]   # 複用不改名


def test_list_filter_by_type_and_status(client):
    """四類過濾 / 狀態過濾 / 排序 type asc, version desc / include_schema=0 省流量。"""
    inquiry_id, _ = _published(client, "inquiry")
    _create(client, "record")
    _create(client, "treatment")
    _create(client, "prescription")

    body = client.get("/api/templates", params=_auth()).json()
    assert len(body["templates"]) == 4
    types = [t["type"] for t in body["templates"]]
    assert types == sorted(types)
    assert body["counts"] == {"inquiry": 1, "record": 1, "treatment": 1, "prescription": 1}

    only_inquiry = client.get("/api/templates", params=_auth(type="inquiry")).json()
    assert [t["id"] for t in only_inquiry["templates"]] == [inquiry_id]
    assert only_inquiry["counts"]["record"] == 1        # counts 不受過濾影響

    drafts = client.get("/api/templates", params=_auth(status="draft")).json()
    assert len(drafts["templates"]) == 3
    assert all(t["status"] == "draft" for t in drafts["templates"])

    slim = client.get("/api/templates", params=_auth(include_schema=0)).json()
    assert all("schema_json" not in t for t in slim["templates"])

    bad_type = client.get("/api/templates", params=_auth(type="unknown"))
    assert bad_type.status_code == 400 and bad_type.json()["detail"]["error"] == "invalid_type"
    bad_status = client.get("/api/templates", params=_auth(status="published"))
    assert bad_status.status_code == 400 and bad_status.json()["detail"]["error"] == "invalid_status"


def test_get_single_with_chain(client):
    """詳情帶 `chain`：鏈上全部版本，按 version 降序（§10.2 #2）。"""
    v1_id, _ = _published(client, "treatment")
    derived = client.post("/api/templates/%d/derive" % v1_id, json=_auth())
    assert derived.status_code == 201, derived.text
    v2_id = derived.json()["template"]["id"]

    r = _GET(client, v2_id)
    assert r.status_code == 200
    body = r.json()
    assert body["template"]["id"] == v2_id
    assert body["generated_count"] == 0
    chain = body["chain"]
    assert set(chain[0].keys()) == {"id", "version", "status", "updated_at"}
    assert [c["version"] for c in chain] == [2, 1]
    assert [c["status"] for c in chain] == ["draft", "active"]
    assert chain[1]["id"] == v1_id


def test_no_delete_endpoint(client):
    """§10.1：不提供 DELETE（路由不存在 → 405 / 404）。"""
    _published(client, "treatment")
    r = client.delete("/api/templates/1", params=_auth())
    assert r.status_code in (404, 405)


# ============ C. 鑑權與參數 ============

def test_teacher_name_id_mismatch_403(client):
    """teacher_name != teacher_id → 403 teacher_mismatch（GET 走 query、POST / PUT 走 body）。"""
    r = client.post("/api/templates", json={"teacher_name": TEACHER, "teacher_id": OTHER_TEACHER, "type": "inquiry"})
    assert r.status_code == 403 and r.json()["detail"]["error"] == "teacher_mismatch"

    r = client.get("/api/templates", params={"teacher_name": TEACHER, "teacher_id": OTHER_TEACHER})
    assert r.status_code == 403 and r.json()["detail"]["error"] == "teacher_mismatch"

    tpl_id, _ = _published(client, "treatment")
    r = client.put("/api/templates/%d" % tpl_id, json={"teacher_name": TEACHER, "teacher_id": OTHER_TEACHER, "name": "x"})
    assert r.status_code == 403


def test_cross_teacher_access_403(client):
    """他人模板：讀 / 改 / 發佈 / 歸檔 / 派生一律 403，且不回行內容、列表不含他人行。"""
    tpl_id, _ = _published(client, "treatment")
    params = {"teacher_name": OTHER_TEACHER, "teacher_id": OTHER_TEACHER}

    r = client.get("/api/templates/%d" % tpl_id, params=params)
    assert r.status_code == 403 and r.json()["detail"]["error"] == "template_forbidden"
    assert "schema_json" not in json.dumps(r.json(), ensure_ascii=False)
    assert "疏肝" not in json.dumps(r.json(), ensure_ascii=False)     # 不泄露行內容

    assert client.put("/api/templates/%d" % tpl_id, json={**_auth(OTHER_TEACHER), "name": "偷改"}).status_code == 403
    assert client.post("/api/templates/%d/publish" % tpl_id, json=_auth(OTHER_TEACHER)).status_code == 403
    assert client.post("/api/templates/%d/archive" % tpl_id, json=_auth(OTHER_TEACHER)).status_code == 403
    assert client.post("/api/templates/%d/activate" % tpl_id, json=_auth(OTHER_TEACHER)).status_code == 403
    assert client.post("/api/templates/%d/derive" % tpl_id, json=_auth(OTHER_TEACHER)).status_code == 403

    listing = client.get("/api/templates", params=params).json()
    assert listing["templates"] == []
    assert listing["counts"] == {"inquiry": 0, "record": 0, "treatment": 0, "prescription": 0}


def test_lineage_id_non_empty_400(client):
    """§10.1：`lineage_id` 傳非空值 → 400 lineage_not_supported（防前端提前誤用留白字段）。"""
    r = client.post("/api/templates", json=_auth(type="inquiry", lineage_id="lineage-x"))
    assert r.status_code == 400 and r.json()["detail"]["error"] == "lineage_not_supported"

    r = client.get("/api/templates", params=_auth(lineage_id="lineage-x"))
    assert r.status_code == 400 and r.json()["detail"]["error"] == "lineage_not_supported"

    tpl_id, _ = _published(client, "treatment")
    r = client.post("/api/templates/%d/derive" % tpl_id, json=_auth(lineage_id="lineage-x"))
    assert r.status_code == 400 and r.json()["detail"]["error"] == "lineage_not_supported"


# ============ D. 狀態機 ============

def test_publish_auto_archives_old_active_same_tx(client):
    """發佈 v2：舊 active 同事務歸檔、響應 archived_ids、HTTP 200（不是 409）、兩者 updated_at 一致。"""
    v1_id, first = _published(client, "treatment")
    assert first["archived_ids"] == [] and first["changed"] is True

    created = _create(client, "treatment", _publishable("treatment"))
    assert created.status_code == 201
    assert created.json()["template"]["version"] == 2      # 同 scope 已有 v1 → 取下一號
    v2_id = created.json()["template"]["id"]

    r = client.post("/api/templates/%d/publish" % v2_id, json=_auth())
    assert r.status_code == 200, r.text                    # 批復 2：不報 409
    payload = r.json()
    assert payload["archived_ids"] == [v1_id]
    assert payload["template"]["status"] == "active"
    assert payload["changed"] is True
    assert payload["event"] == "template_configured"

    v1 = _GET(client, v1_id).json()["template"]
    assert v1["status"] == "archived"
    assert v1["updated_at"] == payload["template"]["updated_at"]    # 同一事務、同一時間戳
    # 同一 scope 只有一條 active（部分唯一索引硬約束）
    actives = [
        t for t in client.get("/api/templates", params=_auth(type="treatment")).json()["templates"]
        if t["status"] == "active"
    ]
    assert [t["id"] for t in actives] == [v2_id]


def test_publish_idempotent(client):
    """重複 publish → 200 + changed=False + archived_ids=[]（§11.1 冪等）。"""
    tpl_id, _ = _published(client, "treatment")
    r = client.post("/api/templates/%d/publish" % tpl_id, json=_auth())
    assert r.status_code == 200
    assert r.json()["changed"] is False
    assert r.json()["archived_ids"] == []


def test_update_active_returns_409(client):
    """已發佈版本不可原地改 → 409 template_published_immutable，且內容與 updated_at 未變（批復 3）。"""
    tpl_id, _ = _published(client, "treatment")
    before = _GET(client, tpl_id).json()["template"]

    changed = database.default_template_schema("treatment")
    changed["content"] = "偷偷改掉已發佈版本"
    r = client.put("/api/templates/%d" % tpl_id, json={**_auth(), "schema_json": changed})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "template_published_immutable"

    after = _GET(client, tpl_id).json()["template"]
    assert after["schema_json"] == before["schema_json"]
    assert after["updated_at"] == before["updated_at"]


def test_update_archived_returns_409(client):
    """已歸檔版本同樣只讀 → 409（走「基於此版本修訂」派生）。"""
    v1_id, _ = _published(client, "treatment")
    v2 = _create(client, "treatment", _publishable("treatment"))
    client.post("/api/templates/%d/publish" % v2.json()["template"]["id"], json=_auth())

    r = client.put("/api/templates/%d" % v1_id, json={**_auth(), "name": "改個名"})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "template_published_immutable"


def test_archive_active_then_generation_falls_back(client):
    """歸檔 active → GET /api/templates/active 返回 null（生成側回落內置骨架）；重複歸檔冪等。"""
    tpl_id, _ = _published(client, "record")
    active = client.get("/api/templates/active", params=_auth(type="record")).json()
    assert active["template"]["id"] == tpl_id

    r = client.post("/api/templates/%d/archive" % tpl_id, json=_auth())
    assert r.status_code == 200 and r.json()["changed"] is True
    assert client.get("/api/templates/active", params=_auth(type="record")).json()["template"] is None

    again = client.post("/api/templates/%d/archive" % tpl_id, json=_auth())
    assert again.status_code == 200 and again.json()["changed"] is False


def test_activate_archived_requires_no_schema_check(client):
    """重新啟用不校驗 schema（§11.3）：即使 v1 內容已不可能通過發佈校驗也允許激活，並歸檔現有 active。"""
    v1_id, _ = _published(client, "record")
    v2 = _create(client, "record", _publishable("record"))
    v2_id = v2.json()["template"]["id"]
    client.post("/api/templates/%d/publish" % v2_id, json=_auth())

    # 人為把 v1 的 schema 改成「發佈級不可能通過」的內容（模擬歷史遺留 / 髒數據）
    conn = database.get_connection()
    conn.execute(
        "UPDATE templates SET schema_json = ? WHERE id = ?",
        (json.dumps({"version": 1, "sections": []}), v1_id),
    )
    conn.commit()
    conn.close()

    r = client.post("/api/templates/%d/activate" % v1_id, json=_auth())
    assert r.status_code == 200, r.text
    assert r.json()["changed"] is True
    assert r.json()["archived_ids"] == [v2_id]
    assert client.get("/api/templates/active", params=_auth(type="record")).json()["template"]["id"] == v1_id


# ============ E. 版本（派生）============

def test_derive_from_active_version_monotonic(client):
    """派生：`version = max(父+1, 鏈內 max+1)`、`parent_template_id = 父 id`、新行 status='draft'、內容繼承。"""
    v1_id, published = _published(client, "treatment")

    d1 = client.post("/api/templates/%d/derive" % v1_id, json=_auth())
    assert d1.status_code == 201, d1.text
    v2 = d1.json()["template"]
    assert v2["version"] == 2
    assert v2["parent_template_id"] == v1_id
    assert v2["status"] == "draft"
    assert v2["schema_json"] == published["template"]["schema_json"]    # 凍結快照逐字節繼承
    assert v2["name"] == published["template"]["name"]

    # 發布 v2 後再從 v1 派生 → 鏈內 max+1 = 3（不撞號）
    assert client.post("/api/templates/%d/publish" % v2["id"], json=_auth()).status_code == 200
    d2 = client.post("/api/templates/%d/derive" % v1_id, json=_auth())
    assert d2.status_code == 201
    assert d2.json()["template"]["version"] == 3
    assert d2.json()["template"]["parent_template_id"] == v1_id


def test_derive_reuses_existing_draft(client):
    """同鏈已有草稿 → 200 + reused_draft=True，返回同一行（不產生第二份草稿，§4.3 第 4 條）。"""
    v1_id, _ = _published(client, "treatment")
    first = client.post("/api/templates/%d/derive" % v1_id, json=_auth())
    assert first.status_code == 201
    first_id = first.json()["template"]["id"]

    again = client.post("/api/templates/%d/derive" % v1_id, json=_auth())
    assert again.status_code == 200, again.text
    assert again.json()["reused_draft"] is True
    assert again.json()["template"]["id"] == first_id


def test_derive_parent_scope_mismatch_400(client):
    """父版本與來源不同類型（禁跨老師 / 跨師門 / 跨類型掛鏈）→ 400 template_parent_scope_mismatch。"""
    treatment_id, _ = _published(client, "treatment")
    inquiry_id = _create(client, "inquiry").json()["template"]["id"]

    r = client.post(
        "/api/templates/%d/derive" % treatment_id,
        json={**_auth(), "parent_template_id": inquiry_id},
    )
    assert r.status_code == 400 and r.json()["detail"]["error"] == "template_parent_scope_mismatch"


def test_derive_parent_not_found_and_self_reference(client):
    """來源不存在 → 400 template_parent_not_found；父指向自身（髒數據）→ 400 template_parent_self_reference。"""
    r = client.post("/api/templates/999999/derive", json=_auth())
    assert r.status_code == 400 and r.json()["detail"]["error"] == "template_parent_not_found"

    v1_id, _ = _published(client, "treatment")
    conn = database.get_connection()
    conn.execute("UPDATE templates SET parent_template_id = id WHERE id = ?", (v1_id,))
    conn.commit()
    conn.close()

    r = client.post("/api/templates/%d/derive" % v1_id, json=_auth())
    assert r.status_code == 400 and r.json()["detail"]["error"] == "template_parent_self_reference"


def test_version_chain_no_duplicate_version(client):
    """版本序列嚴格遞增且不重複（含「歸檔草稿占用了下一號」的場景）。"""
    v1_id, _ = _published(client, "treatment")
    v2_id = client.post("/api/templates/%d/derive" % v1_id, json=_auth()).json()["template"]["id"]
    # 把 v2 草稿歸檔（版本號被占用，但沒有草稿了）→ 再派生必須跳到 v3
    assert client.post("/api/templates/%d/archive" % v2_id, json=_auth()).json()["changed"] is True

    derived = client.post("/api/templates/%d/derive" % v1_id, json=_auth())
    assert derived.status_code == 201
    assert derived.json()["template"]["version"] == 3

    versions = [
        t["version"]
        for t in client.get("/api/templates", params=_auth(type="treatment")).json()["templates"]
    ]
    assert versions == [3, 2, 1]
    assert len(set(versions)) == len(versions)


# ============ F. 兼容與零回溯 ============

def test_legacy_plan_template_api_unchanged(client):
    """§12.4 / §5.2 第 2 條：舊 `GET/POST /api/plan_template` 請求 / 響應結構 100% 不變。"""
    r = client.get("/api/plan_template", params={"teacher_name": TEACHER})
    assert r.status_code == 200
    assert r.json() == {"content": ""}

    r = client.post("/api/plan_template", json={"teacher_name": TEACHER, "content": "疏肝理氣，健脾和胃。"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    r = client.get("/api/plan_template", params={"teacher_name": TEACHER})
    assert r.status_code == 200
    assert set(r.json().keys()) == {"content"}
    assert r.json()["content"] == "疏肝理氣，健脾和胃。"

    conn = database.get_connection()
    row = conn.execute(
        "SELECT teacher_name, content FROM plan_templates WHERE teacher_name = ?", (TEACHER,)
    ).fetchone()
    conn.close()
    assert row["teacher_name"] == TEACHER
    assert row["content"] == "疏肝理氣，健脾和胃。"


def test_template_archive_does_not_touch_history(client):
    """§4.4 / §14.1 F：發布 v2、v1 轉歸檔後，引用 v1 的草案與已簽病歷逐字節不變。"""
    v1_id, v1_payload = _published(client, "treatment")
    v1_content = v1_payload["template"]["schema_json"]["content"]

    draft_id = database.insert_draft(0, "张三", TEACHER, "AI 原草案：依 v1 生成")
    # 只傳 final_plan（不傳 final_content）→ 落庫的 `final_plan` 列就是 v1 的內容，
    # 這樣能直接斷言「歷史病歷凍結在 v1 內容上」。
    database.sign_draft(draft_id, v1_content)
    before = database.get_patient_records("张三", TEACHER)[0]
    assert before["final_plan"] == v1_content

    created = _create(client, "treatment", _publishable("treatment"))
    r = client.post("/api/templates/%d/publish" % created.json()["template"]["id"], json=_auth())
    assert r.json()["archived_ids"] == [v1_id]

    after = database.get_patient_records("张三", TEACHER)[0]
    assert after["final_plan"] == before["final_plan"] == v1_content
    assert after["ai_draft"] == before["ai_draft"] == "AI 原草案：依 v1 生成"
    assert after["visit_at"] == before["visit_at"]        # 就診時間基準也不動

    # v1 行仍在、仍是凍結快照（版本號與內容都不動）
    v1_now = _GET(client, v1_id).json()["template"]
    assert v1_now["status"] == "archived"
    assert v1_now["version"] == 1
    assert v1_now["schema_json"]["content"] == v1_content


def test_templates_flag_off_returns_404(client, monkeypatch):
    """§5.2 第 5 條：flag off → 全部 `/api/templates*` 404 templates_disabled（前端據此不渲染入口）。"""
    monkeypatch.setenv("TEMPLATE_API_ENABLED", "off")

    get_targets = ["/api/templates", "/api/templates/1", "/api/templates/active"]
    for url in get_targets:
        r = client.get(url, params=_auth(type="inquiry"))
        assert r.status_code == 404, (url, r.text)
        assert r.json()["detail"]["error"] == "templates_disabled"

    write_targets = [
        ("post", "/api/templates"),
        ("put", "/api/templates/1"),
        ("post", "/api/templates/1/publish"),
        ("post", "/api/templates/1/archive"),
        ("post", "/api/templates/1/activate"),
        ("post", "/api/templates/1/derive"),
    ]
    for method, url in write_targets:
        r = getattr(client, method)(url, json=_auth(type="inquiry"))
        assert r.status_code == 404, (url, r.text)
        assert r.json()["detail"]["error"] == "templates_disabled"


# ============ I. 校驗層（§9：只攔截、絕不清洗）============

def test_validation_rejects_invalid_type_and_non_object_schema(client):
    """`type` 白名單外的值直接 400 invalid_type；`schema_json` 不是物件 → 400 schema_invalid。"""
    r = client.post("/api/templates", json=_auth(type="diagnosis"))
    assert r.status_code == 400 and r.json()["detail"]["error"] == "invalid_type"

    r = _create(client, "inquiry", schema=[{"key": "cold_heat"}])
    assert r.status_code == 400 and r.json()["detail"]["error"] == "schema_invalid"
    assert r.json()["detail"]["errors"][0]["path"] == ""

    # 非法 type 不落任何行
    assert client.get("/api/templates", params=_auth()).json()["templates"] == []


def test_validation_rejects_illegal_role_without_silent_cleaning(client):
    """§9.4：`role` 不在白名單 → 400（不走 clean_prescription_role 的清洗），且不落任何行。"""
    schema = {
        "version": 1,
        "herbs": [
            {"herb_name": "甘草", "default_amount": 6, "role": "帥", "cooking_method": "常规"},
        ],
        "formulas": [],
        "meta": {},
    }
    r = _create(client, "prescription", schema)
    assert r.status_code == 400 and r.json()["detail"]["error"] == "schema_invalid"
    paths = [e["path"] for e in r.json()["detail"]["errors"]]
    assert "herbs[0].role" in paths
    # 絕不悄悄清洗：庫裏不許出現被改成 '' 的殘行
    assert client.get("/api/templates", params=_auth()).json()["counts"]["prescription"] == 0

    # 空字串 role（未標註）與白名單值都是合法的
    schema["herbs"][0]["role"] = ""
    assert _create(client, "prescription", schema).status_code == 201


def test_validation_rejects_illegal_cooking_method_in_formula(client):
    """§9.4：`formulas[].composition[].cooking_method` 同樣走白名單；錯誤 path 精確到項。"""
    schema = {
        "version": 1,
        "herbs": [],
        "formulas": [
            {
                "name": "四君子湯",
                "composition": [
                    {"herb_name": "人參", "amount": 9, "role": "君", "cooking_method": "另煎"},
                    {"herb_name": "白朮", "amount": 9, "role": "臣", "cooking_method": "先煮"},
                ],
            },
        ],
        "defaults": {"cooking_method": "乱煎", "remote": False},
        "meta": {},
    }
    r = _create(client, "prescription", schema)
    assert r.status_code == 400
    paths = [e["path"] for e in r.json()["detail"]["errors"]]
    assert "formulas[0].composition[1].cooking_method" in paths
    assert "defaults.cooking_method" in paths
    assert "formulas[0].composition[0].cooking_method" not in paths   # 白名單值不報錯


def test_validation_rejects_invalid_key_and_duplicate_order(client):
    """§9.1：`key` 正則 / `order` 唯一 / `label` 長度上限，錯誤 path 用 JS 風格。"""
    schema = database.default_template_schema("inquiry")
    schema["fields"][0]["key"] = "ColdHeat"            # 不符 ^[a-z][a-z0-9_]{0,31}$
    schema["fields"][1]["order"] = 1                   # 與 fields[0].order 重複
    schema["fields"][2]["label"] = "頭" * 17           # 超過 16 字

    r = _create(client, "inquiry", schema)
    assert r.status_code == 400 and r.json()["detail"]["error"] == "schema_invalid"
    paths = [e["path"] for e in r.json()["detail"]["errors"]]
    assert "fields[0].key" in paths
    assert "fields[1].order" in paths
    assert "fields[2].label" in paths


def test_schema_too_large_400(client):
    """§9.0：序列化後 > 64 KB → 400 schema_too_large（未知鍵原樣保留，所以走 meta 塞大文本）。"""
    schema = database.default_template_schema("treatment")
    schema["content"] = "方" * 100
    schema["meta"] = {"big_%d" % i: "疏" * 2000 for i in range(40)}   # 每串合法（≤2000 字），總量超 64 KB
    r = _create(client, "treatment", schema)
    assert r.status_code == 400 and r.json()["detail"]["error"] == "schema_too_large"


def test_publish_requires_complete_schema(client):
    """§9.0 校驗時機：草稿允許半成品（201），發佈必須完整（400 schema_invalid + 具體 errors）。"""
    # 施治：content 為空 → 發佈被拒（草稿可以存）
    draft = _create(client, "treatment")
    assert draft.status_code == 201
    draft_id = draft.json()["template"]["id"]
    r = client.post("/api/templates/%d/publish" % draft_id, json=_auth())
    assert r.status_code == 400 and r.json()["detail"]["error"] == "schema_invalid"
    assert any(e["path"] == "content" for e in r.json()["detail"]["errors"])

    # 問診：只留 2 項 → 草稿可存，發佈被拒
    partial = database.default_template_schema("inquiry")
    partial["fields"] = partial["fields"][:2]
    inquiry = _create(client, "inquiry", partial)
    assert inquiry.status_code == 201
    inquiry_id = inquiry.json()["template"]["id"]
    r = client.post("/api/templates/%d/publish" % inquiry_id, json=_auth())
    assert r.status_code == 400
    assert any("3 項" in e["msg"] for e in r.json()["detail"]["errors"])

    # 補到 3 項但仍無「必問」→ 仍被拒
    partial["fields"] = database.default_template_schema("inquiry")["fields"][:3]
    fixed = client.put("/api/templates/%d" % inquiry_id, json={**_auth(), "schema_json": partial})
    assert fixed.status_code == 200
    r = client.post("/api/templates/%d/publish" % inquiry_id, json=_auth())
    assert r.status_code == 400
    assert any("必問" in e["msg"] for e in r.json()["detail"]["errors"])

    # 病歷：全部段落都不是「留待老師」→ 發佈被拒（AI 永不辨證的守護）
    record = database.default_template_schema("record")
    for section in record["sections"]:
        section["writable_by"] = "ai"
    record_draft = _create(client, "record", record)
    assert record_draft.status_code == 201
    r = client.post("/api/templates/%d/publish" % record_draft.json()["template"]["id"], json=_auth())
    assert r.status_code == 400
    assert any("留待老師" in e["msg"] for e in r.json()["detail"]["errors"])


def test_prescription_missing_inventory_warns(client):
    """§9.4：藥材未入庫 → 200 通過 + warnings（黃字提醒），入庫後 warnings 消失。"""
    schema = {
        "version": 1,
        "herbs": [{"herb_name": "甘草", "default_amount": 6, "role": "君", "cooking_method": "常规"}],
        "formulas": [
            {"name": "四君子湯", "composition": [{"herb_name": "白朮", "amount": 9, "role": "臣", "cooking_method": "常规"}]},
        ],
        "defaults": {"cooking_method": "常规", "remote": False},
        "meta": {},
    }
    r = _create(client, "prescription", schema)
    assert r.status_code == 201, r.text
    warnings = r.json()["warnings"]
    assert sorted(w["herb_name"] for w in warnings) == ["甘草", "白朮"]   # sorted = 碼位序
    assert all(w["code"] == "herb_not_in_inventory" for w in warnings)
    draft_id = r.json()["template"]["id"]

    for herb_name in ("甘草", "白朮"):
        client.post("/api/herbs", json={
            "teacher_name": TEACHER, "herb_name": herb_name,
            "stock_amount": 100, "unit": "克", "warn_threshold": 50,
        })
    updated = client.put("/api/templates/%d" % draft_id, json={**_auth(), "schema_json": schema})
    assert updated.status_code == 200
    assert updated.json()["warnings"] == []


def test_unknown_keys_preserved_verbatim(client):
    """§9.0 前向兼容：未知鍵「忽略且原樣保留」，不做補默認 / 刪鍵 / 清洗。"""
    schema = database.default_template_schema("treatment")
    schema["content"] = "疏肝理氣。"
    schema["epic3_preview"] = {"hash": "abc", "chain": [1, 2]}
    schema["meta"] = {"note": "老師備註", "updated_hint": "未保存提示"}

    r = _create(client, "treatment", schema)
    assert r.status_code == 201, r.text
    stored = r.json()["template"]["schema_json"]
    assert stored["epic3_preview"] == {"hash": "abc", "chain": [1, 2]}
    assert stored["meta"] == {"note": "老師備註", "updated_hint": "未保存提示"}
    assert stored == schema


def test_template_store_unavailable_503(client):
    """§7：遷移未跑（表缺失）→ 503 template_store_unavailable（舊鏈路不受影響）。"""
    conn = database.get_connection()
    conn.execute("ALTER TABLE templates RENAME TO templates_hidden")
    conn.commit()
    conn.close()

    r = client.get("/api/templates", params=_auth())
    assert r.status_code == 503 and r.json()["detail"]["error"] == "template_store_unavailable"
    # 舊鏈路照常
    assert client.get("/api/plan_template", params={"teacher_name": TEACHER}).status_code == 200
