"""Async HTTP-клиент к backend Mental Club. Бот не содержит бизнес-логики."""
from __future__ import annotations

import httpx

from config import API_BASE_URL, PROVIDER


class API:
    def __init__(self, base_url: str = API_BASE_URL):
        self._c = httpx.AsyncClient(base_url=base_url, timeout=30)

    async def close(self):
        await self._c.aclose()

    async def _post(self, path: str, json: dict) -> dict:
        r = await self._c.post(path, json=json)
        r.raise_for_status()
        return r.json()

    async def _get(self, path: str) -> dict:
        r = await self._c.get(path)
        r.raise_for_status()
        return r.json()

    # identity
    async def resolve_user(self, tg_id: int) -> int:
        r = await self._post("/api/v1/users/resolve",
                             {"provider": PROVIDER, "provider_user_id": str(tg_id)})
        return r["user_id"]

    # catalog / intake
    async def modules(self) -> list[dict]:
        return await self._get("/api/v1/modules")

    async def intake_questions(self) -> dict:
        return await self._get("/api/v1/intake")

    async def submit_intake(self, tg_id: int, answers: dict[int, int]) -> dict:
        return await self._post("/api/v1/intake/submit", {
            "provider": PROVIDER, "provider_user_id": str(tg_id),
            "answers": {str(k): v for k, v in answers.items()},
        })

    # enrollment / flow
    async def enroll(self, tg_id: int, module_code: str, mode: str = "normal") -> dict:
        return await self._post("/api/v1/enroll", {
            "provider": PROVIDER, "provider_user_id": str(tg_id),
            "module_code": module_code, "mode": mode,
        })

    async def abandon_active(self, tg_id: int) -> dict:
        return await self._post("/api/v1/users/abandon-active",
                               {"provider": PROVIDER, "provider_user_id": str(tg_id)})

    async def reset_user(self, tg_id: int) -> dict:
        return await self._post("/api/v1/users/reset",
                               {"provider": PROVIDER, "provider_user_id": str(tg_id)})

    async def get_settings(self, tg_id: int) -> dict:
        return await self._post("/api/v1/users/settings",
                               {"provider": PROVIDER, "provider_user_id": str(tg_id)})

    async def update_settings(self, tg_id: int, **fields) -> dict:
        return await self._post("/api/v1/users/settings/update",
                               {"provider": PROVIDER, "provider_user_id": str(tg_id), **fields})

    async def reminders_due(self) -> list[dict]:
        r = await self._post("/api/v1/reminders/due", {})
        return r["due"]

    async def mark_reminded(self, tg_id: int | str, slot: str) -> dict:
        return await self._post("/api/v1/reminders/mark",
                               {"provider": PROVIDER, "provider_user_id": str(tg_id), "slot": slot})

    async def user_enrollments(self, tg_id: int) -> list[dict]:
        r = await self._post("/api/v1/users/enrollments",
                             {"provider": PROVIDER, "provider_user_id": str(tg_id)})
        return r["enrollments"]

    async def status(self, eid: int) -> dict:
        return await self._get(f"/api/v1/enrollments/{eid}/status")

    async def journal_list(self, tg_id: int, module_code: str | None = None) -> list[dict]:
        body = {"provider": PROVIDER, "provider_user_id": str(tg_id)}
        if module_code:
            body["module_code"] = module_code
        r = await self._post("/api/v1/journal/list", body)
        return r["entries"]

    async def journal_add(self, tg_id: int, text: str, module_code: str | None = None) -> dict:
        return await self._post("/api/v1/journal", {
            "provider": PROVIDER, "provider_user_id": str(tg_id),
            "text": text, "module_code": module_code})

    async def today(self, eid: int) -> dict:
        return await self._get(f"/api/v1/enrollments/{eid}/today")

    async def set_audio_file_id(self, code: str, file_id: str) -> dict:
        return await self._post(f"/api/v1/audio/{code}/tg-file-id", {"tg_file_id": file_id})

    async def open_day(self, eid: int, **payload) -> dict:
        return await self._post(f"/api/v1/enrollments/{eid}/open-day", payload)

    async def close_day(self, eid: int, **payload) -> dict:
        return await self._post(f"/api/v1/enrollments/{eid}/close-day", payload)

    async def complete_day(self, eid: int, **payload) -> dict:
        return await self._post(f"/api/v1/enrollments/{eid}/complete-day", payload)

    async def selfcheck_questions(self, eid: int) -> dict:
        return await self._get(f"/api/v1/enrollments/{eid}/selfcheck-questions")

    async def selfcheck(self, eid: int, answers: dict[int, int]) -> dict:
        return await self._post(f"/api/v1/enrollments/{eid}/selfcheck",
                               {"answers": {str(k): v for k, v in answers.items()}})

    async def final_product_template(self, eid: int) -> dict:
        return await self._get(f"/api/v1/enrollments/{eid}/final-product/template")

    async def final_product_save(self, eid: int, answers: list[str]) -> dict:
        return await self._post(f"/api/v1/enrollments/{eid}/final-product", {"answers": answers})

    async def final_products_list(self, tg_id: int) -> list[dict]:
        r = await self._post("/api/v1/final-products/list",
                             {"provider": PROVIDER, "provider_user_id": str(tg_id)})
        return r.get("items", [])

    async def final_product_file_bytes(self, eid: int) -> bytes:
        r = await self._c.get(f"/api/v1/enrollments/{eid}/final-product/file")
        r.raise_for_status()
        return r.content

    async def postmodule_questions(self, eid: int) -> dict:
        return await self._get(f"/api/v1/enrollments/{eid}/postmodule-questions")

    async def postmodule(self, eid: int, answers: dict | None = None) -> dict:
        return await self._post(f"/api/v1/enrollments/{eid}/postmodule", {"answers": answers})

    async def test_advance(self, eid: int, scope: str = "day", preset: str = "best") -> dict:
        return await self._post(f"/api/v1/enrollments/{eid}/test/advance",
                               {"scope": scope, "preset": preset})

    # ИИ
    async def ask(self, tg_id: int, question: str) -> dict:
        return await self._post("/api/v1/ai/ask", {
            "provider": PROVIDER, "provider_user_id": str(tg_id), "question": question})

    async def insight(self, eid: int) -> dict:
        return await self._post(f"/api/v1/enrollments/{eid}/insight", {})

    async def week_insight(self, eid: int) -> dict:
        return await self._post(f"/api/v1/enrollments/{eid}/week-insight", {})


api = API()
