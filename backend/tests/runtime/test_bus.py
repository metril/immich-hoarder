import asyncio

from app.runtime.bus import EventBus


async def test_bus_subscriber_removed_on_exit() -> None:
    bus = EventBus()
    with bus.subscribe(1) as sub:
        bus.publish(1, {"type": "log"})
        ev = await asyncio.wait_for(sub.__anext__(), 1)
        assert ev["type"] == "log"
        assert bus.subscriber_count(1) == 1
    assert bus.subscriber_count(1) == 0
    bus.publish(1, {"type": "log"})  # no error without subscribers


async def test_dashboard_gets_all_events_with_job_id() -> None:
    bus = EventBus()
    with bus.subscribe(None) as dash, bus.subscribe(2) as other:
        bus.publish(1, {"type": "log"})
        ev = await asyncio.wait_for(dash.__anext__(), 1)
        assert ev["job_id"] == 1
        assert other._queue.empty()


async def test_slow_subscriber_drops_oldest_with_gap_marker() -> None:
    bus = EventBus()
    with bus.subscribe(1) as sub:
        for i in range(1001):
            bus.publish(1, {"type": "log", "i": i})
        got = [await sub.__anext__() for _ in range(1000)]
    assert any(e["type"] == "gap" for e in got)
    assert got[-1]["i"] == 1000
    assert got[0].get("i") != 0
