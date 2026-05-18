from datetime import datetime

from app.schemas import ScreenerResult


class ScreenerService:
    def results(self, list_type: str) -> list[ScreenerResult]:
        if list_type == "rebound":
            rows = [
                ("000001", "示例科技", 82, -3.2, "缩量企稳 + 接近支撑位"),
                ("000002", "示例医药", 79, -1.8, "跌幅充分 + 放量止跌"),
                ("000003", "示例消费", 75, 0.6, "远离均线 + 情绪修复"),
            ]
        else:
            list_type = "trend"
            rows = [
                ("300308", "中际旭创", 91, 3.84, "行业强 + 放量突破"),
                ("300502", "新易盛", 88, 5.12, "相对强度前列"),
                ("601138", "工业富联", 84, 2.27, "量能持续放大"),
            ]

        return [
            ScreenerResult(
                list_type=list_type,  # type: ignore[arg-type]
                symbol=symbol,
                name=name,
                score=score,
                change_pct=change_pct,
                reason=reason,
                risk_status="通过",
                generated_at=datetime.now(),
            )
            for symbol, name, score, change_pct, reason in rows
        ]


screener_service = ScreenerService()
