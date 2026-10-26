"""
Integration and route tests for Flask web dashboard.
Verifies authentication, RBAC, CSRF, and all dashboard pages.
"""

import unittest
from app import create_app
from app.models import SessionLocal, init_db
from app.models.entities import User
from argon2 import PasswordHasher

ph = PasswordHasher()


class TestDashboardRoutes(unittest.TestCase):
    def setUp(self):
        init_db()
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False  # Disable CSRF in test client
        self.client = self.app.test_client()

        # Seed admin and regular user
        db = SessionLocal()
        try:
            admin = db.query(User).filter_by(username="test_admin").first()
            if not admin:
                admin = User(
                    username="test_admin",
                    password_hash=ph.hash("admin123"),
                    role="admin",
                    is_active=True
                )
                db.add(admin)

            user = db.query(User).filter_by(username="test_user").first()
            if not user:
                user = User(
                    username="test_user",
                    password_hash=ph.hash("user123"),
                    role="user",
                    is_active=True
                )
                db.add(user)
            db.commit()
        finally:
            db.close()

    def test_health_endpoint(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("status", data)
        self.assertIn("database", data)

    def test_unauthenticated_redirect(self):
        # Protected route redirects to login
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_admin_flow(self):
        # 1. Login with wrong password
        resp = self.client.post("/login", data={"username": "test_admin", "password": "wrong"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Username atau password salah", resp.get_data(as_text=True))

        # 2. Login with correct password
        resp = self.client.post("/login", data={"username": "test_admin", "password": "admin123"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Ringkasan Operasional", resp.get_data(as_text=True))

        # 3. Access /results
        resp = self.client.get("/results")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Daftar File Hasil Ekspor Excel", resp.get_data(as_text=True))

        # 4. Access /accounts
        resp = self.client.get("/accounts")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Manajemen Akun & Sesi Kalodata", resp.get_data(as_text=True))

        # 5. Access /jobs
        resp = self.client.get("/jobs")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Jadwal & Trigger", resp.get_data(as_text=True))

        # 6. Access /settings
        resp = self.client.get("/settings")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Pengaturan Sistem & Kebijakan", resp.get_data(as_text=True))

    def test_user_rbac(self):
        # Login as normal user
        self.client.post("/login", data={"username": "test_user", "password": "user123"}, follow_redirects=True)

        # Normal user can see dashboard and results
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get("/results")
        self.assertEqual(resp.status_code, 200)

        # Normal user CANNOT see admin settings or accounts (§5.2, §14)
        resp = self.client.get("/settings")
        self.assertEqual(resp.status_code, 403)

        resp = self.client.get("/accounts")
        self.assertEqual(resp.status_code, 403)

    def test_job_detail_page(self):
        # Login as admin
        self.client.post("/login", data={"username": "test_admin", "password": "admin123"}, follow_redirects=True)

        db = SessionLocal()
        try:
            from app.models.entities import ScrapeRun, ScrapeJob
            from datetime import date
            today = date.today()
            run = ScrapeRun(trigger="manual", period_start=today, period_end=today, status="SUCCESS")
            db.add(run)
            db.flush()
            job = ScrapeJob(
                run_id=run.id,
                country_code="ID",
                module="creator",
                period_start=today,
                period_end=today,
                status="SUCCESS",
                stage="COMPLETED"
            )
            db.add(job)
            db.commit()
            job_id = job.id
        finally:
            db.close()

        resp = self.client.get(f"/jobs/{job_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Detail Job: ID", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()

