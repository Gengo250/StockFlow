"""Capture deterministic UI snapshots, optionally compare with an earlier capture."""
import argparse
import os
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QPA_PLATFORMTHEME'] = ''
os.environ['QT_STYLE_OVERRIDE'] = 'Fusion'

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QScrollArea
from stockflow.presentation.windows.main_window import MainWindow
from stockflow.presentation.widgets.user_form import UserForm
from stockflow.presentation.demo_users import DEMO_USERS


def capture(output, baseline=None):
    app = QApplication.instance() or QApplication([])
    app.setCursorFlashTime(0)
    output.mkdir(parents=True, exist_ok=True)
    failures = []
    count = 0

    def snapshot(widget, name):
        nonlocal count
        app.processEvents()
        app.processEvents()
        image = widget.grab().toImage()
        path = output / f'{name}.png'
        if not image.save(str(path)):
            raise RuntimeError(f'Could not save {path}')
        if baseline is not None and image != QImage(str(baseline / path.name)):
            failures.append(path.name)
        count += 1

    for width, height in ((1440, 900), (1024, 768)):
        window = MainWindow()
        window.resize(width, height)
        window.show()
        prefix = str(width)
        for key in window.page_widgets:
            window.show_page(key)
            snapshot(window, f'{prefix}-{key}')
        for page, name in ((window.novo_produto_page, 'new-product'),
                           (window.editar_produto_page, 'edit-product')):
            if page.edit_mode:
                page.load_product(window.estoque_page.produtos[0])
            window.pages.setCurrentWidget(page)
            snapshot(window, f'{prefix}-{name}')
            scroll = page.findChild(QScrollArea)
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
            snapshot(window, f'{prefix}-{name}-bottom')
        window._show_product_details('PRD-009')
        snapshot(window, f'{prefix}-details')
        window._show_product_details('missing')
        snapshot(window, f'{prefix}-details-error')
        for user, name in ((None, 'new-user'), (DEMO_USERS[0], 'edit-user')):
            form = UserForm(user, window)
            form.setStyleSheet(window.page_widgets['usuarios'].styleSheet())
            form.show()
            snapshot(form, f'{prefix}-{name}')
            form.close()
        window.close()
    print(f'{count} snapshots; {len(failures)} differences')
    if failures:
        raise SystemExit('\n'.join(failures))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    capture(args.output, args.baseline)
