"""영상팀 핸드오프 테스트 — 순수 복사 + refuse-if-exists + .work_dir 권위."""
import unicodedata
from pathlib import Path

import pytest

from handoff_to_video import resolve_work_dir, handoff, _parse_args


def _make_script(tmp_path, text="대본 본문.\n복잡한 세상, 제대로 읽어갑시다."):
    p = tmp_path / "src" / "대본.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_resolve_work_dir_reads_file(tmp_path):
    repo = tmp_path / "gen"
    repo.mkdir()
    (repo / ".work_dir").write_text("/docs/경제베테랑-youtube\n", encoding="utf-8")
    assert resolve_work_dir(str(repo)) == "/docs/경제베테랑-youtube"


def test_resolve_work_dir_missing_raises(tmp_path):
    with pytest.raises(ValueError):
        resolve_work_dir(str(tmp_path / "gen"))   # .work_dir 없음


def test_handoff_copies_to_date_dir(tmp_path):
    src = _make_script(tmp_path)
    wd = str(tmp_path / "work")
    dest = handoff(src, "2026-06-20", wd)
    assert dest == str(Path(wd) / "2026-06-20" / "대본.txt")
    assert Path(dest).read_text(encoding="utf-8").endswith("제대로 읽어갑시다.")


def test_handoff_dest_filename_is_nfc(tmp_path):
    dest = handoff(_make_script(tmp_path), "2026-06-20", str(tmp_path / "work"))
    name = Path(dest).name
    assert name == unicodedata.normalize("NFC", name)


def test_handoff_refuse_if_exists(tmp_path):
    src = _make_script(tmp_path)
    wd = str(tmp_path / "work")
    handoff(src, "2026-06-20", wd)
    with pytest.raises(FileExistsError):       # 실제 코퍼스 클로버 방지
        handoff(src, "2026-06-20", wd)


def test_handoff_force_overwrites(tmp_path):
    src = _make_script(tmp_path, text="첫 버전.\n복잡한 세상, 제대로 읽어갑시다.")
    wd = str(tmp_path / "work")
    handoff(src, "2026-06-20", wd)
    src2 = _make_script(tmp_path / "v2", text="둘째 버전.\n복잡한 세상, 제대로 읽어갑시다.")
    dest = handoff(src2, "2026-06-20", wd, force=True)
    assert "둘째 버전" in Path(dest).read_text(encoding="utf-8")


def test_handoff_missing_script_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        handoff(str(tmp_path / "none.txt"), "2026-06-20", str(tmp_path / "work"))


def test_parse_args():
    ns = _parse_args(["--script", "/s/대본.txt", "--date", "2026-06-20", "--force"])
    assert ns.script == "/s/대본.txt" and ns.date == "2026-06-20" and ns.force is True
    assert ns.work_dir is None
