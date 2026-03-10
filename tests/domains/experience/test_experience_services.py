from datetime import UTC, date, datetime

from src.domains.experience.repository import ExperienceRepository
from src.domains.experience.services import ExperienceQueryService


async def _seed_metrics_and_issues(repo: ExperienceRepository) -> None:
    for metric_date, values in [
        (
            date(2026, 3, 1),
            {"product": 90.0, "logistics": 88.0, "service": 86.0, "risk": 80.0},
        ),
        (
            date(2026, 3, 2),
            {"product": 91.0, "logistics": 87.0, "service": 87.0, "risk": 81.0},
        ),
        (
            date(2026, 3, 3),
            {"product": 92.0, "logistics": 89.0, "service": 88.0, "risk": 79.0},
        ),
    ]:
        for dimension, score in values.items():
            await repo.upsert_metric(
                shop_id="1001",
                metric_date=metric_date,
                dimension=dimension,
                metric_key="dimension_score",
                metric_score=score,
                metric_value=score,
                metric_unit="pt",
                source_field=f"raw.{dimension}.score",
                is_penalty=dimension == "risk",
                deduct_points=max(0.0, 100.0 - score) if dimension == "risk" else 0.0,
                source="seed",
            )

    await repo.upsert_metric(
        shop_id="1001",
        metric_date=date(2026, 3, 3),
        dimension="risk",
        metric_key="fake_transaction",
        metric_score=78.0,
        metric_value=22.0,
        metric_unit="pt",
        source_field="raw.risk.fake_transaction_cases",
        is_penalty=True,
        deduct_points=22.0,
        source="seed",
        extra={"impact_score": 14.3, "status": "processing", "owner": "owner_7"},
    )

    await repo.upsert_metric(
        shop_id="1001",
        metric_date=date(2026, 3, 3),
        dimension="product",
        metric_key="product_return_rate",
        metric_score=89.0,
        metric_value=1.8,
        metric_unit="%",
        source_field="raw.product.return_rate",
        source="seed",
    )

    await repo.upsert_issue(
        shop_id="1001",
        metric_date=date(2026, 3, 3),
        dimension="product",
        issue_key="issue_1",
        issue_title="product defect complaints",
        status="pending",
        owner="owner_1",
        impact_score=18.5,
        deduct_points=6.2,
        occurred_at=datetime(2026, 3, 3, 9, 0, tzinfo=UTC),
        deadline_at=datetime(2026, 3, 6, 18, 0, tzinfo=UTC),
        source="seed",
    )
    await repo.upsert_issue(
        shop_id="1001",
        metric_date=date(2026, 3, 2),
        dimension="risk",
        issue_key="issue_2",
        issue_title="policy violation warning",
        status="resolved",
        owner="owner_2",
        impact_score=11.0,
        deduct_points=3.0,
        occurred_at=datetime(2026, 3, 2, 8, 0, tzinfo=UTC),
        deadline_at=None,
        source="seed",
    )


async def test_get_overview_returns_weighted_score_and_alerts(test_db):
    async with test_db() as session:
        repo = ExperienceRepository(session)
        await _seed_metrics_and_issues(repo)
        await session.commit()

        service = ExperienceQueryService(repo=repo)
        overview = await service.get_overview(shop_id=1001, date_range="30d")

        assert overview.shop_id == 1001
        assert len(overview.dimensions) == 4
        # formula: product*40% + logistics*30% + service*30% - risk_deduct_points
        # latest scores: product=92, logistics=89, service=88, risk_deduct_points=21
        assert overview.overall_score == 68.9
        assert overview.alerts.total == 2
        assert overview.alerts.critical == 1
        assert overview.alerts.warning == 1
        assert overview.alerts.unread == 1


async def test_get_metric_detail_risk_contains_penalty_fields(test_db):
    async with test_db() as session:
        repo = ExperienceRepository(session)
        await _seed_metrics_and_issues(repo)
        await session.commit()

        service = ExperienceQueryService(repo=repo)
        detail = await service.get_metric_detail(
            shop_id=1001,
            metric_type="risk",
            period="30d",
            date_range="30d",
        )

        assert detail.metric_type == "risk"
        assert len(detail.sub_metrics) == 3
        assert len(detail.trend) >= 1
        fake_tx = [
            item for item in detail.sub_metrics if item.id == "fake_transaction"
        ][0]
        assert fake_tx.deduct_points is not None
        assert fake_tx.impact_score is not None
        assert fake_tx.status == "processing"
        assert fake_tx.owner == "owner_7"


async def test_get_dashboard_kpis_contains_trend_and_change(test_db):
    async with test_db() as session:
        repo = ExperienceRepository(session)
        await _seed_metrics_and_issues(repo)
        await session.commit()

        service = ExperienceQueryService(repo=repo)
        kpis = await service.get_dashboard_kpis(shop_id=1001, date_range="30d")

        assert kpis.shop_id == 1001
        assert len(kpis.kpis) == 3
        assert len(kpis.trend) == 3
        assert kpis.kpis[0].id == "orders"
        assert kpis.kpis[1].id == "gmv"
        assert kpis.kpis[2].id == "refund_rate"
        assert kpis.kpis[0].change.endswith("%")
