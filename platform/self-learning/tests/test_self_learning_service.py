from __future__ import annotations


def test_health(test_client):
    r = test_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "self-learning"
    assert body["version"] == "1.0.0"


def test_record_and_list_and_retrieve(test_client):
    payload = {
        "task_id": "task-1",
        "task_description": "open browser and search docs",
        "action_sequence": [{"step": "open_browser"}, {"step": "search"}],
        "outcome": "success",
        "duration_ms": 1800,
        "error_message": None,
        "model_used": "llama3",
        "user_rating": 5,
    }

    rr = test_client.post("/learn/record", json=payload)
    assert rr.status_code == 200
    rec = rr.json()
    assert "score" in rec

    ls = test_client.get("/learn/skills")
    assert ls.status_code == 200
    skills = ls.json()
    assert isinstance(skills, list)

    ret = test_client.post("/learn/retrieve", json={"task_description": "search browser docs", "top_k": 3})
    assert ret.status_code == 200
    matches = ret.json()
    assert isinstance(matches, list)


def test_stats_and_training_status(test_client):
    st = test_client.get("/learn/stats")
    assert st.status_code == 200
    body = st.json()
    assert "total_skills" in body
    assert "total_tasks_recorded" in body
    assert "model_version" in body

    sched = test_client.post("/learn/train/schedule")
    assert sched.status_code == 200
    job = sched.json()
    assert "job_id" in job
    assert "status" in job

    status = test_client.get(f"/learn/train/status/{job['job_id']}")
    assert status.status_code == 200
    assert status.json()["job_id"] == job["job_id"]


def test_delete_skill_roundtrip(test_client):
    payload = {
        "task_id": "task-del",
        "task_description": "collect logs",
        "action_sequence": [{"step": "collect"}],
        "outcome": "success",
        "duration_ms": 1000,
        "error_message": None,
        "model_used": "llama3",
        "user_rating": 5,
    }

    rec = test_client.post("/learn/record", json=payload).json()
    skill_id = rec.get("skill_id")
    if skill_id:
        resp = test_client.delete(f"/learn/skills/{skill_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
