from io import BytesIO

from fastapi.testclient import TestClient


def _api_data(response, *, status_code: int = 200):
    assert response.status_code == status_code, response.text
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


def _login(client: TestClient, username: str, password: str = "123456") -> str:
    data = _api_data(
        client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
    )
    return data["access_token"]


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_knowledge_base(client: TestClient, token: str, name: str = "客服知识库") -> dict:
    return _api_data(
        client.post(
            "/api/v1/knowledge-bases",
            json={"name": name, "description": "用于接口测试的知识库"},
            headers=_auth_header(token),
        )
    )


def _upload_document(
    client: TestClient,
    token: str,
    *,
    knowledge_base_id: int,
    file_name: str,
    content: bytes,
    content_type: str = "text/plain",
) -> dict:
    return _api_data(
        client.post(
            "/api/v1/documents/upload",
            data={"knowledge_base_id": str(knowledge_base_id)},
            files={"file": (file_name, content, content_type)},
            headers=_auth_header(token),
        )
    )


def test_auth_profile_and_admin_permissions(client: TestClient) -> None:
    admin_token = _login(client, "admin")
    user_token = _login(client, "user")

    admin_profile = _api_data(
        client.get("/api/v1/auth/profile", headers=_auth_header(admin_token))
    )
    assert admin_profile["username"] == "admin"
    assert admin_profile["role"] == "admin"

    forbidden_response = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "普通用户不能新建", "description": ""},
        headers=_auth_header(user_token),
    )
    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["message"] == "只有管理员可以执行该操作"

    knowledge_base = _create_knowledge_base(client, admin_token, name="权限测试知识库")
    knowledge_bases = _api_data(
        client.get("/api/v1/knowledge-bases", headers=_auth_header(user_token))
    )
    assert [item["id"] for item in knowledge_bases] == [knowledge_base["id"]]


def test_document_upload_parse_search_and_chat_flow(client: TestClient) -> None:
    admin_token = _login(client, "admin")
    user_token = _login(client, "user")
    knowledge_base = _create_knowledge_base(client, admin_token)

    document_text = (
        "七天退款政策\n\n"
        "客户在签收后七天内可以申请退款，客服需要核对订单号和付款记录。"
        "确认符合条件后，应在两个工作日内处理退款。"
    )
    document = _upload_document(
        client,
        admin_token,
        knowledge_base_id=knowledge_base["id"],
        file_name="refund-policy.txt",
        content=document_text.encode("utf-8"),
    )
    assert document["status"] == "uploaded"
    assert document["file_type"] == "TXT"
    assert document["has_file"] is True

    parsed_document = _api_data(
        client.post(
            f"/api/v1/documents/{document['id']}/parse",
            headers=_auth_header(admin_token),
        )
    )
    assert parsed_document["status"] == "completed"
    assert parsed_document["parse_progress"] == 100
    assert parsed_document["parse_chunk_count"] >= 1

    chunks = _api_data(
        client.get(
            f"/api/v1/documents/{document['id']}/chunks",
            headers=_auth_header(user_token),
        )
    )
    assert chunks["total"] >= 1
    assert "七天退款政策" in chunks["items"][0]["content"]

    search_result = _api_data(
        client.post(
            f"/api/v1/knowledge-bases/{knowledge_base['id']}/search",
            json={"query": "七天退款怎么处理", "top_k": 3},
            headers=_auth_header(user_token),
        )
    )
    assert search_result["total"] >= 1
    assert search_result["items"][0]["document_id"] == document["id"]

    chat_result = _api_data(
        client.post(
            "/api/v1/chat/messages",
            json={
                "knowledge_base_id": knowledge_base["id"],
                "question": "七天退款怎么处理？",
                "top_k": 3,
            },
            headers=_auth_header(user_token),
        )
    )
    assert chat_result["conversation_id"] > 0
    assert chat_result["user_message"]["role"] == "user"
    assert chat_result["assistant_message"]["role"] == "assistant"
    assert chat_result["citations"][0]["document_id"] == document["id"]
    assert "refund-policy.txt" in chat_result["assistant_message"]["content"]

    conversations = _api_data(
        client.get("/api/v1/chat/conversations", headers=_auth_header(user_token))
    )
    assert conversations["total"] == 1
    assert conversations["items"][0]["message_count"] == 2

    messages = _api_data(
        client.get(
            f"/api/v1/chat/conversations/{chat_result['conversation_id']}/messages",
            headers=_auth_header(user_token),
        )
    )
    assert messages["total"] == 2
    assert messages["items"][1]["citations"][0]["document_id"] == document["id"]


def test_document_list_filters_sorting_delete_and_validation(client: TestClient) -> None:
    admin_token = _login(client, "admin")
    knowledge_base = _create_knowledge_base(client, admin_token, name="文档列表知识库")

    txt_document = _upload_document(
        client,
        admin_token,
        knowledge_base_id=knowledge_base["id"],
        file_name="alpha-policy.txt",
        content=b"alpha policy content",
    )
    md_document = _upload_document(
        client,
        admin_token,
        knowledge_base_id=knowledge_base["id"],
        file_name="beta-guide.md",
        content=b"# beta guide\n\nrefund guide content",
        content_type="text/markdown",
    )

    unsupported_response = client.post(
        "/api/v1/documents/upload",
        data={"knowledge_base_id": str(knowledge_base["id"])},
        files={"file": ("script.exe", b"not allowed", "application/octet-stream")},
        headers=_auth_header(admin_token),
    )
    assert unsupported_response.status_code == 400
    assert unsupported_response.json()["message"] == "暂仅支持 PDF、DOCX、TXT、MD 格式文档"

    empty_response = client.post(
        "/api/v1/documents/upload",
        data={"knowledge_base_id": str(knowledge_base["id"])},
        files={"file": ("empty.txt", b"", "text/plain")},
        headers=_auth_header(admin_token),
    )
    assert empty_response.status_code == 400
    assert empty_response.json()["message"] == "不能上传空文档"

    filtered = _api_data(
        client.get(
            "/api/v1/documents",
            params={
                "knowledge_base_id": knowledge_base["id"],
                "file_type": "TXT",
                "sort_by": "file_name",
                "sort_order": "asc",
            },
            headers=_auth_header(admin_token),
        )
    )
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == txt_document["id"]

    all_documents = _api_data(
        client.get(
            "/api/v1/documents",
            params={"sort_by": "file_name", "sort_order": "asc"},
            headers=_auth_header(admin_token),
        )
    )
    assert [item["file_name"] for item in all_documents["items"]] == [
        "alpha-policy.txt",
        "beta-guide.md",
    ]

    _api_data(
        client.delete(
            f"/api/v1/documents/{md_document['id']}",
            headers=_auth_header(admin_token),
        )
    )
    refreshed_knowledge_base = _api_data(
        client.get(
            f"/api/v1/knowledge-bases/{knowledge_base['id']}",
            headers=_auth_header(admin_token),
        )
    )
    assert refreshed_knowledge_base["document_count"] == 1


def _make_pdf_bytes(text: str) -> bytes:
    import fitz

    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), text)
    buffer = BytesIO(pdf.write())
    pdf.close()
    return buffer.getvalue()


def test_pdf_parse_records_page_number(client: TestClient) -> None:
    admin_token = _login(client, "admin")
    knowledge_base = _create_knowledge_base(client, admin_token, name="PDF 知识库")
    pdf_document = _upload_document(
        client,
        admin_token,
        knowledge_base_id=knowledge_base["id"],
        file_name="refund-policy.pdf",
        content=_make_pdf_bytes("PDF refund policy allows refund within seven days."),
        content_type="application/pdf",
    )

    parsed_document = _api_data(
        client.post(
            f"/api/v1/documents/{pdf_document['id']}/parse",
            headers=_auth_header(admin_token),
        )
    )
    assert parsed_document["status"] == "completed"

    chunks = _api_data(
        client.get(
            f"/api/v1/documents/{pdf_document['id']}/chunks",
            headers=_auth_header(admin_token),
        )
    )
    assert chunks["total"] == 1
    assert chunks["items"][0]["page_number"] == 1
    assert "refund policy" in chunks["items"][0]["content"]
