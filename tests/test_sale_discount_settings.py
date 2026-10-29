from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.pages.overview import SettingsPage


def test_discount_limit_settings_are_admin_only(qapp):
    admin = SettingsPage(conta_por_papel(UserRole.ADMIN).session())
    seller = SettingsPage(conta_por_papel(UserRole.SELLER).session())

    assert not admin.discount_limits_card.isHidden()
    assert seller.discount_limits_card.isHidden()


def test_admin_settings_emit_limit_to_persist(qapp):
    page = SettingsPage(conta_por_papel(UserRole.ADMIN).session())
    received = []
    page.discount_limits_save_requested.connect(received.append)
    page.seller_discount_limit.setText("7,5")

    page.save_discount_limits_button.click()

    assert received == ["7,5"]
    page.set_discount_limits({"SELLER": 12.5, "ADMIN": None})
    assert page.seller_discount_limit.text() == "12,5"
