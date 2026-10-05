import os
import tempfile
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_PLATFORMTHEME"] = ""
os.environ["QT_STYLE_OVERRIDE"] = "Fusion"

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from stockflow.presentation.app import LoginFlow
from stockflow.presentation.windows.login_window import DEMO_EMAIL, DEMO_PASSWORD, LoginWindow


class LoginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_login_logout_and_remember_email(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(f"{directory}/settings.ini", QSettings.IniFormat)
            flow = LoginFlow(settings)
            login = flow.login
            self.addCleanup(login.close)
            login.show()
            self.assertIsNone(flow.main)
            login.submit_button.click()
            self.assertIn("Preencha", login.error.text())
            login.email_input.setText(DEMO_EMAIL)
            login.password_input.setText("senha errada")
            login.submit_button.click()
            self.assertIsNone(flow.main)
            self.assertIn("incorretos", login.error.text())
            login.password_input.setText(DEMO_PASSWORD)
            login.toggle_password.trigger()
            self.assertEqual(login.password_input.echoMode(), QLineEdit.Normal)
            login.email_input.setText(f"  {DEMO_EMAIL.upper()}  ")
            login.remember_email.setChecked(True)
            QTest.keyClick(login.password_input, Qt.Key_Return)
            self.addCleanup(flow.main.close)
            self.assertTrue(flow.main.isVisible())
            self.assertFalse(login.isVisible())
            self.assertEqual(login.password_input.text(), "")
            self.assertEqual(settings.allKeys(), ["login/email"])
            self.assertEqual(settings.value("login/email"), DEMO_EMAIL)
            flow.main.sidebar.logout_button.click()
            self.assertTrue(login.isVisible())
            self.assertIsNone(flow.main)  # O contexto anterior é descartado no logout.
            self.assertEqual(login.password_input.echoMode(), QLineEdit.Password)
            fresh = LoginWindow(settings)
            self.addCleanup(fresh.close)
            self.assertEqual(fresh.email_input.text(), DEMO_EMAIL)
            self.assertEqual(fresh.password_input.text(), "")
            login.remember_email.setChecked(False)
            login.password_input.setText(DEMO_PASSWORD)
            login.submit_button.click()
            self.assertEqual(settings.value("login/email"), "")

    def test_login_layout_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            login = LoginWindow(QSettings(f"{directory}/settings.ini", QSettings.IniFormat))
            self.addCleanup(login.close)
            login.show()
            for width, height in ((1426, 878), (440, 640)):
                login.resize(width, height)
                self.app.processEvents()
                self.assertEqual(login.size().width(), width)
                self.assertEqual(login.brand.isVisible(), width >= 1100)
                self.assertTrue(login.submit_button.isVisible())
                self.assertGreaterEqual(login.email_input.width(), 300)
                login.grab().save(f"/tmp/stockflow-login-{width}.png")


if __name__ == "__main__":
    unittest.main()
