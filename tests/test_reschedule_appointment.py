"""
Unit tests for reschedule_appointment (SQLite in-memory; no HTTP).
Run: python -m unittest tests.test_reschedule_appointment -v
"""

import os
import unittest
from datetime import date, time

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.database import Base
from db.models import Appointment, Provider, Slot, User
from services.booking_service import reschedule_appointment


class TestRescheduleAppointment(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"] = ""
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, future=True)

    def _seed_two_slots(self) -> tuple[Session, Appointment, Slot, Slot]:
        db: Session = self.Session()
        p = Provider(name="Dr Test", service="general", is_active=True)
        db.add(p)
        db.flush()
        u = User(name="Patient", email="p@test.com", phone="0300")
        db.add(u)
        db.flush()
        d = date(2026, 5, 1)
        s1 = Slot(provider_id=p.id, date=d, time=time(9, 0), end_time=time(9, 30), is_booked=True)
        s2 = Slot(provider_id=p.id, date=d, time=time(10, 0), end_time=time(10, 30), is_booked=False)
        db.add_all([s1, s2])
        db.flush()
        appt = Appointment(
            user_id=u.id,
            provider_id=p.id,
            date=d,
            time=time(9, 0),
            status="confirmed",
            google_calendar_event_id=None,
        )
        db.add(appt)
        db.commit()
        db.refresh(s1)
        db.refresh(s2)
        db.refresh(appt)
        return db, appt, s1, s2

    def test_reschedule_moves_booking_and_slots(self) -> None:
        db, appt, s1, s2 = self._seed_two_slots()
        try:
            out, cal_msg, did = reschedule_appointment(db, appt.id, s2.id)
            self.assertTrue(did)
            self.assertEqual(out.date, s2.date)
            self.assertEqual(out.time, s2.time)
            db.refresh(s1)
            db.refresh(s2)
            self.assertFalse(s1.is_booked)
            self.assertTrue(s2.is_booked)
            self.assertIsInstance(cal_msg, str)
        finally:
            db.close()

    def test_same_slot_rejected_clearly(self) -> None:
        db, appt, s1, _s2 = self._seed_two_slots()
        try:
            with self.assertRaises(ValueError) as ctx:
                reschedule_appointment(db, appt.id, s1.id)
            self.assertIn("already your current", str(ctx.exception).lower())
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
