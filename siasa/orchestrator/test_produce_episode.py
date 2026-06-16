"""produce_episode 오케스트레이션 시퀀싱 테스트 — runner stub(GPU 없이).

생성·seo는 주입 runner로 stub. 6분 GPU LoRA는 dev 루프 금지(E2E 1회 별도 수용검사).
"""
import json

import pytest

import produce_episode as pe
from produce_episode import produce_episode, _default_workspace, _parse_args


def _gen_stub(script="대본 본문.\n복잡한 세상, 제대로 읽어갑시다.", review="검수: 수치 3개"):
    """call_writer 대역 — 대본.txt + .review.txt를 워크스페이스에 쓴다."""
    def runner(topic, out_path):
        from pathlib import Path
        p = Path(out_path)
        p.write_text(script, encoding="utf-8")
        Path(str(p).replace(".txt", ".review.txt")).write_text(review, encoding="utf-8")
    return runner


def _seo_stub(text="제목: X\n설명: Y\n태그: a,b\n썸네일: Z"):
    calls = []
    def runner(script):
        calls.append(script)
        return text
    runner.calls = calls
    return runner


def test_runs_steps_and_writes_bundle(tmp_path):
    ws = tmp_path / "ep"
    r = produce_episode("환율 급등", str(ws), gen_runner=_gen_stub(), seo_runner=_seo_stub())
    assert (ws / "대본.txt").exists()
    assert (ws / "bundle.json").exists()
    bundle = json.loads((ws / "bundle.json").read_text(encoding="utf-8"))
    assert bundle["topic"] == "환율 급등"
    assert r["script_chars"] > 0
    assert r["verdict"] == "REVIEW"          # 자동 PASS/FAIL 아님 — 디렉터 판단


def test_seo_receives_generated_script(tmp_path):
    seo = _seo_stub()
    produce_episode("주제", str(tmp_path / "ep"), gen_runner=_gen_stub(script="생성된 대본"), seo_runner=seo)
    assert seo.calls and "생성된 대본" in seo.calls[0]   # 생성 후 그 대본으로 seo


def test_review_surfaced_in_report(tmp_path):
    r = produce_episode("주제", str(tmp_path / "ep"),
                        gen_runner=_gen_stub(review="검수: 신뢰도저하 1건"), seo_runner=_seo_stub())
    assert "신뢰도저하" in r["review"]


def test_missing_script_raises(tmp_path):
    def bad_gen(topic, out_path):
        pass                                  # 아무것도 안 씀 = 생성 실패
    with pytest.raises(RuntimeError):
        produce_episode("주제", str(tmp_path / "ep"), gen_runner=bad_gen, seo_runner=_seo_stub())


def test_workspace_created(tmp_path):
    ws = tmp_path / "deep" / "ep"
    produce_episode("주제", str(ws), gen_runner=_gen_stub(), seo_runner=_seo_stub())
    assert ws.is_dir()


def test_missing_review_graceful(tmp_path):
    # .review.txt 없어도(드문 경우) 죽지 않고 빈 review로 진행
    def gen_no_review(topic, out_path):
        from pathlib import Path
        Path(out_path).write_text("대본만", encoding="utf-8")
    r = produce_episode("주제", str(tmp_path / "ep"), gen_runner=gen_no_review, seo_runner=_seo_stub())
    assert r["review"] == ""


def test_default_workspace_slugifies(monkeypatch):
    monkeypatch.delenv("SIASA_OUT_DIR", raising=False)
    ws = _default_workspace("환율 급등!")
    assert ws.endswith("환율_급등_")           # 비영숫자 → _ 슬러그


def test_default_workspace_uses_env(monkeypatch):
    monkeypatch.setenv("SIASA_OUT_DIR", "/x/out")
    assert _default_workspace("주제").startswith("/x/out/")


def test_parse_args():
    ns = _parse_args(["--topic", "t", "--workspace", "/w"])
    assert ns.topic == "t" and ns.workspace == "/w"


def test_gen_runner_passes_topic_as_arg_not_shell(monkeypatch):
    # injection-safe: topic은 positional arg로 전달(셸 보간 아님)
    captured = {}
    monkeypatch.setattr(pe.subprocess, "run", lambda cmd, **kw: captured.update(cmd=cmd, kw=kw))
    pe._gen_via_call_writer('주제"; rm -rf /', "/tmp/o.txt")
    cmd = captured["cmd"]
    assert cmd[0] == "bash" and cmd[1] == "-c"
    assert '주제"; rm -rf /' in cmd            # 악성 topic이 arg로(스크립트 문자열엔 미보간)
    assert '주제"; rm -rf /' not in cmd[2]      # 스크립트 본문엔 없음
    assert captured["kw"]["check"] is True


def test_seo_runner_invokes_seo_director(monkeypatch):
    class _R:
        stdout = "제목: X"
    monkeypatch.setattr(pe.subprocess, "run", lambda cmd, **kw: _R())
    captured = {}
    monkeypatch.setattr(pe.subprocess, "run",
                        lambda cmd, **kw: captured.update(cmd=cmd) or _R())
    out = pe._seo_via_chat("대본내용")
    assert "-p" in captured["cmd"] and "seo-director" in captured["cmd"]
    assert out == "제목: X"
