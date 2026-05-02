"""Print all unbooked slots from DB: service, date, time, doctor."""
from collections import defaultdict

from db.database import SessionLocal
from db.models import Provider, Slot


def main() -> None:
    db = SessionLocal()
    rows = (
        db.query(Slot, Provider)
        .join(Provider, Slot.provider_id == Provider.id)
        .filter(Slot.is_booked.is_(False))
        .order_by(Provider.service, Slot.date, Slot.time, Provider.name)
        .all()
    )
    by_service: dict[str, list[tuple[str, str, str, int]]] = defaultdict(list)
    for slot, provider in rows:
        by_service[provider.service].append(
            (str(slot.date), str(slot.time)[:5], provider.name, slot.id)
        )

    for svc in sorted(by_service.keys()):
        print(f"SERVICE (DB): {svc}")
        for date_s, time_s, name, sid in sorted(by_service[svc], key=lambda x: (x[0], x[1], x[2])):
            print(f"  {date_s}  {time_s}  {name}  (slot_id={sid})")

    print(f"\nTOTAL FREE SLOTS: {len(rows)}")
    db.close()


if __name__ == "__main__":
    main()
