from datetime import UTC, date, datetime

from sqlalchemy import func, select

from src.domains.experience.models import ExperienceIssueDaily, ExperienceMetricDaily
from src.domains.experience.repository import ExperienceRepository


async def test_upsert_metric_updates_existing_row(test_db):
    async with test_db() as session:
        repo = ExperienceRepository(session)

        first = await repo.upsert_metric(
            shop_id="1001",
            metric_date=date(2026, 3, 1),
            dimension="product",
            metric_key="dimension_score",
            metric_score=90.0,
            metric_value=90.0,
            metric_unit="pt",
            source_field="raw.product.score",
            source="seed",
        )
        second = await repo.upsert_metric(
            shop_id="1001",
            metric_date=date(2026, 3, 1),
            dimension="product",
            metric_key="dimension_score",
            metric_score=92.0,
            metric_value=92.0,
            metric_unit="pt",
            source_field="raw.product.score",
            source="seed_v2",
        )

        count = (
            await session.execute(
                select(func.count(ExperienceMetricDaily.id)).where(
                    ExperienceMetricDaily.shop_id == "1001",
                    ExperienceMetricDaily.metric_date == date(2026, 3, 1),
                    ExperienceMetricDaily.dimension == "product",
                    ExperienceMetricDaily.metric_key == "dimension_score",
                )
            )
        ).scalar_one()

        assert first.id == second.id
        assert second.metric_score == 92.0
        assert second.source == "seed_v2"
        assert count == 1


async def test_list_issues_filters_and_paginates(test_db):
    async with test_db() as session:
        repo = ExperienceRepository(session)
        for issue in [
            ExperienceIssueDaily(
                shop_id="1001",
                metric_date=date(2026, 3, 3),
                dimension="product",
                issue_key="i1",
                issue_title="issue 1",
                status="pending",
                owner="owner_1",
                impact_score=10.0,
                deduct_points=2.0,
                occurred_at=datetime(2026, 3, 3, 8, 0, tzinfo=UTC),
                source="seed",
            ),
            ExperienceIssueDaily(
                shop_id="1001",
                metric_date=date(2026, 3, 2),
                dimension="product",
                issue_key="i2",
                issue_title="issue 2",
                status="resolved",
                owner="owner_2",
                impact_score=7.0,
                deduct_points=1.0,
                occurred_at=datetime(2026, 3, 2, 8, 0, tzinfo=UTC),
                source="seed",
            ),
            ExperienceIssueDaily(
                shop_id="1001",
                metric_date=date(2026, 3, 1),
                dimension="risk",
                issue_key="i3",
                issue_title="issue 3",
                status="pending",
                owner="owner_3",
                impact_score=16.0,
                deduct_points=4.5,
                occurred_at=datetime(2026, 3, 1, 8, 0, tzinfo=UTC),
                source="seed",
            ),
        ]:
            session.add(issue)
        await session.commit()

        rows, total = await repo.list_issues(
            shop_id="1001",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 3),
            dimension="product",
            status="pending",
            page=1,
            size=10,
        )

        assert total == 1
        assert len(rows) == 1
        assert rows[0].issue_key == "i1"

        paged_rows, paged_total = await repo.list_issues(
            shop_id="1001",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 3),
            dimension=None,
            status=None,
            page=1,
            size=2,
        )
        assert paged_total == 3
        assert len(paged_rows) == 2
        assert paged_rows[0].metric_date >= paged_rows[1].metric_date


async def test_get_latest_metric_date_by_dimension(test_db):
    async with test_db() as session:
        repo = ExperienceRepository(session)
        for metric_date in [date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 4)]:
            await repo.upsert_metric(
                shop_id="1001",
                metric_date=metric_date,
                dimension="product",
                metric_key="dimension_score",
                metric_score=90.0,
                metric_value=90.0,
                metric_unit="pt",
                source_field="raw.product.score",
            )
        await repo.upsert_metric(
            shop_id="1001",
            metric_date=date(2026, 3, 3),
            dimension="risk",
            metric_key="dimension_score",
            metric_score=80.0,
            metric_value=80.0,
            metric_unit="pt",
            source_field="raw.risk.score",
        )

        latest_product = await repo.get_latest_metric_date(
            shop_id="1001",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 4),
            dimension="product",
        )
        latest_risk = await repo.get_latest_metric_date(
            shop_id="1001",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 4),
            dimension="risk",
        )

        assert latest_product == date(2026, 3, 4)
        assert latest_risk == date(2026, 3, 3)
