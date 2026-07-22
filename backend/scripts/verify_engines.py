"""Сквозная проверка движков на реально загруженных модулях (BOUND, REAL) + интейк."""
from sqlalchemy import select, delete
from app.database import SessionLocal
from app import models as m
from app.services import intake, progression, scoring, postmodule, identity


def best_answers(db, module_code, week_n, *, worst=False):
    """{q_index: индекс варианта с макс(мин) весом}. Для core — weight, для flag — flag_weight."""
    week = db.execute(select(m.ModuleWeek).where(m.ModuleWeek.module_code == module_code,
                                                 m.ModuleWeek.n == week_n)).scalar_one()
    qs = db.execute(select(m.SelfcheckQuestion).where(m.SelfcheckQuestion.week_id == week.id)
                    .order_by(m.SelfcheckQuestion.q_index)).scalars().all()
    out = {}
    for q in qs:
        key = "weight" if q.kind == "core" else "flag_weight"
        weights = [int(o.get(key, 0)) for o in q.options]
        out[q.q_index] = weights.index(min(weights) if worst else max(weights))
    return out


def cleanup(db, uid):
    ens = db.execute(select(m.Enrollment).where(m.Enrollment.user_id == uid)).scalars().all()
    for e in ens:
        db.execute(delete(m.SelfcheckResult).where(m.SelfcheckResult.enrollment_id == e.id))
        db.execute(delete(m.FlagAccumulator).where(m.FlagAccumulator.enrollment_id == e.id))
        db.execute(delete(m.DailyEntry).where(m.DailyEntry.enrollment_id == e.id))
        db.execute(delete(m.PostmoduleResult).where(m.PostmoduleResult.enrollment_id == e.id))
    db.execute(delete(m.Enrollment).where(m.Enrollment.user_id == uid))
    db.execute(delete(m.IntakeResult).where(m.IntakeResult.user_id == uid))
    db.commit()


def main():
    db = SessionLocal()
    # реальный пользователь через identity-резолвер
    tester = identity.resolve_or_create(db, "telegram", "verify-tester")
    UID = tester.id
    cleanup(db, UID)
    ok = []
    ok.append(f"identity: resolve_or_create(telegram, verify-tester) → user_id={UID}")

    # ── 1. ИНТЕЙК: перекос в сторону BOUND (вопросы 22–24 = 4, остальное 0) ──
    ans = {n: 0 for n in range(1, 31)}
    ans.update({22: 4, 23: 4, 24: 4})
    r = intake.score_intake(db, ans, user_id=UID)
    assert r["leading"] == "BOUND", r["leading"]
    assert r["leading_module"] == "BOUND"
    assert r["_scores"]["BOUND"] == 12
    assert not r["is_soft"]
    ok.append(f"intake: ведущий BOUND(12)→модуль BOUND, доп={r['focus1']}/{r['focus2']}, текст {len(r['result_text'])} симв.")

    # soft-случай: все ответы 1 (ведущий < 7)
    r2 = intake.score_intake(db, {n: 1 for n in range(1, 31)}, user_id=UID)
    assert r2["is_soft"], "ожидался soft при низких баллах"
    # tie-break бережности: при равных все по 3 → BURN первым
    r3 = intake.score_intake(db, {n: 3 for n in range(1, 31)}, user_id=UID)
    assert r3["leading"] == "BURN", r3["leading"]
    ok.append(f"intake: soft при низких баллах ✓; tie-break при равных → {r3['leading']} (BURN) ✓")

    # ── 2. DAY-PROGRESSION: полный проход BOUND (6 недель) с GREEN ──
    e = progression.enroll(db, UID, "BOUND")
    today = progression.get_today(db, e)
    assert today["status"] == "active" and today["week"] == 1 and today["day"] == 1
    assert len(today["morning_markers"]) == 5 and len(today["evening_markers"]) == 5
    assert today["audio"]["code"] == "AUDIO_BOUND_W1_A1"

    week_zones = []
    for wk in range(1, 7):
        for d in range(1, 8):
            st = progression.complete_day(db, e, task_status="DONE",
                                          quiz_answer="да", reflection=["a", "b", "c"])
        assert st["status"] == "selfcheck_due", (wk, st)
        res = progression.submit_selfcheck(db, e, best_answers(db, "BOUND", wk))
        week_zones.append(res["zone"])
        assert res["blocks_progression"] is False
    e_final = db.get(m.Enrollment, e.id)
    assert e_final.status == "completed", e_final.status
    assert week_zones == ["GREEN"] * 6, week_zones
    ok.append(f"progression: BOUND пройден 6 недель, зоны {week_zones}, статус={e_final.status}")

    # ── 3. SCORING: RED-зона на худших ответах (свежий проход BOUND W1) ──
    cleanup(db, UID)
    e = progression.enroll(db, UID, "BOUND")
    for d in range(1, 8):
        progression.complete_day(db, e, task_status="NOT_DONE")
    red = progression.submit_selfcheck(db, e, best_answers(db, "BOUND", 1, worst=True))
    assert red["zone"] == "RED", red["zone"]
    assert red["core_score"] == 0
    ok.append(f"scoring: худшие ответы BOUND W1 → зона {red['zone']}(0) ✓")

    # ── 3b. CRITICAL-LOGIC по refs: REAL W1 (нормализовано) ──
    er = progression.enroll(db, UID, "REAL")
    w1 = db.execute(select(m.ModuleWeek).where(m.ModuleWeek.module_code == "REAL",
                                               m.ModuleWeek.n == 1)).scalar_one()
    ctr = db.execute(select(m.CriticalTrigger).where(m.CriticalTrigger.week_id == w1.id)).scalar_one()
    assert ctr.refs, "REAL W1 critical.refs пусты — нормализация не применилась"
    base = best_answers(db, "REAL", 1)                 # лучшие ответы — critical не должен сработать
    no = scoring.score_week(db, er, 1, base, persist=False)
    assert len(no["critical_texts"]) == 0, "critical не должен срабатывать на лучших ответах REAL"
    ref = ctr.refs[0]
    base[ref["q"]] = ref["opt"]                          # выбрать критичный вариант
    cr = scoring.score_week(db, er, 1, base, persist=False)
    assert len(cr["critical_texts"]) >= 1, "REAL critical по refs не сработал"
    ok.append(f"critical-logic (refs): REAL W1 refs={len(ctr.refs)} → срабатывает по критичному варианту, молчит без него ✓")

    # ── 3c. CRITICAL-LOGIC по refs: BOUND W1 (нормализовано) ──
    eb = progression.enroll(db, UID, "BOUND")
    wb = db.execute(select(m.ModuleWeek).where(m.ModuleWeek.module_code == "BOUND",
                                               m.ModuleWeek.n == 1)).scalar_one()
    ctb = db.execute(select(m.CriticalTrigger).where(m.CriticalTrigger.week_id == wb.id)).scalar_one()
    assert ctb.refs, "BOUND W1 critical.refs пусты — нормализация не применилась"
    base = best_answers(db, "BOUND", 1, worst=True)      # худшие — critical НЕ должен сработать
    no = scoring.score_week(db, eb, 1, base, persist=False)
    assert len(no["critical_texts"]) == 0, "critical не должен срабатывать на нейтральных worst-flag"
    ref = ctb.refs[0]
    base[ref["q"]] = ref["opt"]                           # выбрать сигнальный flag-вариант
    yes = scoring.score_week(db, eb, 1, base, persist=False)
    assert len(yes["critical_texts"]) >= 1, "BOUND critical по refs не сработал"
    ok.append(f"critical-logic (refs): BOUND W1 min_hits={ctb.min_hits}, refs={len(ctb.refs)} → срабатывает по сигнальному варианту, молчит без него ✓")

    # ── 4. ПОСТМОДУЛЬ flags (BOUND): накопить флаги, получить фокусы ──
    cleanup(db, UID)
    e = progression.enroll(db, UID, "BOUND")
    for wk in range(1, 7):
        for d in range(1, 8):
            progression.complete_day(db, e, task_status="DONE")
        progression.submit_selfcheck(db, e, best_answers(db, "BOUND", wk))  # макс flag_weight → флаги копятся
    pm = postmodule.run_flags(db, e)
    assert pm["kind"] == "flags"
    assert pm["auto_switch"] is False
    assert len(pm["focuses"]) <= 2
    ok.append(f"постмодуль flags: фокусов={len(pm['focuses'])} {[f['tag'] for f in pm['focuses']]}, автоперехода нет ✓")

    # ── 5. ПОСТМОДУЛЬ test (REAL): сильные ответы по теме ANX ──
    cleanup(db, UID)
    e = progression.enroll(db, UID, "REAL")
    cfg = db.get(m.PostmoduleConfig, "REAL")
    # для каждой темы выберем вариант с макс весом в каждом из 3 вопросов
    test_ans = {}
    for t in cfg.config["topics"]:
        picks = []
        for q in t["questions"]:
            ws = [int(o.get("weight", 0)) for o in q["options"]]
            picks.append(ws.index(max(ws)))
        test_ans[t["tag"]] = picks
    pt = postmodule.run_test(db, e, test_ans)
    assert pt["kind"] == "test"
    assert all(0 <= s <= 9 for s in pt["scores"].values()), pt["scores"]
    assert len(pt["recommended"]) >= 1, pt["scores"]
    ok.append(f"постмодуль test: баллы тем {pt['scores']}, рекомендовано {[r['tag'] for r in pt['recommended']]} ✓")

    # ── 6. ТЕСТ-РЕЖИМ: перемотка всей программы (best) + guard ──
    from app.services import testmode
    cleanup(db, UID)
    en = progression.enroll(db, UID, "BOUND")                 # normal
    try:
        testmode.run(db, en, scope="program"); assert False, "перемотка не должна работать в normal"
    except ValueError:
        pass
    et = progression.enroll(db, UID, "BOUND", mode="test")     # test
    one = testmode.run(db, et, scope="day")
    assert one["steps"][0]["event"] == "day" and et.status == "active"
    full = testmode.run(db, et, scope="program", preset="best")
    scs = [s for s in full["steps"] if s["event"] == "selfcheck"]
    assert full["status"] == "completed"
    assert [s["zone"] for s in scs] == ["GREEN"] * 6, [s["zone"] for s in scs]
    assert full["postmodule"]["kind"] == "flags"
    ok.append(f"test-режим: guard(normal) блокирует; scope=day/program работает; "
              f"best→6×GREEN, постмодуль {full['postmodule']['kind']}, фокусов {len(full['postmodule']['focuses'])} ✓")

    cleanup(db, UID)
    print("\n".join("✓ " + x for x in ok))
    print("\nВСЕ ДВИЖКИ РАБОТАЮТ")


if __name__ == "__main__":
    main()
