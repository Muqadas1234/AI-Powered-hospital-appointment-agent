from db.database import Base, SessionLocal, engine
from services.auth_service import ensure_default_admin


def seed_data():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_default_admin(db)
        db.commit()
        print("Seed complete: admin ensured. No demo data inserted.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
